"""Audio input engine using sounddevice.

Manages audio device selection and streaming. The PortAudio callback copies
audio into a ring buffer; a separate detector thread runs pitch detection
and pushes results to a queue consumed by the game loop.

Features:
- Automatic noise floor measurement on startup
- Onset detection passed through from pitch detector
- Auto-calibration support for timing analysis
- Peak and RMS level tracking for meter display
"""

import queue
import time
import threading
import numpy as np
import sounddevice as sd

from piano_hero.constants import (
    SAMPLE_RATE, BUFFER_SIZE, HOP_SIZE, CHANNELS, SILENCE_THRESHOLD,
)
from piano_hero.audio.pitch_detector import PitchDetector


# Duration in seconds to measure ambient noise on startup
_NOISE_FLOOR_DURATION = 0.5

# Default input gain — set to 1.0; the FFT peak detector handles
# weak signals internally via noise profile subtraction.
_DEFAULT_INPUT_GAIN = 1.0

# Bandpass filter: removes DC/sub-bass below 60 Hz and extreme HF.
# Low cutoff at 60 Hz allows notes down to C2 (65 Hz) through.
# Hum at 60 Hz and harmonics is handled by noise profile subtraction
# in the pitch detector, not by this filter.
_BP_LOW_HZ = 55.0
_BP_HIGH_HZ = 4000.0


def _build_bandpass_sos(low_hz: float, high_hz: float, sr: float):
    """Build a 3rd-order Butterworth bandpass filter (SOS form).

    Returns second-order sections for use with scipy-style sosfilt, or
    a manual cascade if scipy is not available.
    """
    try:
        from scipy.signal import butter
        return butter(3, [low_hz, high_hz], btype='band', fs=sr, output='sos')
    except ImportError:
        # Fallback: simple first-order high-pass only
        return None


def _sosfilt_online(sos, x, state):
    """Apply SOS filter to a block of samples, maintaining state across calls.

    Returns (filtered_output, new_state).
    """
    try:
        from scipy.signal import sosfilt
        y, state = sosfilt(sos, x, zi=state)
        return y.astype(np.float32), state
    except ImportError:
        return x, state


def _sosfilt_init(sos):
    """Create initial filter state (zeros)."""
    try:
        from scipy.signal import sosfilt_zi
        return sosfilt_zi(sos) * 0.0  # Start from silence
    except ImportError:
        return None


class AudioEngine:
    """Manages audio input stream and real-time pitch detection.

    Queue tuple format:
        (note_name, midi_number, frequency, confidence, is_onset, timestamp)

    where is_onset is a bool indicating a detected note onset, and timestamp
    is from time.perf_counter().
    """

    def __init__(self, pitch_queue: queue.Queue, device_index=None, input_gain=None,
                 passthrough=False):
        """
        Args:
            pitch_queue: Thread-safe queue for detection results (6-element tuples).
            device_index: Audio input device index, or None for default.
            input_gain: Software gain multiplier for input signal (default 3.0).
            passthrough: If True, route audio input directly to the computer speakers.
        """
        self.pitch_queue = pitch_queue
        self.device_index = device_index
        self.input_gain = input_gain if input_gain is not None else _DEFAULT_INPUT_GAIN
        self.sample_rate = SAMPLE_RATE
        self.stream = None
        self.detector = PitchDetector(SAMPLE_RATE, BUFFER_SIZE)
        self._running = False
        self._passthrough = passthrough
        self._output_stream = None
        self._output_device = None
        # Ring buffer large enough for polyphonic detection (4096 samples)
        self._poly_buffer_size = max(BUFFER_SIZE, 4096)
        self._ring_buffer = np.zeros(self._poly_buffer_size, dtype=np.float32)
        self._ring_pos = 0
        self._lock = threading.Lock()
        self._detect_event = threading.Event()
        self._detect_thread = None

        # Bandpass filter state (removes ground loop hum + HF noise)
        self._bp_sos = _build_bandpass_sos(_BP_LOW_HZ, _BP_HIGH_HZ, SAMPLE_RATE)
        self._bp_state = _sosfilt_init(self._bp_sos) if self._bp_sos is not None else None

        # Level tracking
        self._latest_rms = 0.0
        self._latest_peak = 0.0

        # Noise floor (updated on start)
        self.noise_floor = SILENCE_THRESHOLD

        # Calibration state
        self._calibrating = False
        self._calibration_lock = threading.Lock()
        self._calibration_onsets: list[float] = []

    @staticmethod
    def list_input_devices():
        """Return list of (index, name, channels, sample_rate) for input devices."""
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                devices.append((
                    i,
                    dev['name'],
                    dev['max_input_channels'],
                    dev['default_samplerate'],
                ))
        return devices

    def start(self):
        """Open the audio stream and begin capturing.

        Measures ambient noise for ~0.5 seconds before entering the main
        detection loop to set an adaptive silence threshold.
        """
        if self._running:
            return

        self._running = True

        # Auto-detect the best input device (USB adapter > Line In > default)
        self._auto_detect_device()

        # Measure noise floor before starting detection
        self._measure_noise_floor()

        # Start detector thread (runs pitch detection off the audio callback)
        self._detect_thread = threading.Thread(target=self._detector_loop,
                                                daemon=True)
        self._detect_thread.start()

        # Open passthrough output to computer speakers (not the USB adapter)
        if self._passthrough:
            self._setup_passthrough_output()

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=HOP_SIZE,
                device=self.device_index,
                channels=CHANNELS,
                dtype='float32',
                callback=self._audio_callback,
            )
            self.stream.start()
        except Exception as e:
            self._running = False
            self._detect_event.set()  # Unblock detector thread so it can exit
            raise RuntimeError(f"Failed to open audio stream: {e}") from e

    def _setup_passthrough_output(self):
        """Open output streams to ALL available speakers (monitor, Realtek, etc).

        Skips the USB audio adapter (that's the input device) to avoid feedback.
        """
        self._output_streams = []
        try:
            devices = sd.query_devices()
            for idx, info in enumerate(devices):
                if info['max_output_channels'] == 0:
                    continue
                name = info['name'].lower()
                # Skip USB audio adapter (input device) and Bluetooth
                if 'usb' in name:
                    continue
                if 'bthhfenum' in name or 'hands-free' in name:
                    continue
                # Skip duplicate backends — only use MME (lowest index per device)
                try:
                    stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        blocksize=HOP_SIZE,
                        device=idx,
                        channels=min(info['max_output_channels'], CHANNELS),
                        dtype='float32',
                    )
                    stream.start()
                    self._output_streams.append((idx, stream))
                    print(f"Audio passthrough: opened '{info['name']}' [device {idx}]")
                except Exception:
                    pass
            # Keep the legacy attribute for the stop() method
            self._output_stream = self._output_streams[0][1] if self._output_streams else None
        except Exception as e:
            print(f"Audio passthrough failed: {e}")
            self._output_streams = []
            self._output_stream = None

    def stop(self):
        """Stop and close the audio stream."""
        self._running = False
        self._detect_event.set()  # Unblock detector thread
        for _, out_stream in getattr(self, '_output_streams', []):
            try:
                out_stream.stop()
                out_stream.close()
            except Exception:
                pass
        self._output_streams = []
        self._output_stream = None
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self._detect_thread is not None:
            self._detect_thread.join(timeout=1.0)
            self._detect_thread = None

    def is_running(self) -> bool:
        return self._running and self.stream is not None

    # ── Calibration ──────────────────────────────────────────────────────────

    def start_calibration(self):
        """Begin recording onset timestamps for timing calibration.

        The game can call this before a calibration sequence, then compare
        collected onset times against expected beat times to compute latency.
        """
        with self._calibration_lock:
            self._calibration_onsets = []
            self._calibrating = True

    def stop_calibration(self) -> list[float]:
        """Stop calibration and return collected onset timestamps.

        Returns:
            List of perf_counter timestamps where onsets were detected.
        """
        with self._calibration_lock:
            self._calibrating = False
            onsets = list(self._calibration_onsets)
            self._calibration_onsets = []
        return onsets

    # ── Auto Device Detection ───────────────────────────────────────────────

    def _auto_detect_device(self):
        """Find the best audio input device.

        Priority: USB Audio Device (external adapter) > Line In > configured.
        USB adapters have proper gain staging and are preferred over the
        motherboard's Realtek Line In which has signal level issues.
        """
        try:
            devices = sd.query_devices()
        except Exception:
            return

        usb_mme = None
        mme_line_in = None
        any_line_in = None

        for idx, info in enumerate(devices):
            if info['max_input_channels'] == 0:
                continue
            name = info['name'].lower()
            # USB audio adapters show up as "Microphone (USB Audio Device)"
            if 'usb' in name and ('microphone' in name or 'mic' in name):
                if usb_mme is None:
                    usb_mme = idx
            elif 'line in' in name:
                if any_line_in is None:
                    any_line_in = idx
                if mme_line_in is None:
                    mme_line_in = idx

        # Priority: USB > MME Line In > any Line In > configured device
        chosen = usb_mme or mme_line_in or any_line_in or self.device_index
        if chosen is not None and chosen != self.device_index:
            try:
                info = sd.query_devices(chosen)
                print(f"Audio: selected '{info['name']}' [device {chosen}]")
            except Exception:
                pass
        if chosen is not None:
            self.device_index = chosen

    # ── Level Meters ─────────────────────────────────────────────────────────

    def get_input_level(self) -> float:
        """Return current RMS level (0.0 to ~1.0) for level meter display."""
        return self._latest_rms

    def get_peak_level(self) -> float:
        """Return current peak level (0.0 to 1.0) for level meter display."""
        return self._latest_peak

    # ── Internal: Noise Floor ────────────────────────────────────────────────

    def _measure_noise_floor(self):
        """Record ambient audio to set noise floor and build noise spectrum profile.

        Records _NOISE_FLOOR_DURATION seconds of silence, computes RMS for the
        silence threshold, and builds an FFT noise profile for spectral
        subtraction in the pitch detector.
        """
        num_samples = int(self.sample_rate * max(_NOISE_FLOOR_DURATION, 1.0))
        try:
            recording = sd.rec(
                frames=num_samples,
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype='float32',
                device=self.device_index,
            )
            sd.wait()
            mono = recording[:, 0]

            # RMS-based noise floor
            ambient_rms = self.detector.measure_noise_floor(mono)
            self.noise_floor = max(SILENCE_THRESHOLD, ambient_rms * 2.0)
            self.detector.noise_floor = self.noise_floor

            # Build noise spectrum profile for FFT peak detector
            buf_size = self.detector.buffer_size
            window = np.hanning(buf_size)
            spectra = []
            for i in range(0, len(mono) - buf_size, buf_size):
                chunk = mono[i:i + buf_size].astype(np.float64)
                spectrum = np.abs(np.fft.rfft(chunk * window))
                spectra.append(spectrum)
            if spectra:
                noise_profile = np.mean(spectra, axis=0)
                self.detector.set_noise_profile(noise_profile)
        except Exception:
            self.noise_floor = SILENCE_THRESHOLD
            self.detector.noise_floor = SILENCE_THRESHOLD

    # ── Internal: Audio Callback ─────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice on the audio thread. Copies data to ring buffer."""
        if not self._running:
            return

        # indata shape: (frames, channels) — take channel 0
        raw = indata[:, 0].copy()

        # Audio passthrough: send raw input directly to all speaker outputs
        if hasattr(self, '_output_streams') and self._output_streams:
            audio_out = indata.copy()
            for _, out_stream in self._output_streams:
                try:
                    # Match channel count
                    if out_stream.channels == 1 and audio_out.shape[1] > 1:
                        out_stream.write(audio_out[:, :1])
                    elif out_stream.channels >= audio_out.shape[1]:
                        out_stream.write(audio_out)
                    else:
                        out_stream.write(audio_out[:, :out_stream.channels])
                except Exception:
                    pass

        # Apply bandpass filter to remove ground loop hum (<130Hz) and HF noise
        if self._bp_sos is not None and self._bp_state is not None:
            filtered, self._bp_state = _sosfilt_online(
                self._bp_sos, raw, self._bp_state)
        else:
            filtered = raw

        # Apply software gain and clip
        mono = np.clip(filtered * self.input_gain, -1.0, 1.0)
        n = len(mono)

        buf_size = self._poly_buffer_size
        with self._lock:
            if self._ring_pos + n <= buf_size:
                self._ring_buffer[self._ring_pos:self._ring_pos + n] = mono
                self._ring_pos += n
            else:
                # Shift buffer left and append new data
                shift = self._ring_pos + n - buf_size
                self._ring_buffer[:buf_size - shift] = self._ring_buffer[shift:buf_size]
                self._ring_buffer[buf_size - n:] = mono
                self._ring_pos = buf_size

            # Compute levels for the meter
            self._latest_rms = float(np.sqrt(np.mean(mono ** 2)))
            self._latest_peak = float(np.max(np.abs(mono)))

            # Signal detector thread if buffer is full
            if self._ring_pos >= buf_size:
                self._detect_event.set()

    # ── Internal: Detector Loop ──────────────────────────────────────────────

    def _detector_loop(self):
        """Runs on a separate thread. Waits for audio data, runs pitch detection."""
        while self._running:
            # Wait for audio callback to signal data is ready
            self._detect_event.wait(timeout=0.1)
            self._detect_event.clear()

            if not self._running:
                break

            # Copy buffer under lock
            with self._lock:
                if self._ring_pos < self._poly_buffer_size:
                    continue
                buf_copy = self._ring_buffer.copy()

            # Run polyphonic pitch detection (outside lock)
            timestamp = time.perf_counter()
            detections = self.detector.detect_polyphonic(buf_copy, max_notes=4)

            if not detections:
                # Push a silence result so the game knows nothing is playing
                self._push_to_queue((None, 0, 0.0, 0.0, False, timestamp))
            else:
                for name, midi, freq, confidence, is_onset in detections:
                    # Record onset for calibration if active
                    if is_onset:
                        with self._calibration_lock:
                            if self._calibrating:
                                self._calibration_onsets.append(timestamp)

                    self._push_to_queue(
                        (name, midi, freq, confidence, is_onset, timestamp))

    def _push_to_queue(self, result):
        """Push a detection result to the queue, dropping oldest if full."""
        try:
            self.pitch_queue.put_nowait(result)
        except queue.Full:
            try:
                self.pitch_queue.get_nowait()
                self.pitch_queue.put_nowait(result)
            except (queue.Empty, queue.Full):
                pass
