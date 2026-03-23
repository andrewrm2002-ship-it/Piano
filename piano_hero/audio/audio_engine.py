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

# Bandpass filter: very gentle, just removes DC/sub-bass and extreme HF.
# We keep the hum in the signal and let the noise-profile FFT detector
# subtract it spectrally (more precise than a broad filter).
_BP_LOW_HZ = 200.0
_BP_HIGH_HZ = 3000.0


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

    def __init__(self, pitch_queue: queue.Queue, device_index=None, input_gain=None):
        """
        Args:
            pitch_queue: Thread-safe queue for detection results (6-element tuples).
            device_index: Audio input device index, or None for default.
            input_gain: Software gain multiplier for input signal (default 3.0).
        """
        self.pitch_queue = pitch_queue
        self.device_index = device_index
        self.input_gain = input_gain if input_gain is not None else _DEFAULT_INPUT_GAIN
        self.sample_rate = SAMPLE_RATE
        self.stream = None
        self.detector = PitchDetector(SAMPLE_RATE, BUFFER_SIZE)
        self._running = False
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

        # Auto-detect the input device with the strongest signal
        if self.device_index is not None:
            self._auto_detect_device()

        # Measure noise floor before starting detection
        self._measure_noise_floor()

        # Start detector thread (runs pitch detection off the audio callback)
        self._detect_thread = threading.Thread(target=self._detector_loop,
                                                daemon=True)
        self._detect_thread.start()

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

    def stop(self):
        """Stop and close the audio stream."""
        self._running = False
        self._detect_event.set()  # Unblock detector thread
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
        """Find the Line In device by name.

        The Realtek driver exposes the same jack under multiple API backends
        (MME, DirectSound, WASAPI, WDM-KS) with different indices. We search
        for 'Line In' in the device name and prefer the MME backend since it
        has been the most reliable for this hardware.
        """
        try:
            devices = sd.query_devices()
        except Exception:
            return

        # Priority order: MME Line In > any Line In > configured device
        mme_line_in = None
        any_line_in = None

        for idx, info in enumerate(devices):
            if info['max_input_channels'] == 0:
                continue
            name = info['name'].lower()
            if 'line in' in name:
                if any_line_in is None:
                    any_line_in = idx
                # MME devices don't have "WDM-KS" or "WASAPI" in hostapi
                # MME tends to be the lowest-numbered Line In device
                if mme_line_in is None:
                    mme_line_in = idx

        chosen = mme_line_in or any_line_in or self.device_index
        if chosen != self.device_index:
            try:
                info = sd.query_devices(chosen)
                print(f"Audio: selected '{info['name']}' [device {chosen}]")
            except Exception:
                pass
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
