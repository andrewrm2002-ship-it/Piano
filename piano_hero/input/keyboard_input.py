"""Computer keyboard input — maps keyboard keys to piano notes.

Piano-style layout with H = Middle C (C4):

  White keys on the home row (left to right):
    A   S   D   F   G   H   J   K   L   ;   '
    E3  F3  G3  A3  B3  C4  D4  E4  F4  G4  A4

  Black keys on the QWERTY row above (positioned between white keys):
        W   E   R           Y   U           O   P   [
        F#3 G#3 A#3         C#4 D#4         F#4 G#4 A#4

  Upper white keys on the bottom row (continuing right):
    Z   X   C   V   B   N   M
    B4  C5  D5  E5  F5  G5  A5

  Upper black keys on the number row:
                    8   9           -   =
                    C#5 D#5         F#5 G#5

  (No black key between B-C or E-F, matching a real piano.)

This module pushes note events into the same pitch_queue used by the
audio engine, so the game session doesn't need any changes.
"""

import time
import queue
import pygame
from piano_hero.constants import midi_to_note_name, midi_to_freq


# ── Key-to-MIDI mapping ─────────────────────────────────────────────────────

CHROMATIC_MAP = {}

# --- Home row: white keys (E3 through A4) ---
_WHITE_HOME = [
    (pygame.K_a, 52),          # E3
    (pygame.K_s, 53),          # F3
    (pygame.K_d, 55),          # G3
    (pygame.K_f, 57),          # A3
    (pygame.K_g, 59),          # B3
    (pygame.K_h, 60),          # C4  ← Middle C
    (pygame.K_j, 62),          # D4
    (pygame.K_k, 64),          # E4
    (pygame.K_l, 65),          # F4
    (pygame.K_SEMICOLON, 67),  # G4
    (pygame.K_QUOTE, 69),      # A4
]

# --- QWERTY row: black keys for home-row octave ---
_BLACK_QWERTY = [
    # No black key between E3(A) and F3(S) — E-F is a natural half step
    (pygame.K_w, 54),          # F#3  (between S=F3 and D=G3)
    (pygame.K_e, 56),          # G#3  (between D=G3 and F=A3)
    (pygame.K_r, 58),          # A#3  (between F=A3 and G=B3)
    # No black key between B3(G) and C4(H) — B-C is a natural half step
    (pygame.K_y, 61),          # C#4  (between H=C4 and J=D4)
    (pygame.K_u, 63),          # D#4  (between J=D4 and K=E4)
    # No black key between E4(K) and F4(L) — E-F is a natural half step
    (pygame.K_o, 66),          # F#4  (between L=F4 and ;=G4)
    (pygame.K_p, 68),          # G#4  (between ;=G4 and '=A4)
    (pygame.K_LEFTBRACKET, 70),  # A#4 (between '=A4 and Z=B4)
]

# --- Bottom row: white keys upper octave (B4 through A5) ---
_WHITE_BOTTOM = [
    (pygame.K_z, 71),          # B4
    (pygame.K_x, 72),          # C5
    (pygame.K_c, 74),          # D5
    (pygame.K_v, 76),          # E5
    (pygame.K_b, 77),          # F5
    (pygame.K_n, 79),          # G5
    (pygame.K_m, 81),          # A5
]

# --- Number row: black keys for bottom-row octave ---
_BLACK_NUMBER = [
    # No black key between B4(Z) and C5(X) — B-C is a natural half step
    (pygame.K_8, 73),          # C#5  (between X=C5 and C=D5)
    (pygame.K_9, 75),          # D#5  (between C=D5 and V=E5)
    # No black key between E5(V) and F5(B) — E-F is a natural half step
    (pygame.K_MINUS, 78),      # F#5  (between B=F5 and N=G5)
    (pygame.K_EQUALS, 80),     # G#5  (between N=G5 and M=A5)
]

# Build the combined map
for key, midi in _WHITE_HOME + _BLACK_QWERTY + _WHITE_BOTTOM + _BLACK_NUMBER:
    CHROMATIC_MAP[key] = midi


# ── Yamaha Keyboard Game Controls ────────────────────────────────────────────
# Far-left keys (C2-B2, MIDI 36-47) are unused by all 65 songs.
# Map them to game actions so players never need to leave the keyboard.
YAMAHA_CONTROLS = {
    36: 'restart',       # C2  = Restart current song
    38: 'next_song',     # D2  = Next song in list
    40: 'prev_song',     # E2  = Previous song
    41: 'pause',         # F2  = Pause / Resume
    43: 'star_power',    # G2  = Activate Star Power
    45: 'speed_toggle',  # A2  = Cycle practice speed (50/75/100%)
    47: 'back_to_menu',  # B2  = Return to song select
    # Far-right keys (A#5-C6, MIDI 82-84) also unused:
    82: 'wait_toggle',   # A#5 = Toggle wait mode
    83: 'names_toggle',  # B5  = Toggle note name display
    84: 'speed_toggle',  # C6  = Cycle practice speed
}


# ── Reverse map for display labels ──────────────────────────────────────────

_KEY_NAMES = {
    pygame.K_a: 'A', pygame.K_b: 'B', pygame.K_c: 'C', pygame.K_d: 'D',
    pygame.K_e: 'E', pygame.K_f: 'F', pygame.K_g: 'G', pygame.K_h: 'H',
    pygame.K_i: 'I', pygame.K_j: 'J', pygame.K_k: 'K', pygame.K_l: 'L',
    pygame.K_m: 'M', pygame.K_n: 'N', pygame.K_o: 'O', pygame.K_p: 'P',
    pygame.K_q: 'Q', pygame.K_r: 'R', pygame.K_s: 'S', pygame.K_t: 'T',
    pygame.K_u: 'U', pygame.K_v: 'V', pygame.K_w: 'W', pygame.K_x: 'X',
    pygame.K_y: 'Y', pygame.K_z: 'Z',
    pygame.K_SEMICOLON: ';', pygame.K_QUOTE: "'",
    pygame.K_COMMA: ',', pygame.K_PERIOD: '.', pygame.K_SLASH: '/',
    pygame.K_LEFTBRACKET: '[', pygame.K_RIGHTBRACKET: ']',
    pygame.K_1: '1', pygame.K_2: '2', pygame.K_3: '3', pygame.K_4: '4',
    pygame.K_5: '5', pygame.K_6: '6', pygame.K_7: '7', pygame.K_8: '8',
    pygame.K_9: '9', pygame.K_0: '0', pygame.K_MINUS: '-', pygame.K_EQUALS: '=',
}

MIDI_TO_KEY_NAME = {}
for pg_key, midi in CHROMATIC_MAP.items():
    if pg_key in _KEY_NAMES:
        MIDI_TO_KEY_NAME[midi] = _KEY_NAMES[pg_key]


# ── Input handler ────────────────────────────────────────────────────────────

class KeyboardNoteInput:
    """Translates computer keyboard events into note detections,
    pushing them into the same pitch_queue used by the audio engine."""

    def __init__(self, pitch_queue: queue.Queue):
        self.pitch_queue = pitch_queue
        self.enabled = True
        self._pressed_keys = set()

    def handle_event(self, event) -> bool:
        """Process a pygame event. Returns True if a note was triggered."""
        if not self.enabled:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key in CHROMATIC_MAP and event.key not in self._pressed_keys:
                self._pressed_keys.add(event.key)
                midi = CHROMATIC_MAP[event.key]
                name = midi_to_note_name(midi)
                freq = midi_to_freq(midi)
                timestamp = time.perf_counter()
                try:
                    self.pitch_queue.put_nowait(
                        (name, midi, freq, 1.0, True, timestamp))
                except queue.Full:
                    try:
                        self.pitch_queue.get_nowait()
                        self.pitch_queue.put_nowait(
                            (name, midi, freq, 1.0, True, timestamp))
                    except (queue.Empty, queue.Full):
                        pass
                return True

        elif event.type == pygame.KEYUP:
            self._pressed_keys.discard(event.key)

        return False

    @staticmethod
    def get_yamaha_action(midi: int) -> str:
        """Check if a MIDI note corresponds to a Yamaha control key.
        Returns action name or empty string."""
        return YAMAHA_CONTROLS.get(midi, '')

    def get_key_for_midi(self, midi: int) -> str:
        """Return the keyboard key name for a given MIDI note, or ''."""
        return MIDI_TO_KEY_NAME.get(midi, '')
