"""Pitch detection using FFT-accelerated YIN algorithm with onset detection.

Detects the fundamental frequency of monophonic audio input and maps it
to the nearest MIDI note. Uses FFT-based autocorrelation for O(n log n)
difference function computation. Supports adaptive buffer sizing for
better accuracy across the frequency range.
"""

import numpy as np
from piano_hero.constants import (
    SAMPLE_RATE, BUFFER_SIZE, BUFFER_SIZE_HIGH, CONFIDENCE_THRESHOLD,
    SILENCE_THRESHOLD, MIN_FREQ, MAX_FREQ, HIGH_FREQ_CUTOFF,
    freq_to_midi, midi_to_note_name, MIN_MIDI, MAX_MIDI, ONSET_THRESHOLD,
)


class PitchDetector:
    """Real-time monophonic pitch detector using FFT-accelerated YIN algorithm.

    Features:
    - FFT-based difference function (fully vectorized, no Python for-loops)
    - Adaptive buffer sizing: smaller buffer for high frequencies, larger for low
    - Onset detection via RMS energy tracking
    - Configurable noise floor for silence gating
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE,
                 buffer_size: int = BUFFER_SIZE,
                 noise_floor: float = SILENCE_THRESHOLD):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.buffer_size_high = BUFFER_SIZE_HIGH
        self.noise_floor = noise_floor

        # YIN lag ranges for each buffer size
        self.tau_min = max(2, int(sample_rate / MAX_FREQ))

        self.tau_max_low = min(buffer_size // 2, int(sample_rate / MIN_FREQ))
        self.tau_max_high = min(BUFFER_SIZE_HIGH // 2, int(sample_rate / MIN_FREQ))

        # Onset detection state
        self._prev_rms = 0.0

    def detect(self, audio_buffer: np.ndarray):
        """Detect pitch from an audio buffer.

        Args:
            audio_buffer: Float32 mono audio samples, length >= buffer_size.

        Returns:
            (note_name, midi_number, frequency, confidence, is_onset) or
            (None, 0, 0.0, 0.0, False) if no pitch detected.
        """
        if len(audio_buffer) < self.buffer_size:
            return None, 0, 0.0, 0.0, False

        buf_full = audio_buffer[:self.buffer_size].astype(np.float64)

        # Compute RMS for silence check and onset detection
        rms = np.sqrt(np.mean(buf_full ** 2))

        # Onset detection: flag when RMS jumps significantly
        is_onset = False
        if self._prev_rms > 0:
            rms_ratio = rms / self._prev_rms
            if rms_ratio >= ONSET_THRESHOLD:
                is_onset = True
        elif rms > self.noise_floor:
            # First non-silent frame is an onset
            is_onset = True
        self._prev_rms = rms

        # Silence gate
        if rms < self.noise_floor:
            return None, 0, 0.0, 0.0, False

        # Run detection with the full (low-frequency) buffer
        freq_low, conf_low = self._yin_fft(buf_full, self.tau_max_low)

        # Run detection with the smaller (high-frequency) buffer
        buf_high = audio_buffer[:self.buffer_size_high].astype(np.float64)
        freq_high, conf_high = self._yin_fft(buf_high, self.tau_max_high)

        # Pick the result: use high buffer if it found a high frequency with
        # better or comparable confidence
        if (freq_high > HIGH_FREQ_CUTOFF and conf_high >= conf_low - 0.05):
            freq, confidence = freq_high, conf_high
        elif freq_low > 0:
            freq, confidence = freq_low, conf_low
        else:
            freq, confidence = freq_high, conf_high

        if freq <= 0 or confidence < CONFIDENCE_THRESHOLD:
            return None, 0, 0.0, 0.0, is_onset

        # Map to MIDI
        midi = freq_to_midi(freq)
        if midi < MIN_MIDI or midi > MAX_MIDI:
            return None, 0, 0.0, 0.0, is_onset

        name = midi_to_note_name(midi)
        return name, midi, freq, confidence, is_onset

    def detect_polyphonic(self, audio_buffer: np.ndarray, max_notes: int = 4):
        """Detect multiple simultaneous pitches using FFT peak analysis.

        Uses the FFT magnitude spectrum to find prominent peaks, then
        eliminates harmonics to isolate distinct fundamental frequencies.
        Requires peaks to be at least 15% of the strongest peak's magnitude
        to filter out spectral leakage and noise.

        Args:
            audio_buffer: Float32 mono audio, length >= buffer_size.
            max_notes: Maximum number of simultaneous notes to detect.

        Returns:
            List of (note_name, midi_number, frequency, confidence, is_onset)
            tuples. May be empty if silence detected. The first entry is
            always the strongest (most confident) pitch.
        """
        # Use up to 4096 samples for better frequency resolution on chords.
        # Falls back to buffer_size (2048) if less data is available.
        poly_size = min(len(audio_buffer), max(self.buffer_size, 4096))
        if poly_size < self.buffer_size:
            return []

        buf = audio_buffer[:poly_size].astype(np.float64)

        # RMS / onset
        rms = np.sqrt(np.mean(buf ** 2))
        is_onset = False
        if self._prev_rms > 0:
            if rms / self._prev_rms >= ONSET_THRESHOLD:
                is_onset = True
        elif rms > self.noise_floor:
            is_onset = True
        self._prev_rms = rms

        if rms < self.noise_floor:
            return []

        # --- FFT magnitude spectrum ---
        # Use the full buffer for polyphonic analysis. For close intervals
        # (e.g. A3 + C4, only 42 Hz apart), we need at least 4096 samples
        # at 44100 Hz for adequate frequency resolution (~10.8 Hz bins).
        # Zero-pad to at least 2x for interpolation accuracy.
        n = len(buf)
        window = np.hanning(n)
        windowed = buf * window

        fft_size = 1
        while fft_size < 4 * n:  # 4x for better interpolation
            fft_size *= 2

        spectrum = np.abs(np.fft.rfft(windowed, fft_size))
        freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)
        bin_width = freqs[1] - freqs[0]

        # Restrict to our frequency range
        min_bin = max(1, int(MIN_FREQ * fft_size / self.sample_rate))
        max_bin = min(len(spectrum) - 1,
                      int(MAX_FREQ * fft_size / self.sample_rate))

        # --- Find peaks with stricter criteria ---
        # Require a peak to dominate its neighborhood (not just immediate neighbors)
        neighborhood = max(2, int(15 / bin_width))  # ~15 Hz neighborhood
        peaks = []
        for i in range(min_bin + neighborhood, max_bin - neighborhood):
            lo = max(min_bin, i - neighborhood)
            hi = min(max_bin, i + neighborhood + 1)
            if spectrum[i] == np.max(spectrum[lo:hi]) and spectrum[i] > 0:
                # Parabolic interpolation
                alpha = spectrum[i - 1]
                beta = spectrum[i]
                gamma = spectrum[i + 1]
                denom = alpha - 2 * beta + gamma
                if abs(denom) > 1e-10:
                    p = 0.5 * (alpha - gamma) / denom
                else:
                    p = 0.0
                refined_freq = freqs[i] + p * bin_width
                magnitude = beta - 0.25 * (alpha - gamma) * p
                if refined_freq >= MIN_FREQ and refined_freq <= MAX_FREQ:
                    peaks.append((refined_freq, magnitude))

        if not peaks:
            return []

        # Sort by magnitude (strongest first)
        peaks.sort(key=lambda x: -x[1])

        # Minimum magnitude: must be at least 15% of the strongest peak
        max_mag = peaks[0][1]
        min_mag = max_mag * 0.15
        peaks = [(f, m) for f, m in peaks if m >= min_mag]

        # --- Harmonic elimination ---
        # For each candidate, check if it's a harmonic of any stronger peak.
        # Also check if it's a SUBharmonic (a weaker peak whose frequency is
        # a simple fraction of a stronger one — this handles cases where
        # spectral leakage creates phantom sub-octave peaks).
        tolerance = 0.035  # 3.5% frequency tolerance
        fundamentals = []

        for freq, mag in peaks:
            if len(fundamentals) >= max_notes:
                break

            is_harmonic = False
            for fund_freq, fund_mag in fundamentals:
                # Check if freq is a harmonic of fund_freq (2x, 3x, 4x...)
                for h in range(2, 8):
                    expected = fund_freq * h
                    if abs(freq - expected) / max(expected, 1) < tolerance:
                        is_harmonic = True
                        break
                if is_harmonic:
                    break

                # Check if freq is a subharmonic of fund_freq
                # (freq * h ≈ fund_freq) — this means freq is a phantom
                for h in range(2, 5):
                    expected = fund_freq / h
                    if abs(freq - expected) / max(freq, 1) < tolerance:
                        is_harmonic = True
                        break
                if is_harmonic:
                    break

            if is_harmonic:
                continue

            midi = freq_to_midi(freq)
            if MIN_MIDI <= midi <= MAX_MIDI:
                # Avoid duplicates (same MIDI note from slightly different peaks)
                if any(freq_to_midi(f) == midi for f, _ in fundamentals):
                    continue
                fundamentals.append((freq, mag))

        # Build result list
        results = []
        for freq, mag in fundamentals:
            midi = freq_to_midi(freq)
            name = midi_to_note_name(midi)
            confidence = min(1.0, mag / max_mag)
            results.append((name, midi, freq, confidence, is_onset))

        return results

    def measure_noise_floor(self, buffer: np.ndarray) -> float:
        """Measure the RMS of a quiet audio buffer for noise floor calibration.

        Args:
            buffer: Audio samples captured during a quiet period.

        Returns:
            RMS value suitable for use as noise_floor parameter.
        """
        buf = buffer.astype(np.float64)
        return float(np.sqrt(np.mean(buf ** 2)))

    def _yin_fft(self, buf: np.ndarray, tau_max: int):
        """Core YIN pitch detection using FFT-based difference function.

        The difference function d(tau) is computed as:
            d(tau) = sum_{j=0}^{W-tau-1} (x[j] - x[j+tau])^2
                   = r_x(0, tau) + r_x(tau, tau) - 2 * acf(tau)

        where acf(tau) = sum(x[j] * x[j+tau]) is computed via FFT for
        O(n log n) performance instead of O(n^2).

        Returns (frequency_hz, confidence) where confidence is 0.0..1.0.
        """
        n = len(buf)
        tau_min = self.tau_min
        tau_max = min(tau_max, n // 2)

        if tau_max <= tau_min:
            return 0.0, 0.0

        # --- Step 1: FFT-based difference function (fully vectorized) ---

        # Find next power of 2 for efficient FFT
        fft_size = 1
        while fft_size < 2 * n:
            fft_size *= 2

        # Autocorrelation via FFT: acf[tau] = sum(x[j] * x[j+tau])
        fft_buf = np.fft.rfft(buf, fft_size)
        acf = np.fft.irfft(fft_buf * np.conj(fft_buf), fft_size)[:tau_max + 1]

        # Energy terms: for each tau, we need:
        #   term1(tau) = sum_{j=0}^{n-tau-1} x[j]^2
        #   term2(tau) = sum_{j=tau}^{n-1} x[j]^2 = sum_{j=0}^{n-tau-1} x[j+tau]^2
        # Both equal sum(x[0:n-tau]^2) and sum(x[tau:n]^2)
        # Using cumulative sums for vectorized computation:
        buf_sq = buf ** 2
        cum_sq = np.cumsum(buf_sq)

        # term1[tau] = cum_sq[n-tau-1] = sum of x[0..n-tau-1]^2
        # term2[tau] = cum_sq[n-1] - cum_sq[tau-1] = sum of x[tau..n-1]^2
        taus = np.arange(tau_max + 1)

        # Vectorized energy term computation
        # term1[tau] = sum(x[0:n-tau]^2) for tau=0..tau_max
        term1 = np.empty(tau_max + 1, dtype=np.float64)
        term1[0] = cum_sq[n - 1]
        indices1 = n - taus[1:] - 1
        term1[1:] = cum_sq[indices1]

        # term2[tau] = sum(x[tau:n]^2) for tau=0..tau_max
        term2 = np.empty(tau_max + 1, dtype=np.float64)
        term2[0] = cum_sq[n - 1]
        term2[1:] = cum_sq[n - 1] - cum_sq[taus[1:] - 1]

        # Difference function: d(tau) = term1 + term2 - 2*acf(tau)
        diff = term1 + term2 - 2.0 * acf
        diff[0] = 0.0

        # Clamp small negative values from floating point errors
        np.maximum(diff, 0.0, out=diff)

        # --- Step 2: Cumulative mean normalized difference (CMNDF) ---
        cmndf = np.ones(tau_max + 1, dtype=np.float64)
        cum_diff = np.cumsum(diff[1:])
        # cmndf[tau] = diff[tau] * tau / sum(diff[1..tau])  for tau >= 1
        valid = cum_diff > 0
        tau_indices = np.arange(1, tau_max + 1)
        cmndf[1:] = np.where(valid,
                              diff[1:] * tau_indices / cum_diff,
                              1.0)

        # --- Step 3: Absolute threshold — find first dip below threshold ---
        threshold = CONFIDENCE_THRESHOLD
        tau_estimate = -1

        # Search in the valid range
        search_range = cmndf[tau_min:tau_max]
        below = np.where(search_range < threshold)[0]

        if len(below) > 0:
            # Start from the first value below threshold
            start = below[0] + tau_min
            # Walk forward to find the local minimum in this dip
            tau_estimate = start
            while (tau_estimate + 1 < tau_max and
                   cmndf[tau_estimate + 1] < cmndf[tau_estimate]):
                tau_estimate += 1
        else:
            # No dip below threshold: use global minimum
            tau_estimate = int(np.argmin(cmndf[tau_min:tau_max + 1])) + tau_min

        min_val = cmndf[tau_estimate]

        # --- Step 4: Parabolic interpolation for sub-sample accuracy ---
        if 0 < tau_estimate < tau_max:
            alpha = cmndf[tau_estimate - 1]
            beta = cmndf[tau_estimate]
            gamma = cmndf[tau_estimate + 1]
            denom = 2.0 * (2.0 * beta - alpha - gamma)
            if abs(denom) > 1e-10:
                adjustment = (alpha - gamma) / denom
                tau_refined = tau_estimate + adjustment
            else:
                tau_refined = float(tau_estimate)
        else:
            tau_refined = float(tau_estimate)

        if tau_refined <= 0:
            return 0.0, 0.0

        frequency = self.sample_rate / tau_refined
        confidence = 1.0 - min_val  # Lower cmndf = higher confidence

        return frequency, max(0.0, min(1.0, confidence))
