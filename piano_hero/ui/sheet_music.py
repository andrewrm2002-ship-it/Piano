"""Traditional sheet music overlay for Piano Hero.

Renders a compact treble+bass clef staff at the top of the highway area with
scrolling notes, accidentals, finger number hints, and a cursor line.
"""

import pygame
import math
from piano_hero.constants import *
from piano_hero.ui.renderer import get_font


# ── Staff layout constants ──────────────────────────────────────────────────

# Vertical spacing between staff lines (pixels).  Scaled in setup relative to
# the drawing rect, but we keep a reference value for calculations.
_BASE_LINE_SPACING = 8

# Measures of context shown in the viewport.
_MEASURES_AHEAD = 2
_MEASURES_BEHIND = 1

# Colors used exclusively within the sheet music overlay.
_STAFF_LINE_COLOR = (180, 180, 180)
_BG_COLOR = (15, 10, 25, 200)           # Semi-transparent dark
_CURSOR_COLOR = (0, 230, 255)           # Bright cyan
_NOTE_CURRENT_COLOR = (0, 230, 255)     # Bright cyan
_NOTE_UPCOMING_COLOR = (255, 255, 255)  # White
_NOTE_PAST_COLOR = (90, 90, 100)        # Dimmed gray
_ACCIDENTAL_COLOR = (220, 220, 220)
_FINGER_RH_COLOR = (255, 165, 0)       # Orange – right hand
_FINGER_LH_COLOR = (80, 160, 255)      # Blue – left hand
_NOTENAME_COLOR = (160, 160, 170)
_LEDGER_COLOR = (150, 150, 150)

# ── Chromatic‑to‑staff mapping ──────────────────────────────────────────────

# Pitch class (0‑11) → (staff_offset_within_octave, accidental)
# Staff offset 0 = C of the octave; each +1 is one diatonic step up.
# accidental: 0 = natural, 1 = sharp, -1 = flat
_PITCH_CLASS_MAP = {
    0:  (0, 0),    # C
    1:  (0, 1),    # C#
    2:  (1, 0),    # D
    3:  (1, 1),    # D#  (Eb → show as D#)
    4:  (2, 0),    # E
    5:  (3, 0),    # F
    6:  (3, 1),    # F#
    7:  (4, 0),    # G
    8:  (4, 1),    # G#
    9:  (5, 0),    # A
    10: (5, 1),    # A#
    11: (6, 0),    # B
}

# Number of diatonic steps per octave.
_DIATONIC_STEPS = 7


def _midi_to_staff_position(midi):
    """Return (staff_pos, accidental) for a MIDI note number.

    ``staff_pos`` is measured in *half‑line‑spacings* (i.e. the distance
    between two adjacent staff positions) relative to **middle C (MIDI 60)**
    which is defined as position 0.  Positive = higher pitch (upward on the
    staff).  ``accidental`` is 0, 1 (sharp), or -1 (flat).
    """
    octave = (midi // 12) - 1   # MIDI 60 → octave 4
    pitch_class = midi % 12
    step_in_octave, accidental = _PITCH_CLASS_MAP[pitch_class]
    # Diatonic step relative to C0 (MIDI 12, octave 0)
    diatonic_abs = (octave * _DIATONIC_STEPS) + step_in_octave
    # Middle‑C (MIDI 60) is C4 → octave 4, step 0 → abs = 28
    middle_c_abs = 4 * _DIATONIC_STEPS  # 28
    staff_pos = diatonic_abs - middle_c_abs
    return staff_pos, accidental


def _auto_finger(midi):
    """Return an approximate finger number (1‑5) for beginners.

    Right hand (MIDI >= 60 / treble clef): cycle 1‑5 ascending.
    Left hand (MIDI < 60 / bass clef): cycle 5‑1 ascending.
    """
    pitch_class = midi % 12
    # Map pitch class to a diatonic index (white keys only for cycling)
    step_in_oct, _acc = _PITCH_CLASS_MAP[pitch_class]
    octave = (midi // 12) - 1
    diatonic_abs = octave * _DIATONIC_STEPS + step_in_oct

    if midi >= 60:
        # Right hand: C4=1, D4=2 … G4=5, A4=1, …
        offset = diatonic_abs - 4 * _DIATONIC_STEPS  # relative to C4
        return (offset % 5) + 1
    else:
        # Left hand: C3=5, D3=4, E3=3, F3=2, G3=1, A3=5, …
        offset = diatonic_abs - 3 * _DIATONIC_STEPS  # relative to C3
        return 5 - (offset % 5)


# ── Font cache ──────────────────────────────────────────────────────────────

_font_cache = {}


def _get_cached_font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = get_font(size, bold=bold)
    return _font_cache[key]


# ── SheetMusicOverlay ───────────────────────────────────────────────────────

class SheetMusicOverlay:
    """Renders a scrolling traditional‑notation overlay on top of the highway.

    Usage::

        overlay = SheetMusicOverlay()
        overlay.setup_for_song(song)
        # In the game loop:
        overlay.draw(screen, rect, current_beat, song.notes)
    """

    def __init__(self):
        self.visible = True
        self._song = None
        self._beats_per_measure = 4
        self._note_cache = []         # Pre‑computed per‑note layout data
        self._bg_surface = None       # Cached background with staff lines
        self._bg_rect = None          # Rect the cache was built for

    # ── public API ──────────────────────────────────────────────────────

    def setup_for_song(self, song):
        """Prepare internal caches for *song*."""
        self._song = song
        self._beats_per_measure = song.time_signature[0] if song.time_signature else 4
        self._note_cache = []
        self._bg_surface = None  # Invalidate

        for note in song.notes:
            staff_pos, accidental = _midi_to_staff_position(note.midi)
            finger = getattr(note, "finger", None)
            if finger is None:
                finger = _auto_finger(note.midi)
            is_right_hand = note.midi >= 60
            note_name = midi_to_note_name(note.midi)
            self._note_cache.append({
                "beat": note.start_beat,
                "duration": note.duration_beat,
                "staff_pos": staff_pos,
                "accidental": accidental,
                "finger": finger,
                "is_rh": is_right_hand,
                "name": note_name,
                "midi": note.midi,
                "note_ref": note,
            })

    def set_visible(self, visible: bool):
        self.visible = visible

    def draw(self, surface, rect, current_beat, notes):
        """Render the sheet music overlay into *rect* on *surface*.

        Args:
            surface: The main pygame display surface.
            rect: ``pygame.Rect`` defining the overlay area.
            current_beat: Current playback position in beats.
            notes: The song's note list (used for hit‑state lookups).
        """
        if not self.visible or not self._note_cache:
            return

        # Rebuild background cache when rect changes.
        if self._bg_surface is None or self._bg_rect != rect:
            self._build_bg(rect)
            self._bg_rect = rect

        # Blit cached background (staff lines, clefs).
        surface.blit(self._bg_surface, rect.topleft)

        # Compute layout metrics.
        ls = self._line_spacing(rect)
        treble_bottom_y = self._treble_bottom_y(rect, ls)
        bass_top_y = self._bass_top_y(rect, ls)

        # Beat range visible.
        beats_ahead = _MEASURES_AHEAD * self._beats_per_measure
        beats_behind = _MEASURES_BEHIND * self._beats_per_measure
        beat_lo = current_beat - beats_behind
        beat_hi = current_beat + beats_ahead
        total_beats = beats_ahead + beats_behind

        # Cursor x‑position (where current_beat is rendered).
        cursor_frac = beats_behind / total_beats
        cursor_x = rect.x + int(cursor_frac * rect.width)

        # Draw cursor line.
        pygame.draw.line(
            surface, _CURSOR_COLOR,
            (cursor_x, rect.y + 2),
            (cursor_x, rect.y + rect.height - 2),
            2,
        )

        # Pixels per beat.
        px_per_beat = rect.width / total_beats if total_beats else 1

        # Fonts.
        name_font = _get_cached_font(max(9, ls - 2))
        finger_font = _get_cached_font(max(9, ls - 1), bold=True)
        acc_font = _get_cached_font(max(10, ls + 2), bold=True)

        # Draw visible notes.
        for nc in self._note_cache:
            beat = nc["beat"]
            if beat + nc["duration"] < beat_lo or beat > beat_hi:
                continue

            # Horizontal position.
            x = rect.x + int((beat - beat_lo) * px_per_beat)

            # Vertical position on staff.
            y = self._staff_pos_to_y(
                nc["staff_pos"], rect, ls, treble_bottom_y, bass_top_y
            )

            # Determine colour based on timing state.
            note_ref = nc["note_ref"]
            if note_ref.hit:
                color = _NOTE_PAST_COLOR
            elif abs(beat - current_beat) < 0.05:
                color = _NOTE_CURRENT_COLOR
            elif beat < current_beat:
                color = _NOTE_PAST_COLOR
            else:
                color = _NOTE_UPCOMING_COLOR

            # Draw ledger lines if needed.
            self._draw_ledger_lines(surface, x, y, nc["staff_pos"],
                                    rect, ls, treble_bottom_y, bass_top_y)

            # Draw accidental.
            if nc["accidental"] != 0:
                acc_char = "#" if nc["accidental"] == 1 else "b"
                acc_surf = acc_font.render(acc_char, True, _ACCIDENTAL_COLOR)
                surface.blit(acc_surf,
                             (x - acc_surf.get_width() - 2,
                              y - acc_surf.get_height() // 2))

            # Draw notehead and stem.
            self._draw_note(surface, x, y, nc["duration"], color, ls)

            # Finger number hint.
            finger = nc["finger"]
            if finger is not None:
                fc = _FINGER_RH_COLOR if nc["is_rh"] else _FINGER_LH_COLOR
                circle_r = max(6, ls // 2)
                circle_y = y - ls - circle_r - 1
                pygame.draw.circle(surface, fc, (x, circle_y), circle_r)
                pygame.draw.circle(surface, (0, 0, 0), (x, circle_y), circle_r, 1)
                ftxt = finger_font.render(str(finger), True, (255, 255, 255))
                surface.blit(ftxt, (x - ftxt.get_width() // 2,
                                    circle_y - ftxt.get_height() // 2))

            # Note name label.
            ntxt = name_font.render(nc["name"], True, _NOTENAME_COLOR)
            surface.blit(ntxt, (x - ntxt.get_width() // 2,
                                y + ls))

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _line_spacing(rect):
        """Compute the staff line spacing for a given rect height."""
        # Two 5‑line staves (4 gaps each) + gap between them ≈ 12 gaps.
        # Reserve ~20% top/bottom padding.
        usable = rect.height * 0.75
        spacing = max(5, int(usable / 12))
        return spacing

    @staticmethod
    def _treble_bottom_y(rect, ls):
        """Y coordinate of the lowest line of the treble staff."""
        # Treble staff sits in the upper portion.
        return rect.y + int(rect.height * 0.12) + 4 * ls

    @staticmethod
    def _bass_top_y(rect, ls):
        """Y coordinate of the highest line of the bass staff."""
        # Bass staff sits below the treble with a gap.
        treble_bottom = rect.y + int(rect.height * 0.12) + 4 * ls
        gap = max(ls * 2, 14)
        return treble_bottom + gap

    def _staff_pos_to_y(self, staff_pos, rect, ls, treble_bottom_y, bass_top_y):
        """Convert a staff position to a pixel Y coordinate.

        ``staff_pos`` is in diatonic steps relative to middle C (pos 0).
        Middle C sits on one ledger line below the treble staff, which is the
        space between the two staves.
        """
        half = ls / 2.0  # Half a staff space

        # Middle C (pos 0) is one ledger line below treble staff.
        # Treble bottom line = E4 (staff_pos 2).
        # So treble bottom Y corresponds to staff_pos 2.
        # Each +1 in staff_pos moves up by half a line spacing.
        # Y decreases as pitch goes up.

        # Reference: treble bottom line = staff_pos 2 → y = treble_bottom_y
        # But we also need bass staff.  The bass top line = A3 (staff_pos -2 from
        # middle-C perspective: A is 2 diatonic steps below C, but in the
        # previous octave it is actually further.  Let's be precise.)

        # Treble staff bottom line (E4): staff_pos = 2
        # Bass staff top line (A3): staff_pos = -3  (C4=0, B3=-1, A3=-2 ... wait
        # let's re‑derive.)

        # C4 = 0, B3 = -1, A3 = -2, G3 = -3, F3 = -4, E3 = -5, D3 = -6, C3 = -7
        # Standard bass clef: top line = A3, bottom line = G2
        # A3 = staff_pos -2, G2 = staff_pos -2 -  ... actually let's just count:
        # A3 = -2?  C4=0 → B3=-1, A3=-2.  Yes.
        # Bass top line A3 = -2
        # Bass lines: A3, F3, D3, B2, G2 → positions: -2, -4, -6, -8, -10

        # For positions >= -1 (middle‑C and above), anchor to treble staff.
        # For positions <= -2, anchor to bass staff.

        if staff_pos >= -1:
            # Treble clef region.  Treble bottom line (E4) = pos 2.
            ref_y = treble_bottom_y
            ref_pos = 2
            return ref_y - int((staff_pos - ref_pos) * half)
        else:
            # Bass clef region.  Bass top line (A3) = pos -2.
            ref_y = bass_top_y
            ref_pos = -2
            return ref_y - int((staff_pos - ref_pos) * half)

    def _build_bg(self, rect):
        """Build a cached background surface with staff lines and clefs."""
        self._bg_surface = pygame.Surface(
            (rect.width, rect.height), pygame.SRCALPHA
        )
        # Semi-transparent background.
        self._bg_surface.fill(_BG_COLOR)

        ls = self._line_spacing(rect)

        # -- Treble staff (5 lines) --
        treble_bottom = self._treble_bottom_y(rect, ls) - rect.y
        for i in range(5):
            y = treble_bottom - i * ls
            pygame.draw.line(
                self._bg_surface, _STAFF_LINE_COLOR,
                (10, y), (rect.width - 10, y), 1,
            )

        # -- Bass staff (5 lines) --
        bass_top = self._bass_top_y(rect, ls) - rect.y
        for i in range(5):
            y = bass_top + i * ls
            pygame.draw.line(
                self._bg_surface, _STAFF_LINE_COLOR,
                (10, y), (rect.width - 10, y), 1,
            )

        # -- Clef symbols (text placeholders) --
        clef_font = _get_cached_font(max(12, ls * 3), bold=True)

        treble_top = treble_bottom - 4 * ls
        tc_surf = clef_font.render("G", True, (200, 200, 210))
        self._bg_surface.blit(
            tc_surf,
            (14, treble_top + ls - tc_surf.get_height() // 2 + ls),
        )

        bc_surf = clef_font.render("F", True, (200, 200, 210))
        self._bg_surface.blit(
            bc_surf,
            (14, bass_top - bc_surf.get_height() // 2 + ls),
        )

    def _draw_ledger_lines(self, surface, x, y, staff_pos,
                           rect, ls, treble_bottom_y, bass_top_y):
        """Draw short ledger lines for notes above/below each staff."""
        half = ls / 2.0
        ledger_hw = ls + 4  # Half‑width of ledger line

        # Treble staff: lines at positions 2,4,6,8,10 → bottom to top.
        # Notes at pos 0 (middle C) and pos 1 need a ledger at pos 0.
        # Notes above top line (pos 10) need ledgers at 12, 14, …

        treble_top_pos = 10   # Top line of treble staff (F5)
        treble_bottom_pos = 2 # Bottom line (E4)
        bass_top_pos = -2     # Top line of bass staff (A3)
        bass_bottom_pos = -10 # Bottom line (G2)

        # Ledger lines below treble staff (even positions from 0 down to
        # whatever is needed, but only to bass_top_pos + something).
        if staff_pos >= -1:
            # In treble region
            if staff_pos < treble_bottom_pos:
                pos = treble_bottom_pos - 2
                while pos >= staff_pos - (staff_pos % 2):
                    # Only draw at even positions (on lines)
                    ly = treble_bottom_y + int((treble_bottom_pos - pos) * half)
                    if pos % 2 == 0:
                        pygame.draw.line(
                            surface, _LEDGER_COLOR,
                            (x - ledger_hw, ly), (x + ledger_hw, ly), 1,
                        )
                    pos -= 2
                # Middle C special: always at pos 0 if needed
                if staff_pos <= 0:
                    ly = treble_bottom_y + int((treble_bottom_pos - 0) * half)
                    pygame.draw.line(
                        surface, _LEDGER_COLOR,
                        (x - ledger_hw, ly), (x + ledger_hw, ly), 1,
                    )
            elif staff_pos > treble_top_pos:
                pos = treble_top_pos + 2
                while pos <= staff_pos + (staff_pos % 2):
                    treble_top_y = treble_bottom_y - 4 * ls
                    ly = treble_top_y - int((pos - treble_top_pos) * half)
                    if pos % 2 == 0:
                        pygame.draw.line(
                            surface, _LEDGER_COLOR,
                            (x - ledger_hw, ly), (x + ledger_hw, ly), 1,
                        )
                    pos += 2
        else:
            # In bass region
            if staff_pos < bass_bottom_pos:
                pos = bass_bottom_pos - 2
                bass_bottom_y = bass_top_y + 4 * ls
                while pos >= staff_pos - (1 if staff_pos % 2 != 0 else 0):
                    ly = bass_bottom_y + int((bass_bottom_pos - pos) * half)
                    if pos % 2 == 0:
                        pygame.draw.line(
                            surface, _LEDGER_COLOR,
                            (x - ledger_hw, ly), (x + ledger_hw, ly), 1,
                        )
                    pos -= 2
            elif staff_pos > bass_top_pos:
                pos = bass_top_pos + 2
                while pos <= staff_pos + (1 if staff_pos % 2 != 0 else 0):
                    ly = bass_top_y - int((pos - bass_top_pos) * half)
                    if pos % 2 == 0:
                        pygame.draw.line(
                            surface, _LEDGER_COLOR,
                            (x - ledger_hw, ly), (x + ledger_hw, ly), 1,
                        )
                    pos += 2

    @staticmethod
    def _draw_note(surface, x, y, duration, color, ls):
        """Draw a notehead (and optional stem/flag) at (x, y).

        Duration mapping:
            >= 4.0  → whole note (open, no stem)
            >= 2.0  → half note (open + stem)
            >= 1.0  → quarter note (filled + stem)
            < 1.0   → eighth note (filled + stem + flag)
        """
        r = max(3, int(ls * 0.55))  # Notehead radius

        if duration >= 4.0:
            # Whole note: open oval, no stem.
            pygame.draw.ellipse(
                surface, color,
                (x - r - 1, y - r + 1, (r + 1) * 2, (r - 1) * 2), 2,
            )
        elif duration >= 2.0:
            # Half note: open oval + stem.
            pygame.draw.ellipse(
                surface, color,
                (x - r, y - r + 1, r * 2, (r - 1) * 2), 2,
            )
            stem_h = ls * 3
            pygame.draw.line(
                surface, color,
                (x + r - 1, y), (x + r - 1, y - stem_h), 2,
            )
        elif duration >= 1.0:
            # Quarter note: filled oval + stem.
            pygame.draw.ellipse(
                surface, color,
                (x - r, y - r + 1, r * 2, (r - 1) * 2),
            )
            stem_h = ls * 3
            pygame.draw.line(
                surface, color,
                (x + r - 1, y), (x + r - 1, y - stem_h), 2,
            )
        else:
            # Eighth note: filled oval + stem + flag.
            pygame.draw.ellipse(
                surface, color,
                (x - r, y - r + 1, r * 2, (r - 1) * 2),
            )
            stem_h = ls * 3
            stem_top_x = x + r - 1
            stem_top_y = y - stem_h
            pygame.draw.line(
                surface, color,
                (stem_top_x, y), (stem_top_x, stem_top_y), 2,
            )
            # Flag: a small curved line from stem top.
            flag_pts = [
                (stem_top_x, stem_top_y),
                (stem_top_x + r, stem_top_y + ls),
                (stem_top_x + r // 2, stem_top_y + ls * 2),
            ]
            if len(flag_pts) >= 2:
                pygame.draw.lines(surface, color, False, flag_pts, 2)
