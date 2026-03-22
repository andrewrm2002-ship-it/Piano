"""Piano keyboard visualization at the bottom of the screen."""

import math
import time as _time
import pygame
from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, KEYBOARD_HEIGHT, HIGHWAY_WIDTH_RATIO,
    KEY_WHITE, KEY_WHITE_PRESSED, KEY_BLACK, KEY_BLACK_PRESSED,
    KEY_HIGHLIGHT, COLOR_BLACK, NOTE_NAMES, COLOR_WRONG_NOTE,
    midi_to_note_name,
)


# Which notes are black keys (relative to C)
BLACK_KEY_INDICES = {1, 3, 6, 8, 10}  # C#, D#, F#, G#, A#

# Animation durations (seconds)
_HIT_FLASH_DURATION = 0.25
_WRONG_FLASH_DURATION = 0.30
_NEXT_PULSE_SPEED = 4.0   # Hz for pulsing the next-expected key


def is_black_key(midi):
    return (midi % 12) in BLACK_KEY_INDICES


class KeyboardDisplay:
    """Draws a piano keyboard with hit flash, wrong-note indicator,
    and next-note pulse highlighting."""

    def __init__(self):
        self.highway_width = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        self.y_top = SCREEN_HEIGHT - KEYBOARD_HEIGHT
        self.key_rects = {}  # midi -> pygame.Rect
        self._setup = False

        # Animation state --------------------------------------------------
        # Hit flash: {midi: (start_real_time, color)}
        self._hit_flashes: dict[int, tuple[float, tuple]] = {}
        # Wrong note flash: {midi: start_real_time}
        self._wrong_flashes: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Song setup
    # ------------------------------------------------------------------

    def setup_for_song(self, song):
        """Configure which keys to show based on the song's notes."""
        unique_midis = song.unique_notes()
        if not unique_midis:
            return

        min_midi = (min(unique_midis) // 12) * 12
        max_midi = ((max(unique_midis) // 12) + 1) * 12

        white_keys = [m for m in range(min_midi, max_midi + 1)
                      if not is_black_key(m)]
        num_white = len(white_keys)
        if num_white == 0:
            return

        margin = 20
        usable = self.highway_width - 2 * margin
        white_width = min(40, max(15, usable // num_white))
        total_width = white_width * num_white
        start_x = margin + (usable - total_width) // 2

        self.key_rects = {}

        # Position white keys
        wx = start_x
        for m in range(min_midi, max_midi + 1):
            if not is_black_key(m):
                self.key_rects[m] = pygame.Rect(
                    wx, self.y_top + 5,
                    white_width - 2, KEYBOARD_HEIGHT - 10,
                )
                wx += white_width

        # Position black keys
        black_width = int(white_width * 0.6)
        black_height = int((KEYBOARD_HEIGHT - 10) * 0.6)
        for m in range(min_midi, max_midi + 1):
            if is_black_key(m):
                lower = m - 1
                upper = m + 1
                if lower in self.key_rects and upper in self.key_rects:
                    lx = self.key_rects[lower].right
                    rx = self.key_rects[upper].left
                    cx = (lx + rx) // 2
                elif lower in self.key_rects:
                    cx = self.key_rects[lower].right
                else:
                    continue
                self.key_rects[m] = pygame.Rect(
                    cx - black_width // 2, self.y_top + 5,
                    black_width, black_height,
                )

        self._setup = True
        self._hit_flashes.clear()
        self._wrong_flashes.clear()

    # ------------------------------------------------------------------
    # External triggers
    # ------------------------------------------------------------------

    def trigger_hit_flash(self, midi, color):
        """Call when a note is correctly hit. *color* is the judgment color."""
        self._hit_flashes[midi] = (_time.perf_counter(), color)

    def trigger_wrong_flash(self, midi):
        """Call when the player plays a wrong note."""
        self._wrong_flashes[midi] = _time.perf_counter()

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface, detected_note=None, target_note=None,
             song_unique_notes=None, show_key_labels=False,
             active_hold_midis=None):
        """Draw the keyboard with hit flash, wrong-note indicator,
        next-note pulse, and active hold glow.

        Args:
            surface: pygame Surface.
            detected_note: (name, midi) of currently detected note, or None.
            target_note: midi of the next expected note, or None (only set when close).
            show_key_labels: If True, show computer keyboard key names on keys.
            song_unique_notes: set of midi values used in the song.
            active_hold_midis: set of MIDI values currently being held (for hold glow).
        """
        if not self._setup:
            return

        now = _time.perf_counter()

        # Background
        bg_rect = pygame.Rect(0, self.y_top, self.highway_width, KEYBOARD_HEIGHT)
        pygame.draw.rect(surface, (20, 10, 35), bg_rect)

        detected_midi = detected_note[1] if detected_note else None
        song_midis = set(song_unique_notes) if song_unique_notes else set()

        # Draw white keys first, then black keys on top
        for midi, rect in sorted(self.key_rects.items(),
                                  key=lambda x: is_black_key(x[0])):
            black = is_black_key(midi)
            color = self._compute_key_color(
                midi, black, detected_midi, target_note, song_midis, now
            )

            border_radius = 2 if black else 3
            pygame.draw.rect(surface, color, rect, border_radius=border_radius)

            if not black:
                pygame.draw.rect(surface, (100, 100, 100), rect, 1,
                                 border_radius=3)

            # Overlay for hit flash (bright white blend that fades)
            flash_info = self._hit_flashes.get(midi)
            if flash_info:
                flash_start, flash_color = flash_info
                age = now - flash_start
                if age < _HIT_FLASH_DURATION:
                    t = age / _HIT_FLASH_DURATION
                    alpha = int(180 * (1.0 - t))
                    overlay = pygame.Surface(
                        (rect.width, rect.height), pygame.SRCALPHA
                    )
                    overlay.fill((*flash_color[:3], alpha))
                    surface.blit(overlay, rect.topleft)
                else:
                    del self._hit_flashes[midi]

            # Overlay for wrong-note flash (red tint)
            wrong_start = self._wrong_flashes.get(midi)
            if wrong_start is not None:
                age = now - wrong_start
                if age < _WRONG_FLASH_DURATION:
                    t = age / _WRONG_FLASH_DURATION
                    alpha = int(160 * (1.0 - t))
                    overlay = pygame.Surface(
                        (rect.width, rect.height), pygame.SRCALPHA
                    )
                    overlay.fill((*COLOR_WRONG_NOTE[:3], alpha))
                    surface.blit(overlay, rect.topleft)
                else:
                    del self._wrong_flashes[midi]

            # Active hold glow — pulsing glow while holding (color varies by key type)
            hold_midis = active_hold_midis or set()
            if midi in hold_midis:
                pulse = 0.6 + 0.4 * math.sin(now * 6)
                # Use different glow colors for contrast on white vs black keys
                if is_black_key(midi):
                    hold_color = (0, 255, 100)  # Green on black = visible
                    hold_alpha = int(100 * pulse)
                else:
                    hold_color = (0, 100, 200)  # Blue on white = visible
                    hold_alpha = int(140 * pulse)
                hold_overlay = pygame.Surface(
                    (rect.width, rect.height), pygame.SRCALPHA)
                hold_overlay.fill((*hold_color, hold_alpha))
                surface.blit(hold_overlay, rect.topleft)

        # Draw keyboard key labels (computer keyboard mapping)
        if show_key_labels:
            self._draw_key_labels(surface)

    # ------------------------------------------------------------------
    # Key labels
    # ------------------------------------------------------------------

    def _draw_key_labels(self, surface):
        """Draw computer keyboard key names on each piano key."""
        try:
            from piano_hero.input.keyboard_input import MIDI_TO_KEY_NAME
        except ImportError:
            return
        if not hasattr(self, '_label_font') or self._label_font is None:
            from piano_hero.ui.renderer import get_font
            self._label_font = get_font(11, bold=True)

        for midi, rect in self.key_rects.items():
            key_name = MIDI_TO_KEY_NAME.get(midi, '')
            if not key_name:
                continue
            black = is_black_key(midi)
            color = (180, 180, 180) if black else (100, 100, 120)
            text = self._label_font.render(key_name, True, color)
            text_rect = text.get_rect(
                centerx=rect.centerx,
                bottom=rect.bottom - 3,
            )
            surface.blit(text, text_rect)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_key_color(self, midi, black, detected_midi, target_note,
                           song_midis, now):
        """Determine the base color for a key, including the gentle
        next-note pulse."""
        # Currently pressed
        if midi == detected_midi:
            return KEY_BLACK_PRESSED if black else KEY_WHITE_PRESSED

        # Next expected note: gentle pulse
        if midi == target_note:
            pulse = 0.4 + 0.3 * math.sin(now * _NEXT_PULSE_SPEED * 2 * math.pi)
            base = KEY_BLACK if black else KEY_WHITE
            highlight = tuple(c // 2 for c in KEY_HIGHLIGHT) if black else KEY_HIGHLIGHT
            return tuple(
                int(b + (h - b) * pulse)
                for b, h in zip(base, highlight)
            )

        # Normal key
        if black:
            return KEY_BLACK
        if midi in song_midis:
            return KEY_WHITE
        return (200, 200, 200)
