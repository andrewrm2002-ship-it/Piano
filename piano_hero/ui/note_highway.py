"""Synthesia-style scrolling 3-D perspective note highway.

Notes are rendered as tall rectangles whose height equals their duration in
pixels.  A whole note at 100 BPM is a tall pillar; an eighth note is a short
block.  There is no separate "trail" -- the block itself IS the visual
representation of the hold duration.

Includes: prominent NOW zone, HOLD labels, release markers, hold progress,
Star Power visuals, beat grid, approach glow, and hit/miss animations.
"""

import time as _time
import math
import pygame
from dataclasses import dataclass
from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, HIGHWAY_WIDTH_RATIO, KEYBOARD_HEIGHT,
    HIT_LINE_Y_RATIO, PREVIEW_BEATS, OCTAVE_COLORS, DEFAULT_NOTE_COLOR,
    HIT_LINE_COLOR, COLOR_PERFECT, COLOR_GOOD, COLOR_OK, COLOR_MISS,
    COLOR_DARK_GRAY, COLOR_WHITE, COLOR_BLACK, BG_COLOR,
    PERFECT_POINTS, GOOD_POINTS, OK_POINTS, COLOR_ACCENT,
    COLOR_EARLY, COLOR_LATE,
)
from piano_hero.ui.renderer import get_font, lerp_color


# ---------------------------------------------------------------------------
# Data classes for post-hit animations
# ---------------------------------------------------------------------------

@dataclass
class NoteAnimation:
    """Tracks a per-note animation after hit/miss."""
    note: object            # The original Note object
    start_time: float       # perf_counter when animation started
    anim_type: str          # "hit_perfect", "hit_good", "hit_ok", "miss"
    x: int
    y: int
    points: int = 0
    early_late: str = ""    # "early", "late", or "" for perfect


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HIT_ANIM_DURATION = 0.30     # seconds for hit shrink+fade
_MISS_ANIM_DURATION = 0.50    # seconds for miss fall-away
_POPUP_DURATION = 0.60        # seconds for score popup float
_POPUP_RISE = 60              # pixels the popup text rises
_APPROACH_GLOW_BEATS = 2.0    # glow starts this many beats before hit line
_MIN_NOTE_HEIGHT = 12         # minimum rendered height for very short notes

# NOW zone
_NOW_ZONE_HALF = 5            # half-thickness of the NOW band (total ~10px)

# Star Power palette
_SP_BG = (5, 10, 50)
_SP_CYAN = (0, 220, 255)
_SP_WHITE = (230, 245, 255)
_SP_EDGE_BASE = (20, 80, 200)


class NoteHighway:
    """Renders a Synthesia-style scrolling note highway where each note is a
    tall rectangle whose height equals its duration in pixels."""

    def __init__(self):
        self.highway_width = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        self.highway_height = SCREEN_HEIGHT - KEYBOARD_HEIGHT
        self.hit_line_y = int(self.highway_height * 0.85)
        self.font = None
        self.note_font = None
        self.popup_font = None
        self.hold_font = None
        self.key_font = None
        # Will be set when a song starts
        self.column_map = {}          # midi -> x position (un-perspectived)
        self.column_width = 0
        self.pixels_per_second = 0
        self.show_note_names = True
        self.beat_duration = 0.5      # seconds per beat (set from tempo)

        # Post-hit / miss animations
        self._animations: list[NoteAnimation] = []
        # Set of note ids already animated so we don't double-fire
        self._animated_ids: set[int] = set()

    # ------------------------------------------------------------------
    # Perspective helpers
    # ------------------------------------------------------------------

    def _perspective(self, x, y):
        """Apply 3-D perspective transform to a point on the highway.

        *y* is in screen space (0 = top of highway, highway_height = bottom).
        Returns (px, py, scale) where *scale* can be used to size elements.
        """
        t = max(0.0, min(1.0, y / self.highway_height))  # 0 top, 1 bottom
        scale = 0.35 + 0.65 * t   # 35 % at top, 100 % at bottom
        center_x = self.highway_width / 2
        px = center_x + (x - center_x) * scale
        return px, y, scale

    def _perspective_width(self, width, scale):
        """Scale a horizontal dimension by the current perspective factor."""
        return width * scale

    # ------------------------------------------------------------------
    # Lazy font init
    # ------------------------------------------------------------------

    def _ensure_fonts(self):
        if self.font is None:
            self.font = get_font(14)
            self.note_font = get_font(12, bold=True)
            self.popup_font = get_font(16, bold=True)
            self.hold_font = get_font(10, bold=True)
            self.key_font = get_font(11)

    # ------------------------------------------------------------------
    # Song setup
    # ------------------------------------------------------------------

    def setup_for_song(self, song, tempo):
        """Configure columns and scroll speed based on the song's notes."""
        unique_midis = song.unique_notes()
        if not unique_midis:
            return

        # Column layout (flat / un-perspectived)
        margin = 20
        usable_width = self.highway_width - 2 * margin
        num_cols = len(unique_midis)
        self.column_width = min(60, max(20, usable_width // max(num_cols, 1)))
        total_cols_width = self.column_width * num_cols
        start_x = margin + (usable_width - total_cols_width) // 2

        self.column_map = {}
        for i, midi in enumerate(unique_midis):
            self.column_map[midi] = start_x + i * self.column_width

        # Scroll speed: pixels per second
        self.beat_duration = 60.0 / tempo
        preview_seconds = PREVIEW_BEATS * self.beat_duration
        scroll_area = self.hit_line_y  # Pixels from top to hit line
        self.pixels_per_second = scroll_area / max(preview_seconds, 0.01)

        # Reset animation state
        self._animations.clear()
        self._animated_ids.clear()

    # ------------------------------------------------------------------
    # Public draw entry point
    # ------------------------------------------------------------------

    def draw(self, surface, current_time, notes, show_names=True,
             game_session=None, star_power_active=False):
        """Draw the note highway with all visual enhancements."""
        self._ensure_fonts()
        self.show_note_names = show_names
        self._game_session = game_session
        now_real = _time.perf_counter()

        # Background
        highway_rect = pygame.Rect(0, 0, self.highway_width, self.highway_height)
        if star_power_active:
            pygame.draw.rect(surface, _SP_BG, highway_rect)
            self._draw_star_power_edges(surface, now_real)
        else:
            pygame.draw.rect(surface, BG_COLOR, highway_rect)

        # Beat grid lines (perspective-adjusted)
        self._draw_beat_grid(surface, current_time)

        # Column guides (perspective-adjusted subtle vertical lines)
        self._draw_column_guides(surface)

        # Draw note blocks (Synthesia-style duration rectangles)
        # Skip those with active animations
        for note_idx, note in enumerate(notes):
            if id(note) not in self._animated_ids:
                self._draw_note(surface, note, current_time, now_real,
                                note_idx, star_power_active)
            # Spawn animations for newly-hit notes
            self._maybe_spawn_animation(note, current_time, now_real)

        # NOW zone -- the thick glowing hit band
        self._draw_now_zone(surface, now_real, star_power_active)

        # Column labels (note names + keyboard keys) just below the NOW zone
        self._draw_column_labels(surface)

        # Post-hit/miss animations (shrink, fade, fall, popups)
        self._draw_animations(surface, now_real)

    # ------------------------------------------------------------------
    # NOW zone (prominent hit line)
    # ------------------------------------------------------------------

    def _draw_now_zone(self, surface, now_real, star_power_active):
        """Draw a thick glowing band at the hit line with pulsing chevrons."""
        left_px, _, _ = self._perspective(0, self.hit_line_y)
        right_px, _, _ = self._perspective(self.highway_width, self.hit_line_y)
        lx = int(left_px)
        rx = int(right_px)
        band_w = rx - lx
        if band_w <= 0:
            return

        # Pulsing brightness
        pulse = 0.7 + 0.3 * math.sin(now_real * 6)

        # Outer glow (wider, softer)
        glow_h = 20
        glow_surf = pygame.Surface((band_w, glow_h), pygame.SRCALPHA)
        if star_power_active:
            glow_color = (0, 180, 255, int(50 * pulse))
        else:
            glow_color = (150, 150, 255, int(45 * pulse))
        glow_surf.fill(glow_color)
        surface.blit(glow_surf, (lx, self.hit_line_y - glow_h // 2))

        # Core band (bright, opaque)
        band_h = _NOW_ZONE_HALF * 2
        band_top = self.hit_line_y - _NOW_ZONE_HALF
        if star_power_active:
            core_color = tuple(int(c * pulse) for c in _SP_CYAN)
        else:
            bright_val = int(200 * pulse + 55)
            core_color = (bright_val, bright_val, min(255, bright_val + 30))
        pygame.draw.rect(surface, core_color,
                         pygame.Rect(lx, band_top, band_w, band_h))

        # Bright edge lines at top and bottom of band
        edge_color = (255, 255, 255, int(200 * pulse))
        edge_surf = pygame.Surface((band_w, 2), pygame.SRCALPHA)
        edge_surf.fill(edge_color)
        surface.blit(edge_surf, (lx, band_top))
        surface.blit(edge_surf, (lx, band_top + band_h - 2))

        # Pulsing downward-pointing chevrons above the NOW zone
        chevron_y_base = self.hit_line_y - _NOW_ZONE_HALF - 14
        chevron_pulse = 0.5 + 0.5 * math.sin(now_real * 4)
        chevron_alpha = int(120 + 100 * chevron_pulse)
        num_chevrons = max(3, band_w // 120)
        spacing = band_w / (num_chevrons + 1)
        for i in range(num_chevrons):
            cx = lx + int(spacing * (i + 1))
            cy = chevron_y_base - int(3 * chevron_pulse)
            chev_size = 6
            chev_surf = pygame.Surface((chev_size * 2 + 2, chev_size + 2),
                                       pygame.SRCALPHA)
            if star_power_active:
                chev_color = (*_SP_CYAN[:3], chevron_alpha)
            else:
                chev_color = (255, 255, 255, chevron_alpha)
            # Draw a small downward-pointing chevron
            pts = [
                (0, 0),
                (chev_size, chev_size),
                (chev_size * 2, 0),
            ]
            pygame.draw.lines(chev_surf, chev_color, False, pts, 2)
            surface.blit(chev_surf,
                         (cx - chev_size, cy))

    # ------------------------------------------------------------------
    # Column labels
    # ------------------------------------------------------------------

    def _draw_column_labels(self, surface):
        """Show note names and keyboard key labels below the NOW zone."""
        from piano_hero.constants import midi_to_note_name
        try:
            from piano_hero.input.keyboard_input import MIDI_TO_KEY_NAME
        except ImportError:
            MIDI_TO_KEY_NAME = {}

        label_y_name = self.hit_line_y + _NOW_ZONE_HALF + 6
        label_y_key = label_y_name + 16

        for midi, raw_x in self.column_map.items():
            cx_raw = raw_x + self.column_width // 2
            px, _, sc = self._perspective(cx_raw, label_y_name)

            # Note name (e.g. C4, D4)
            name = midi_to_note_name(midi)
            text = self.font.render(name, True, COLOR_DARK_GRAY)
            text_rect = text.get_rect(centerx=int(px), centery=int(label_y_name))
            surface.blit(text, text_rect)

            # Keyboard key label
            key_name = MIDI_TO_KEY_NAME.get(midi, '')
            if key_name:
                key_text = self.key_font.render(key_name, True, (80, 80, 100))
                key_rect = key_text.get_rect(centerx=int(px),
                                             centery=int(label_y_key))
                surface.blit(key_text, key_rect)

    # ------------------------------------------------------------------
    # Star Power edge flames
    # ------------------------------------------------------------------

    def _draw_star_power_edges(self, surface, now_real):
        """Blue flame/glow on the left and right edges during Star Power."""
        edge_width = 18
        for y in range(0, self.highway_height, 4):
            t = y / self.highway_height
            intensity = 0.5 + 0.5 * math.sin(now_real * 5 + y * 0.04)
            alpha = int(60 * intensity * (0.4 + 0.6 * t))
            # Left edge
            lx, _, sc = self._perspective(0, y)
            stripe = pygame.Surface((int(edge_width * sc), 4), pygame.SRCALPHA)
            stripe.fill((*_SP_EDGE_BASE, alpha))
            surface.blit(stripe, (int(lx), y))
            # Right edge
            rx, _, _ = self._perspective(self.highway_width, y)
            stripe2 = pygame.Surface((int(edge_width * sc), 4), pygame.SRCALPHA)
            stripe2.fill((*_SP_EDGE_BASE, alpha))
            surface.blit(stripe2, (int(rx) - int(edge_width * sc), y))

    # ------------------------------------------------------------------
    # Beat grid
    # ------------------------------------------------------------------

    def _draw_beat_grid(self, surface, current_time):
        """Draw horizontal lines at each beat interval, perspective-adjusted.
        Measure boundaries (every 4th beat) are brighter and thicker."""
        if self.beat_duration <= 0 or self.pixels_per_second <= 0:
            return

        top_time = current_time + self.hit_line_y / self.pixels_per_second
        bot_time = current_time - (self.highway_height - self.hit_line_y) / self.pixels_per_second

        first_beat = int(bot_time / self.beat_duration)
        last_beat = int(top_time / self.beat_duration) + 1

        beat_color = (65, 45, 90)
        measure_color = (90, 65, 120)

        for b in range(first_beat, last_beat + 1):
            beat_time = b * self.beat_duration
            time_until_hit = beat_time - current_time
            y = self.hit_line_y - int(time_until_hit * self.pixels_per_second)
            if 0 <= y <= self.highway_height:
                lx, _, sc = self._perspective(0, y)
                rx, _, _ = self._perspective(self.highway_width, y)
                is_measure = (b % 4 == 0)
                color = measure_color if is_measure else beat_color
                thickness = 2 if is_measure else 1
                pygame.draw.line(surface, color,
                                 (int(lx), y), (int(rx), y), thickness)

    # ------------------------------------------------------------------
    # Column guides
    # ------------------------------------------------------------------

    def _draw_column_guides(self, surface):
        """Subtle vertical lines for each column, converging in perspective."""
        guide_color = (30, 15, 50)
        for midi, raw_x in self.column_map.items():
            cx_raw = raw_x + self.column_width // 2
            prev_px, prev_py = None, None
            for seg_y in range(0, self.highway_height, 12):
                px, _, _ = self._perspective(cx_raw, seg_y)
                if prev_px is not None:
                    pygame.draw.line(surface, guide_color,
                                     (int(prev_px), prev_py),
                                     (int(px), seg_y), 1)
                prev_px, prev_py = px, seg_y

    # ------------------------------------------------------------------
    # Single note rendering (Synthesia-style duration rectangle)
    # ------------------------------------------------------------------

    def _draw_note(self, surface, note, current_time, now_real,
                   note_idx=0, star_power_active=False):
        """Draw a note as a tall rectangle whose height equals its duration.

        The BOTTOM edge is where the player presses (at the hit line).
        The TOP edge is where the player releases.
        """
        if note.midi not in self.column_map:
            return

        raw_x = self.column_map[note.midi]
        raw_cx = raw_x + self.column_width // 2

        # Y position: the BOTTOM of the note block aligns with the hit time
        time_until_hit = note.start_time - current_time
        note_bottom_y = self.hit_line_y - int(time_until_hit * self.pixels_per_second)

        # Duration in pixels
        duration_seconds = note.duration_beat * self.beat_duration
        duration_px = max(_MIN_NOTE_HEIGHT,
                          int(duration_seconds * self.pixels_per_second))
        note_top_y = note_bottom_y - duration_px

        # Skip if completely off screen
        if note_bottom_y < -50 or note_top_y > self.highway_height + 50:
            return

        # -- Choose base color --
        is_star_note = getattr(note, 'star_power', False)
        if note.hit:
            if note.judgment == "perfect":
                base_color = COLOR_PERFECT
            elif note.judgment == "good":
                base_color = COLOR_GOOD
            elif note.judgment == "ok":
                base_color = COLOR_OK
            elif note.judgment == "miss":
                base_color = COLOR_MISS
            else:
                base_color = COLOR_DARK_GRAY
        else:
            octave = note.midi // 12 - 1
            base_color = OCTAVE_COLORS.get(octave, DEFAULT_NOTE_COLOR)

        # Star Power note glow override
        if is_star_note and not note.hit:
            sp_pulse = 0.5 + 0.5 * math.sin(now_real * 6)
            base_color = lerp_color(_SP_CYAN, _SP_WHITE, sp_pulse)
        elif star_power_active and not note.hit:
            base_color = lerp_color(base_color, _SP_CYAN, 0.45)

        # -- Approach glow: notes within 2 beats pulse brighter --
        glow_add = 0
        if not note.hit and self.beat_duration > 0:
            beats_away = time_until_hit / self.beat_duration
            if 0 < beats_away < _APPROACH_GLOW_BEATS:
                proximity = 1.0 - (beats_away / _APPROACH_GLOW_BEATS)
                pulse = 0.5 + 0.5 * math.sin(now_real * (6 + proximity * 10))
                glow_add = int(120 * proximity * pulse)

        draw_color = base_color
        if glow_add > 0:
            draw_color = tuple(min(255, c + glow_add) for c in base_color)

        # -- Hold progress --
        hold_progress = -1.0
        if self._game_session is not None:
            hold_progress = self._game_session.get_hold_progress(note_idx)

        # -- Draw the note block as perspective-adjusted strips --
        # We draw horizontal strips from note_top_y to note_bottom_y to apply
        # per-row perspective scaling.
        draw_top = max(0, note_top_y)
        draw_bottom = min(self.highway_height, note_bottom_y)
        if draw_top >= draw_bottom:
            return

        strip_h = 2
        for y in range(draw_top, draw_bottom, strip_h):
            actual_h = min(strip_h, draw_bottom - y)
            px, _, sc = self._perspective(raw_cx, y)
            w = int(self._perspective_width(self.column_width - 4, sc))
            if w < 3:
                w = 3
            strip_left = int(px - w // 2)

            # Determine fill color for hold progress
            strip_color = draw_color
            if hold_progress > 0 and note_bottom_y > note_top_y:
                # Fill grows upward from the hit line
                fill_boundary = note_bottom_y - int(
                    (note_bottom_y - note_top_y) * hold_progress
                )
                if y >= self.hit_line_y:
                    # Below hit line: always bright fill
                    strip_color = tuple(min(255, c + 70) for c in base_color)
                elif y >= fill_boundary and y < self.hit_line_y:
                    # Between fill boundary and hit line -- filled portion
                    strip_color = tuple(min(255, c + 70) for c in base_color)

            # Draw opaque strip (no alpha -- vivid and solid)
            pygame.draw.rect(surface, strip_color,
                             pygame.Rect(strip_left, y, w, actual_h))

        # -- Star Power halo (pulsing white/cyan glow around the block) --
        if is_star_note and not note.hit:
            halo_pulse = 0.5 + 0.5 * math.sin(now_real * 4)
            halo_alpha = int(40 + 40 * halo_pulse)
            # Draw halo at a few representative heights
            for hy in range(draw_top, draw_bottom, 6):
                hpx, _, hsc = self._perspective(raw_cx, hy)
                hw = int(self._perspective_width(self.column_width + 10, hsc))
                halo_surf = pygame.Surface((hw, 6), pygame.SRCALPHA)
                halo_surf.fill((*_SP_WHITE[:3], halo_alpha))
                surface.blit(halo_surf, (int(hpx - hw // 2), hy))

        # -- Approach glow halo around the block --
        if glow_add > 30 and not note.hit:
            glow_alpha = min(60, glow_add)
            for gy in range(draw_top, draw_bottom, 6):
                gpx, _, gsc = self._perspective(raw_cx, gy)
                gw = int(self._perspective_width(self.column_width + 6, gsc))
                gs = pygame.Surface((gw, 6), pygame.SRCALPHA)
                gs.fill((*base_color[:3], glow_alpha))
                surface.blit(gs, (int(gpx - gw // 2), gy))

        # -- Release marker: bright line at the TOP of the block --
        if not note.hit and draw_top >= 0 and draw_top < self.highway_height:
            rpx, _, rsc = self._perspective(raw_cx, draw_top)
            rw = int(self._perspective_width(self.column_width - 4, rsc))
            if rw > 2:
                release_color = tuple(min(255, c + 80) for c in base_color)
                rleft = int(rpx - rw // 2)
                pygame.draw.rect(surface, release_color,
                                 pygame.Rect(rleft, draw_top, rw, 3))

        # -- Bright edge at the BOTTOM of the block (press edge) --
        if not note.hit and draw_bottom > 0 and draw_bottom <= self.highway_height:
            bpx, _, bsc = self._perspective(raw_cx, draw_bottom - 2)
            bw = int(self._perspective_width(self.column_width - 4, bsc))
            if bw > 2:
                edge_color = tuple(min(255, c + 50) for c in draw_color)
                bleft = int(bpx - bw // 2)
                pygame.draw.rect(surface, edge_color,
                                 pygame.Rect(bleft, draw_bottom - 2, bw, 2))

        # -- HOLD label for sustained notes --
        if not note.hit and duration_seconds > 0.5:
            self._draw_hold_label(surface, note_top_y, note_bottom_y,
                                  raw_cx, duration_seconds, base_color)

        # -- Hold countdown during active holds --
        if hold_progress > 0 and duration_seconds > 0.3:
            remaining = duration_seconds * (1.0 - hold_progress)
            self._draw_hold_countdown(surface, note_top_y, note_bottom_y,
                                      raw_cx, remaining, hold_progress)

        # -- Note name on the block --
        if self.show_note_names and (draw_bottom - draw_top) > 16:
            mid_y = (draw_top + draw_bottom) // 2
            mpx, _, msc = self._perspective(raw_cx, mid_y)
            name_text = self.note_font.render(note.note_name, True,
                                              COLOR_BLACK)
            name_rect = name_text.get_rect(centerx=int(mpx),
                                           centery=mid_y)
            # Only draw if the text fits within visible area
            if name_rect.top >= draw_top and name_rect.bottom <= draw_bottom:
                surface.blit(name_text, name_rect)

    # ------------------------------------------------------------------
    # HOLD label rendering
    # ------------------------------------------------------------------

    def _draw_hold_label(self, surface, note_top_y, note_bottom_y,
                         raw_cx, duration_seconds, base_color):
        """Draw 'HOLD' (and duration) vertically inside the note block."""
        visible_top = max(0, note_top_y)
        visible_bottom = min(self.highway_height, note_bottom_y)
        block_visible_h = visible_bottom - visible_top
        if block_visible_h < 30:
            return

        # Text color: contrasting with the note
        brightness = sum(base_color[:3]) / 3
        text_color = COLOR_BLACK if brightness > 127 else COLOR_WHITE

        mid_y = (visible_top + visible_bottom) // 2
        mpx, _, msc = self._perspective(raw_cx, mid_y)

        if duration_seconds > 1.0 and block_visible_h > 50:
            label = f"HOLD {duration_seconds:.1f}s"
        else:
            label = "HOLD"

        text_surf = self.hold_font.render(label, True, text_color)
        # Rotate 90 degrees for vertical rendering if block is tall enough
        if block_visible_h > 60:
            text_surf = pygame.transform.rotate(text_surf, 90)

        text_rect = text_surf.get_rect(centerx=int(mpx), centery=mid_y)
        # Clamp within visible block
        if text_rect.top < visible_top:
            text_rect.top = visible_top
        if text_rect.bottom > visible_bottom:
            text_rect.bottom = visible_bottom

        surface.blit(text_surf, text_rect)

    # ------------------------------------------------------------------
    # Hold countdown during active holds
    # ------------------------------------------------------------------

    def _draw_hold_countdown(self, surface, note_top_y, note_bottom_y,
                             raw_cx, remaining, progress):
        """Show remaining seconds or hold percentage on the note."""
        visible_top = max(0, note_top_y)
        visible_bottom = min(self.highway_height, note_bottom_y)
        if visible_bottom - visible_top < 20:
            return

        # Show just above the hit line, inside the note
        show_y = min(self.hit_line_y - 18, visible_bottom - 18)
        if show_y < visible_top:
            return

        mpx, _, _ = self._perspective(raw_cx, show_y)

        countdown_text = f"{remaining:.1f}s"
        if progress >= 0.8:
            cd_color = COLOR_PERFECT
        elif progress >= 0.4:
            cd_color = COLOR_GOOD
        else:
            cd_color = (100, 200, 100)

        text_surf = self.hold_font.render(countdown_text, True, cd_color)
        text_rect = text_surf.get_rect(centerx=int(mpx), centery=show_y)
        surface.blit(text_surf, text_rect)

    # ------------------------------------------------------------------
    # Animation spawning
    # ------------------------------------------------------------------

    def _maybe_spawn_animation(self, note, current_time, now_real):
        """If a note has been hit/missed and doesn't have an animation yet,
        create one."""
        if not note.hit:
            return
        nid = id(note)
        if nid in self._animated_ids:
            return

        self._animated_ids.add(nid)

        raw_x = self.column_map.get(note.midi, self.highway_width // 2)
        raw_cx = raw_x + self.column_width // 2
        time_until_hit = note.start_time - current_time
        y = self.hit_line_y - int(time_until_hit * self.pixels_per_second)

        px, _, _ = self._perspective(raw_cx, y)

        anim_type = f"hit_{note.judgment}" if note.judgment != "miss" else "miss"
        points = {
            "perfect": PERFECT_POINTS,
            "good": GOOD_POINTS,
            "ok": OK_POINTS,
        }.get(note.judgment, 0)

        # Determine early/late
        early_late = ""
        if note.judgment in ("good", "ok"):
            if y < self.hit_line_y:
                early_late = "early"
            elif y > self.hit_line_y:
                early_late = "late"

        self._animations.append(NoteAnimation(
            note=note,
            start_time=now_real,
            anim_type=anim_type,
            x=int(px),
            y=min(max(y, 10), self.highway_height - 10),
            points=points,
            early_late=early_late,
        ))

    # ------------------------------------------------------------------
    # Animation drawing
    # ------------------------------------------------------------------

    def _draw_animations(self, surface, now_real):
        """Draw and update all active note animations."""
        alive = []
        for anim in self._animations:
            age = now_real - anim.start_time

            if anim.anim_type == "miss":
                # Miss: note turns red and falls away
                if age < _MISS_ANIM_DURATION:
                    t = age / _MISS_ANIM_DURATION
                    alpha = int(255 * (1.0 - t))
                    fall_y = anim.y + int(80 * t * t)
                    size = max(4, int((self.column_width - 4) * (1.0 - 0.3 * t)))
                    rect = pygame.Rect(
                        anim.x - size // 2, fall_y - size // 2,
                        size, int(size * 0.6),
                    )
                    miss_surf = pygame.Surface(
                        (rect.width, rect.height), pygame.SRCALPHA
                    )
                    pygame.draw.rect(
                        miss_surf, (*COLOR_MISS[:3], alpha),
                        pygame.Rect(0, 0, rect.width, rect.height),
                        border_radius=3,
                    )
                    surface.blit(miss_surf, rect.topleft)
                    alive.append(anim)
            else:
                # Hit: shrink and fade out
                draw_hit = age < _HIT_ANIM_DURATION
                draw_popup = age < _POPUP_DURATION

                if draw_hit:
                    t = age / _HIT_ANIM_DURATION
                    alpha = int(255 * (1.0 - t))
                    anim_scale = 1.0 - 0.6 * t
                    size = max(4, int((self.column_width - 4) * anim_scale))
                    color_map = {
                        "hit_perfect": COLOR_PERFECT,
                        "hit_good": COLOR_GOOD,
                        "hit_ok": COLOR_OK,
                    }
                    color = color_map.get(anim.anim_type, COLOR_GOOD)
                    rect = pygame.Rect(
                        anim.x - size // 2, anim.y - size // 2,
                        size, int(size * 0.6),
                    )
                    hit_surf = pygame.Surface(
                        (rect.width, rect.height), pygame.SRCALPHA
                    )
                    pygame.draw.rect(
                        hit_surf, (*color[:3], alpha),
                        pygame.Rect(0, 0, rect.width, rect.height),
                        border_radius=3,
                    )
                    surface.blit(hit_surf, rect.topleft)

                # Score popup: float upward and fade
                if draw_popup and anim.points > 0:
                    pt = age / _POPUP_DURATION
                    popup_alpha = int(255 * (1.0 - pt))
                    rise = int(_POPUP_RISE * pt)
                    popup_text = f"+{anim.points}"
                    popup_surf = self.popup_font.render(
                        popup_text, True, COLOR_WHITE
                    )
                    popup_surf.set_alpha(popup_alpha)
                    popup_rect = popup_surf.get_rect(
                        center=(anim.x, anim.y - 20 - rise)
                    )
                    surface.blit(popup_surf, popup_rect)

                # Timing indicator: small arrow showing early or late
                if draw_hit and anim.early_late:
                    indicator_y = anim.y + 12
                    if anim.early_late == "early":
                        pts_list = [
                            (anim.x - 10, indicator_y),
                            (anim.x - 2, indicator_y - 5),
                            (anim.x - 2, indicator_y + 5),
                        ]
                        ind_color = COLOR_EARLY
                    else:
                        pts_list = [
                            (anim.x + 10, indicator_y),
                            (anim.x + 2, indicator_y - 5),
                            (anim.x + 2, indicator_y + 5),
                        ]
                        ind_color = COLOR_LATE

                    t = age / _HIT_ANIM_DURATION
                    ind_alpha = int(200 * (1.0 - t))
                    ind_surf = pygame.Surface((24, 14), pygame.SRCALPHA)
                    offset_pts = [
                        (ppx - (anim.x - 12), ppy - (indicator_y - 7))
                        for ppx, ppy in pts_list
                    ]
                    pygame.draw.polygon(ind_surf, (*ind_color[:3], ind_alpha),
                                        offset_pts)
                    surface.blit(ind_surf, (anim.x - 12, indicator_y - 7))

                if draw_hit or draw_popup:
                    alive.append(anim)

        self._animations = alive

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_note_y(self, note, current_time):
        """Get the Y position of a note for effects."""
        time_until_hit = note.start_time - current_time
        return self.hit_line_y - int(time_until_hit * self.pixels_per_second)
