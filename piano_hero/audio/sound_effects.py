"""Sound effects system — synthesized hit/miss sounds and reference tone playback."""

import numpy as np
import pygame
from piano_hero.constants import (
    SAMPLE_RATE, SFX_HIT_FREQ, SFX_MISS_FREQ, SFX_PERFECT_FREQ,
    SFX_DURATION, SFX_VOLUME, midi_to_freq,
    PASSTHROUGH_VOLUME, PASSTHROUGH_DURATION,
)


def _make_tone(freq, duration=SFX_DURATION, volume=SFX_VOLUME,
               sample_rate=SAMPLE_RATE):
    """Generate a short sine wave tone as a pygame Sound object."""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, dtype=np.float32)
    # Sine wave with quick fade envelope
    envelope = np.minimum(1.0, np.minimum(t / 0.005, (duration - t) / 0.02))
    wave = (volume * np.sin(2 * np.pi * freq * t) * envelope).astype(np.float32)
    # Convert to 16-bit int for pygame
    wave_int = (wave * 32767).astype(np.int16)
    # Pygame needs stereo
    stereo = np.column_stack([wave_int, wave_int])
    return pygame.sndarray.make_sound(stereo)


def _make_noise_burst(duration=0.05, volume=0.15, sample_rate=SAMPLE_RATE):
    """Generate a short noise burst for miss sound."""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, dtype=np.float32)
    envelope = np.minimum(1.0, (duration - t) / duration)
    noise = np.random.randn(n_samples).astype(np.float32) * volume * envelope
    wave_int = (noise * 32767).astype(np.int16)
    stereo = np.column_stack([wave_int, wave_int])
    return pygame.sndarray.make_sound(stereo)


class SoundEffects:
    """Manages game sound effects."""

    def __init__(self):
        self._initialized = False
        self.enabled = True
        self._sounds = {}
        self._ref_channel = None

    def init(self):
        """Initialize sound effects. Must be called after pygame.mixer.init()."""
        if self._initialized:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2,
                                  buffer=512)
            self._sounds = {
                'perfect': _make_tone(SFX_PERFECT_FREQ, 0.1, 0.25),
                'good': _make_tone(SFX_HIT_FREQ, 0.08, 0.2),
                'ok': _make_tone(SFX_HIT_FREQ * 0.8, 0.06, 0.15),
                'miss': _make_noise_burst(0.08, 0.12),
                'combo': _make_tone(1760, 0.15, 0.3),
                'countdown': _make_tone(660, 0.1, 0.2),
                'go': _make_tone(880, 0.2, 0.25),
                'star': _make_tone(1320, 0.12, 0.2),
            }
            # Reserve a channel for reference tones
            pygame.mixer.set_num_channels(8)
            self._ref_channel = pygame.mixer.Channel(7)
            self._initialized = True
        except Exception as e:
            print(f"Sound effects init failed: {e}")
            self.enabled = False

    def play(self, name: str):
        """Play a named sound effect."""
        if not self.enabled or not self._initialized:
            return
        sound = self._sounds.get(name)
        if sound:
            sound.play()

    def play_judgment(self, judgment: str):
        """Play the appropriate sound for a judgment."""
        self.play(judgment)

    def play_reference_tone(self, midi: int, duration: float = 0.3):
        """Play a reference tone for a given MIDI note (for practice/preview)."""
        if not self.enabled or not self._initialized:
            return
        try:
            freq = midi_to_freq(midi)
            tone = _make_tone(freq, duration, 0.2)
            if self._ref_channel:
                self._ref_channel.play(tone)
        except Exception:
            pass

    def stop_reference(self):
        """Stop any playing reference tone."""
        if self._ref_channel:
            self._ref_channel.stop()

    # ── Audio Passthrough ────────────────────────────────────────────────────

    def play_note(self, midi: int):
        """Play a synthesized tone for the detected/pressed note.

        Used for audio passthrough so the player hears what they're
        playing through the computer speakers (especially useful with
        computer keyboard input where there's no physical keyboard sound).
        """
        if not self.enabled or not self._initialized:
            return
        try:
            freq = midi_to_freq(midi)
            # Piano-like envelope: quick attack, medium sustain, gradual release
            duration = PASSTHROUGH_DURATION
            n_samples = int(SAMPLE_RATE * duration)
            t = np.linspace(0, duration, n_samples, dtype=np.float32)

            # ADSR-ish envelope
            attack = 0.005
            decay = 0.05
            sustain_level = 0.6
            env = np.where(t < attack, t / attack,
                    np.where(t < attack + decay,
                             1.0 - (1.0 - sustain_level) * (t - attack) / decay,
                             sustain_level * (1.0 - (t - attack - decay) /
                                              (duration - attack - decay))))
            env = np.maximum(env, 0).astype(np.float32)

            # Mix fundamental + soft 2nd harmonic for richer tone
            wave = (PASSTHROUGH_VOLUME * env * (
                0.8 * np.sin(2 * np.pi * freq * t) +
                0.2 * np.sin(2 * np.pi * freq * 2 * t)
            )).astype(np.float32)

            wave_int = (wave * 32767).astype(np.int16)
            stereo = np.column_stack([wave_int, wave_int])
            sound = pygame.sndarray.make_sound(stereo)

            if self._ref_channel:
                self._ref_channel.play(sound)
        except Exception:
            pass

    def stop_note(self):
        """Stop any playing passthrough note."""
        if self._ref_channel:
            self._ref_channel.stop()
