"""Song audio preview - generates and plays short previews of songs."""
import numpy as np
import threading
import time

try:
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

from piano_hero.constants import midi_to_freq

class SongPreviewer:
    """Generates and plays short audio previews of songs."""

    def __init__(self):
        self._playing = False
        self._thread = None
        self._stop_flag = threading.Event()
        self._current_song = None
        self._cache = {}  # song_title -> audio array

    def preview(self, song, duration: float = 8.0):
        """Start playing a preview of the song (first N seconds)."""
        if not HAS_AUDIO:
            return
        if self._current_song == song.title:
            return  # Already playing this song

        self.stop()
        self._current_song = song.title
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._play_thread,
                                         args=(song, duration), daemon=True)
        self._thread.start()

    def stop(self):
        """Stop current preview."""
        self._stop_flag.set()
        self._current_song = None
        if self._thread and self._thread.is_alive():
            try:
                sd.stop()
            except:
                pass
            self._thread.join(timeout=0.5)
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    def _play_thread(self, song, duration):
        """Generate and play preview audio in background thread."""
        try:
            if song.title in self._cache:
                audio = self._cache[song.title]
            else:
                audio = self._generate_preview(song, duration)
                self._cache[song.title] = audio

            if self._stop_flag.is_set():
                return

            self._playing = True
            # Apply fade in/out
            fade_samples = int(0.1 * 44100)
            if len(audio) > fade_samples * 2:
                audio[:fade_samples] *= np.linspace(0, 1, fade_samples)
                audio[-fade_samples:] *= np.linspace(1, 0, fade_samples)

            sd.play(audio, samplerate=44100, blocking=False)

            # Wait for playback to finish or stop signal
            play_time = len(audio) / 44100
            start = time.time()
            while time.time() - start < play_time and not self._stop_flag.is_set():
                time.sleep(0.05)

            if self._stop_flag.is_set():
                sd.stop()

        except Exception:
            pass
        finally:
            self._playing = False

    def _generate_preview(self, song, duration: float) -> np.ndarray:
        """Generate audio preview using sine wave synthesis."""
        sr = 44100
        max_samples = int(duration * sr)
        audio = np.zeros(max_samples, dtype=np.float32)

        for note in song.notes:
            if note.start_time >= duration:
                break

            freq = midi_to_freq(note.midi)
            start_sample = int(note.start_time * sr)
            note_duration = min(note.end_time - note.start_time, duration - note.start_time)
            num_samples = int(note_duration * sr)

            if start_sample + num_samples > max_samples:
                num_samples = max_samples - start_sample
            if num_samples <= 0:
                continue

            t = np.arange(num_samples) / sr

            # Piano-like tone: fundamental + harmonics with decay
            wave = np.sin(2 * np.pi * freq * t) * 0.5
            wave += np.sin(2 * np.pi * freq * 2 * t) * 0.15
            wave += np.sin(2 * np.pi * freq * 3 * t) * 0.05

            # Exponential decay envelope
            decay = np.exp(-t * 3.0)
            # Attack
            attack_samples = min(int(0.01 * sr), num_samples)
            if attack_samples > 0:
                decay[:attack_samples] *= np.linspace(0, 1, attack_samples)

            wave *= decay * 0.3  # Master volume

            audio[start_sample:start_sample + num_samples] += wave[:num_samples]

        # Normalize
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.5

        return audio

    def clear_cache(self):
        """Clear the preview audio cache."""
        self._cache.clear()
