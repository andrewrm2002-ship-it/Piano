"""Main menu, song selection, results, settings, calibration, and stats screens."""

import math
import os
import time

import pygame

from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_WHITE, COLOR_ACCENT, COLOR_GRAY,
    COLOR_DARK_GRAY, COLOR_BLACK, MENU_BG, SONG_CARD_HEIGHT,
    SONG_CARD_PADDING, SCROLL_SPEED, COLOR_STAR_FILLED, COLOR_STAR_EMPTY,
    COLOR_PERFECT, COLOR_GOOD, COLOR_OK, COLOR_MISS, COLOR_STREAK_FLAME,
    OCTAVE_COLORS, DIFFICULTY_TIERS, SONG_CATEGORIES, GRADE_COLORS,
    GRADE_THRESHOLDS,
)
from piano_hero.ui.renderer import get_font, get_title_font, draw_text, lerp_color
from piano_hero.game.score import load_high_scores, get_letter_grade
from piano_hero.game.statistics import load_stats, get_stars_earned, get_average_accuracy


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DAILY_TIPS = [
    "Tip: Start slow and build up speed as you improve!",
    "Tip: Focus on keeping a steady rhythm, not just hitting notes.",
    "Tip: Use Practice mode to master tricky sections at 50% speed.",
    "Tip: A Perfect streak multiplies your score up to 4x!",
    "Tip: Calibrate your audio for the best timing accuracy.",
    "Tip: Consistent practice beats marathon sessions!",
    "Tip: Try to stay relaxed — tension slows your fingers down.",
]


def draw_star_points(cx, cy, size):
    """Generate star polygon points centered at (cx, cy) with given outer radius."""
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = size if i % 2 == 0 else size * 0.4
        points.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    return points


# ---------------------------------------------------------------------------
# MainMenu
# ---------------------------------------------------------------------------

class MainMenu:
    """Main menu screen with Play, Practice, Stats, Settings, Quit."""

    def __init__(self):
        self.title_font = None
        self.subtitle_font = None
        self.button_font = None
        self.tip_font = None
        self.buttons = ["PLAY", "PRACTICE", "STATS", "SETTINGS", "QUIT"]
        self.selected = 0
        self._anim_time = 0.0
        self._tip_index = int(time.time() / 86400) % len(DAILY_TIPS)

    def _ensure_fonts(self):
        if self.title_font is None:
            self.title_font = get_title_font(64)
            self.subtitle_font = get_font(20)
            self.button_font = get_font(28, bold=True)
            self.tip_font = get_font(15)

    def handle_event(self, event):
        """Handle input. Returns action string or None."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected = (self.selected - 1) % len(self.buttons)
            elif event.key == pygame.K_DOWN:
                self.selected = (self.selected + 1) % len(self.buttons)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return self.buttons[self.selected].lower()
            elif event.key == pygame.K_ESCAPE:
                return "quit"
        return None

    def update(self, dt):
        self._anim_time += dt

    def draw(self, surface):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        # Animated title with glow pulse
        glow_t = (math.sin(self._anim_time * 2.0) + 1.0) / 2.0  # 0..1
        glow_alpha = int(40 + 30 * glow_t)
        glow_surf = pygame.Surface((400, 80), pygame.SRCALPHA)
        glow_surf.fill((*COLOR_ACCENT[:3], glow_alpha))
        glow_rect = glow_surf.get_rect(center=(cx, 140))
        surface.blit(glow_surf, glow_rect)

        draw_text(surface, "PIANO HERO", (cx, 140), self.title_font,
                  COLOR_ACCENT, center=True, shadow=True)

        # Subtitle
        draw_text(surface, "Connect your keyboard and play!",
                  (cx, 210), self.subtitle_font, COLOR_GRAY, center=True)

        # Buttons
        y = 300
        for i, label in enumerate(self.buttons):
            if i == self.selected:
                color = COLOR_ACCENT
                indicator_x = cx - 130
                pygame.draw.polygon(surface, COLOR_ACCENT, [
                    (indicator_x, y + 5),
                    (indicator_x + 15, y + 15),
                    (indicator_x, y + 25),
                ])
                btn_rect = pygame.Rect(cx - 110, y - 5, 220, 40)
                sel_surf = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
                sel_surf.fill((0, 200, 255, 30))
                surface.blit(sel_surf, btn_rect)
            else:
                color = COLOR_GRAY
            draw_text(surface, label, (cx, y + 15), self.button_font, color,
                      center=True)
            y += 55

        # Daily tip at bottom
        draw_text(surface, DAILY_TIPS[self._tip_index],
                  (cx, SCREEN_HEIGHT - 70), self.tip_font, COLOR_DARK_GRAY,
                  center=True)

        # Footer
        draw_text(surface, "Use UP/DOWN to navigate, ENTER to select",
                  (cx, SCREEN_HEIGHT - 35), get_font(14), COLOR_DARK_GRAY,
                  center=True)


# ---------------------------------------------------------------------------
# SongSelect
# ---------------------------------------------------------------------------

class SongSelect:
    """Song selection screen with category tabs, search, sort, difficulty badges."""

    SORT_MODES = [
        ('title', 'A-Z'),
        ('difficulty', 'Difficulty'),
        ('tempo', 'Tempo'),
        ('duration', 'Duration'),
        ('notes', 'Note Count'),
    ]

    def __init__(self, songs, practice_mode=False):
        self.all_songs = songs
        self.practice_mode = practice_mode
        self.selected = 0
        self.scroll_offset = 0

        # Category tabs
        self.categories = list(SONG_CATEGORIES)
        self.category_index = 0

        # Search
        self.search_text = ""
        self.search_active = False  # True when typing in search box

        # Sort
        self.sort_index = 0  # Index into SORT_MODES
        self.sort_ascending = True

        # Difficulty selection
        self.difficulty_options = ['Easy', 'Medium', 'Hard']
        self.difficulty_index = 1  # default Medium

        # Practice speed
        self._speed_options = [50, 75, 100]
        self._speed_index = 2

        # Lazy fonts
        self.title_font = None
        self.song_font = None
        self.detail_font = None
        self.small_font = None
        self.tab_font = None
        self.badge_font = None
        self.search_font = None

        self.high_scores = load_high_scores()
        self._rebuild_filtered()

    def _ensure_fonts(self):
        if self.title_font is None:
            self.title_font = get_title_font(36)
            self.song_font = get_font(22, bold=True)
            self.detail_font = get_font(16)
            self.small_font = get_font(14)
            self.tab_font = get_font(15, bold=True)
            self.badge_font = get_font(12, bold=True)
            self.search_font = get_font(18)

    def _rebuild_filtered(self):
        """Rebuild the song list based on category, search, and sort."""
        # Category filter
        cat = self.categories[self.category_index]
        if cat == "All":
            filtered = list(self.all_songs)
        else:
            filtered = [s for s in self.all_songs
                        if getattr(s, 'category', '') == cat]

        # Search filter
        if self.search_text:
            query = self.search_text.lower()
            filtered = [s for s in filtered
                        if (query in s.title.lower()
                            or query in s.composer.lower()
                            or query in getattr(s, 'difficulty_tier', '').lower())]

        # Sort
        sort_key, _ = self.SORT_MODES[self.sort_index]
        if sort_key == 'title':
            filtered.sort(key=lambda s: s.title.lower(),
                          reverse=not self.sort_ascending)
        elif sort_key == 'difficulty':
            order = {'beginner': 0, 'easy': 1, 'medium': 2, 'hard': 3}
            filtered.sort(key=lambda s: order.get(
                getattr(s, 'difficulty_tier', 'easy'), 1),
                          reverse=not self.sort_ascending)
        elif sort_key == 'tempo':
            filtered.sort(key=lambda s: s.tempo,
                          reverse=not self.sort_ascending)
        elif sort_key == 'duration':
            filtered.sort(key=lambda s: s.duration,
                          reverse=not self.sort_ascending)
        elif sort_key == 'notes':
            filtered.sort(key=lambda s: len(s.notes),
                          reverse=not self.sort_ascending)

        self.songs = filtered
        self.selected = min(self.selected, max(0, len(self.songs) - 1))
        self.scroll_offset = 0

    @property
    def speed_percent(self):
        return self._speed_options[self._speed_index]

    def handle_event(self, event):
        """Handle input. Returns 'play', 'back', or None."""
        if event.type != pygame.KEYDOWN:
            return None

        # Search mode: typing into search box
        if self.search_active:
            if event.key == pygame.K_ESCAPE:
                self.search_active = False
                return None
            elif event.key == pygame.K_RETURN:
                self.search_active = False
                return None
            elif event.key == pygame.K_BACKSPACE:
                self.search_text = self.search_text[:-1]
                self._rebuild_filtered()
                return None
            elif event.unicode and event.unicode.isprintable():
                self.search_text += event.unicode
                self._rebuild_filtered()
                return None
            return None

        # Normal mode
        if event.key == pygame.K_ESCAPE:
            if self.search_text:
                self.search_text = ""
                self._rebuild_filtered()
                return None
            return "back"

        # / or F to activate search
        if event.key in (pygame.K_SLASH, pygame.K_f) and not self.search_active:
            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                self.search_active = True
                return None

        # TAB to cycle sort mode
        if event.key == pygame.K_TAB:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_SHIFT:
                self.sort_ascending = not self.sort_ascending
            else:
                self.sort_index = (self.sort_index + 1) % len(self.SORT_MODES)
            self._rebuild_filtered()
            return None

        if not self.songs and event.key not in (pygame.K_LEFT, pygame.K_RIGHT):
            return None

        if event.key == pygame.K_UP:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.difficulty_index = (self.difficulty_index - 1) % len(self.difficulty_options)
            else:
                self.selected = max(0, self.selected - 1)
                self._ensure_visible()
        elif event.key == pygame.K_DOWN:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.difficulty_index = (self.difficulty_index + 1) % len(self.difficulty_options)
            elif self.songs:
                self.selected = min(len(self.songs) - 1, self.selected + 1)
                self._ensure_visible()
        elif event.key == pygame.K_LEFT:
            if self.practice_mode and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self._speed_index = max(0, self._speed_index - 1)
            else:
                self.category_index = (self.category_index - 1) % len(self.categories)
                self._rebuild_filtered()
        elif event.key == pygame.K_RIGHT:
            if self.practice_mode and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self._speed_index = min(len(self._speed_options) - 1, self._speed_index + 1)
            else:
                self.category_index = (self.category_index + 1) % len(self.categories)
                self._rebuild_filtered()
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.songs:
                return "play"

        return None

    def _ensure_visible(self):
        """Scroll to keep selected song visible."""
        visible_height = SCREEN_HEIGHT - 160
        card_total = SONG_CARD_HEIGHT + SONG_CARD_PADDING
        selected_y = self.selected * card_total - self.scroll_offset
        if selected_y < 0:
            self.scroll_offset = self.selected * card_total
        elif selected_y + SONG_CARD_HEIGHT > visible_height:
            self.scroll_offset = (self.selected * card_total +
                                   SONG_CARD_HEIGHT - visible_height)

    def get_selected_song(self):
        if 0 <= self.selected < len(self.songs):
            return self.songs[self.selected]
        return None

    def get_speed(self) -> float:
        """Return the selected practice speed as a multiplier (0.5, 0.75, 1.0)."""
        return self._speed_options[self._speed_index] / 100.0

    def get_difficulty(self) -> str:
        """Return the currently selected difficulty string."""
        return self.difficulty_options[self.difficulty_index]

    def draw(self, surface):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        # Header
        draw_text(surface, "SELECT A SONG", (cx, 25), self.title_font,
                  COLOR_ACCENT, center=True)

        # ── Search bar ──────────────────────────────────────────────
        search_y = 55
        search_w = 300
        search_x = cx - search_w // 2
        search_rect = pygame.Rect(search_x, search_y, search_w, 26)
        border_col = COLOR_ACCENT if self.search_active else (60, 40, 80)
        pygame.draw.rect(surface, (30, 15, 50), search_rect, border_radius=5)
        pygame.draw.rect(surface, border_col, search_rect, 1, border_radius=5)
        if self.search_text:
            draw_text(surface, self.search_text,
                      (search_x + 10, search_y + 4), self.search_font, COLOR_WHITE)
        else:
            hint = "Type / to search..." if not self.search_active else "Type to search..."
            draw_text(surface, hint,
                      (search_x + 10, search_y + 4), self.search_font, COLOR_DARK_GRAY)

        # ── Sort indicator ──────────────────────────────────────────
        _, sort_label = self.SORT_MODES[self.sort_index]
        arrow = "\u25b2" if self.sort_ascending else "\u25bc"
        sort_text = f"Sort: {sort_label} {arrow}  (TAB)"
        draw_text(surface, sort_text, (SCREEN_WIDTH - 30, search_y + 4),
                  self.small_font, COLOR_GRAY)

        # ── Category tabs ────────────────────────────────────────────
        tab_y = 86
        total_tab_w = 0
        tab_widths = []
        for cat in self.categories:
            w = self.tab_font.size(cat)[0] + 24
            tab_widths.append(w)
            total_tab_w += w + 6
        tab_x = (SCREEN_WIDTH - total_tab_w) // 2

        for ci, cat in enumerate(self.categories):
            tw = tab_widths[ci]
            tab_rect = pygame.Rect(tab_x, tab_y, tw, 26)
            if ci == self.category_index:
                pygame.draw.rect(surface, COLOR_ACCENT, tab_rect, border_radius=5)
                draw_text(surface, cat, (tab_x + tw // 2, tab_y + 13),
                          self.tab_font, COLOR_BLACK, center=True)
            else:
                pygame.draw.rect(surface, (40, 20, 60), tab_rect, border_radius=5)
                pygame.draw.rect(surface, (60, 40, 80), tab_rect, 1, border_radius=5)
                draw_text(surface, cat, (tab_x + tw // 2, tab_y + 13),
                          self.tab_font, COLOR_GRAY, center=True)
            tab_x += tw + 6

        # ── Song list (clipped area) ─────────────────────────────────
        list_y = 118
        list_height = SCREEN_HEIGHT - 180
        clip_rect = pygame.Rect(20, list_y, SCREEN_WIDTH - 40, list_height)
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        card_total = SONG_CARD_HEIGHT + SONG_CARD_PADDING
        for i, song in enumerate(self.songs):
            y = list_y + i * card_total - self.scroll_offset
            if y + SONG_CARD_HEIGHT < list_y or y > list_y + list_height:
                continue
            self._draw_song_card(surface, song, i, 30, y, i == self.selected)

        surface.set_clip(old_clip)

        # ── Footer ───────────────────────────────────────────────────
        footer_y = SCREEN_HEIGHT - 55

        # Difficulty selector
        diff_label = self.difficulty_options[self.difficulty_index]
        diff_text = f"Difficulty: < {diff_label} >  (SHIFT+UP/DOWN)"
        draw_text(surface, diff_text, (cx, footer_y), self.small_font,
                  COLOR_ACCENT, center=True)
        footer_y += 18

        if self.practice_mode:
            speed = self._speed_options[self._speed_index]
            speed_text = f"Speed: SHIFT+LEFT/RIGHT  [ {speed}% ]"
            draw_text(surface, speed_text, (cx, footer_y), self.small_font,
                      COLOR_ACCENT, center=True)
            footer_y += 18

        count = len(self.songs)
        draw_text(surface, f"{count} songs | / Search | TAB Sort | SHIFT+TAB Reverse | LEFT/RIGHT Category | ENTER Play",
                  (cx, footer_y), self.small_font, COLOR_DARK_GRAY, center=True)

    def _draw_song_card(self, surface, song, index, x, y, selected):
        """Draw a single song card with difficulty badge, duration, stars, grade, and mini preview."""
        w = SCREEN_WIDTH - 60
        rect = pygame.Rect(x, y, w, SONG_CARD_HEIGHT)

        # Background
        if selected:
            bg_color = (40, 20, 70)
            border_color = COLOR_ACCENT
        else:
            bg_color = (25, 10, 45)
            border_color = (50, 30, 70)

        pygame.draw.rect(surface, bg_color, rect, border_radius=8)
        pygame.draw.rect(surface, border_color, rect, 2, border_radius=8)

        # Song number
        draw_text(surface, f"{index + 1}.", (x + 15, y + 12), self.detail_font,
                  COLOR_DARK_GRAY)

        # Title
        draw_text(surface, song.title, (x + 50, y + 10), self.song_font,
                  COLOR_WHITE if selected else COLOR_GRAY)

        # Difficulty badge
        tier = getattr(song, 'difficulty_tier', 'easy')
        tier_info = DIFFICULTY_TIERS.get(tier, DIFFICULTY_TIERS['easy'])
        badge_label = tier_info['label']
        badge_color = tier_info['color']
        badge_w = self.badge_font.size(badge_label)[0] + 12
        badge_x = x + 50 + self.song_font.size(song.title)[0] + 12
        badge_rect = pygame.Rect(badge_x, y + 12, badge_w, 18)
        pygame.draw.rect(surface, badge_color, badge_rect, border_radius=4)
        draw_text(surface, badge_label,
                  (badge_x + badge_w // 2, y + 21), self.badge_font,
                  COLOR_BLACK, center=True)

        # Composer + duration details
        duration_str = getattr(song, 'duration_str', '')
        details = f"{song.composer}  |  {song.tempo} BPM  |  {len(song.notes)} notes"
        if duration_str:
            details += f"  |  {duration_str}"
        draw_text(surface, details, (x + 50, y + 40), self.detail_font,
                  COLOR_GRAY if selected else COLOR_DARK_GRAY)

        # ── Stars ────────────────────────────────────────────────────
        key = os.path.basename(song.filepath)
        score_data = self.high_scores.get(key, {})
        stars = score_data.get('stars', 0)
        star_x = x + w - 180
        for s in range(5):
            color = COLOR_STAR_FILLED if s < stars else COLOR_STAR_EMPTY
            pygame.draw.polygon(surface, color, draw_star_points(
                star_x + s * 22, y + 18, 8))

        # Letter grade
        grade = score_data.get('grade', '')
        if grade:
            gcolor = GRADE_COLORS.get(grade, COLOR_WHITE)
            draw_text(surface, grade, (x + w - 60, y + 10), self.song_font,
                      gcolor)

        # High score number
        if 'score' in score_data:
            draw_text(surface, f"{score_data['score']:,}",
                      (x + w - 180, y + 42), self.small_font, COLOR_GRAY)

        # ── Mini piano-roll preview (right side of selected card) ────
        if selected:
            self._draw_mini_preview(surface, song, x + w - 155, y + 34, 90, 28)

    def _draw_mini_preview(self, surface, song, px, py, pw, ph):
        """Draw a tiny piano-roll thumbnail for the selected song."""
        if not song.notes:
            return
        preview_rect = pygame.Rect(px, py, pw, ph)
        pygame.draw.rect(surface, (15, 5, 30), preview_rect, border_radius=3)
        pygame.draw.rect(surface, (60, 40, 80), preview_rect, 1, border_radius=3)

        midis = [n.midi for n in song.notes]
        lo, hi = min(midis), max(midis)
        if lo == hi:
            hi = lo + 1
        total_time = song.notes[-1].start_time - song.notes[0].start_time
        if total_time <= 0:
            total_time = 1.0
        start_time = song.notes[0].start_time

        for note in song.notes:
            nx = px + 2 + int((note.start_time - start_time) / total_time * (pw - 4))
            ny = py + ph - 3 - int((note.midi - lo) / (hi - lo) * (ph - 6))
            octave = (note.midi // 12) - 1
            col = OCTAVE_COLORS.get(octave, (200, 200, 200))
            pygame.draw.circle(surface, col, (nx, ny), 1)


# ---------------------------------------------------------------------------
# ResultsScreen
# ---------------------------------------------------------------------------

class ResultsScreen:
    """Post-song results screen with grade, timing analysis, accuracy timeline."""

    def __init__(self, song, score_tracker, diff_mult=1.0):
        self.song = song
        self.tracker = score_tracker
        self.diff_mult = diff_mult
        self._anim_time = 0.0

        # Lazy fonts
        self.title_font = None
        self.big_font = None
        self.grade_font = None
        self.font = None
        self.small_font = None

    def _ensure_fonts(self):
        if self.title_font is None:
            self.title_font = get_title_font(30)
            self.big_font = get_title_font(40)
            self.grade_font = get_title_font(72)
            self.font = get_font(20)
            self.small_font = get_font(15)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                return "continue"
            elif event.key == pygame.K_r:
                return "retry"
        return None

    def update(self, dt):
        self._anim_time += dt

    def draw(self, surface):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        # Title
        draw_text(surface, "SONG COMPLETE!", (cx, 35), self.title_font,
                  COLOR_ACCENT, center=True, shadow=True)
        draw_text(surface, self.song.title, (cx, 70), get_font(20),
                  COLOR_WHITE, center=True)

        # ── Large letter grade (drops in from above with ease-out) ───
        grade = self.tracker.letter_grade
        gcolor = GRADE_COLORS.get(grade, COLOR_WHITE)
        grade_target_y = 135
        grade_drop_duration = 0.6
        if self._anim_time < grade_drop_duration:
            t = self._anim_time / grade_drop_duration
            ease = 1.0 - (1.0 - t) ** 3  # ease-out cubic
            grade_y = int(-60 + (grade_target_y + 60) * ease)
        else:
            grade_y = grade_target_y
        draw_text(surface, grade, (cx, grade_y), self.grade_font,
                  gcolor, center=True, shadow=True)

        # ── Stars (animated reveal) ──────────────────────────────────
        star_y = 190
        stars = self.tracker.stars
        for i in range(5):
            delay = i * 0.3
            if self._anim_time > delay:
                filled = i < stars
                color = COLOR_STAR_FILLED if filled else COLOR_STAR_EMPTY
                size = 22
                elapsed = self._anim_time - delay
                if elapsed < 0.3 and filled:
                    scale = 1.0 + 0.3 * math.sin(elapsed * math.pi / 0.3)
                    size = int(size * scale)
                pts = draw_star_points(cx - 100 + i * 50, star_y, size)
                pygame.draw.polygon(surface, color, pts)

        # ── Score ────────────────────────────────────────────────────
        draw_text(surface, f"Score: {self.tracker.score:,}", (cx, 235),
                  self.big_font, COLOR_WHITE, center=True, shadow=True)

        draw_text(surface, f"Max Streak: {self.tracker.max_streak}",
                  (cx, 285), self.font, COLOR_STREAK_FLAME, center=True)

        # ── Difficulty multiplier ────────────────────────────────────
        if self.diff_mult > 1.0:
            draw_text(surface, f"Difficulty Bonus: x{self.diff_mult:.1f}",
                      (cx, 310), self.small_font, COLOR_GRAY, center=True)

        # ── Breakdown ────────────────────────────────────────────────
        y = 340
        breakdown = [
            (f"Perfect: {self.tracker.perfects}", COLOR_PERFECT),
            (f"Good: {self.tracker.goods}", COLOR_GOOD),
            (f"OK: {self.tracker.oks}", COLOR_OK),
            (f"Miss: {self.tracker.misses}", COLOR_MISS),
        ]
        bx_left = cx - 160
        bx_right = cx + 20
        for idx, (text, color) in enumerate(breakdown):
            bx = bx_left if idx % 2 == 0 else bx_right
            by = y + (idx // 2) * 28
            draw_text(surface, text, (bx, by), self.font, color)
        y += 60

        # Wrong notes
        wrong_count = len(self.tracker.wrong_notes)
        if wrong_count > 0:
            draw_text(surface, f"Wrong Notes: {wrong_count}", (cx, y),
                      self.font, (255, 80, 80), center=True)
            y += 28

        # Accuracy percentage
        pct = self.tracker.percentage * 100
        draw_text(surface, f"Accuracy: {pct:.1f}%", (cx, y), self.font,
                  COLOR_ACCENT, center=True)
        y += 30

        # ── Timing analysis ──────────────────────────────────────────
        early = self.tracker.early_count
        late = self.tracker.late_count
        if early > late:
            tendency = "early"
        elif late > early:
            tendency = "late"
        else:
            tendency = "on time"
        draw_text(surface, f"You tend to play {tendency}",
                  (cx, y), self.small_font, COLOR_GRAY, center=True)
        y += 30

        # ── Accuracy timeline ────────────────────────────────────────
        y = self._draw_accuracy_timeline(surface, y)

        # Continue prompt
        draw_text(surface, "Press ENTER to continue, R to retry",
                  (cx, SCREEN_HEIGHT - 35), self.small_font,
                  COLOR_DARK_GRAY, center=True)

    def _draw_accuracy_timeline(self, surface, y):
        """Draw a horizontal bar with per-note accuracy dots (green/yellow/blue/red)."""
        cx = SCREEN_WIDTH // 2
        timeline_x = 60
        timeline_w = SCREEN_WIDTH - 120
        timeline_y = y + 5
        timeline_h = 14

        # Background bar
        pygame.draw.rect(surface, (30, 15, 50),
                         (timeline_x, timeline_y, timeline_w, timeline_h),
                         border_radius=4)

        results = self.tracker.note_results
        if results:
            judgment_colors = {
                "perfect": COLOR_PERFECT,
                "good": COLOR_GOOD,
                "ok": COLOR_OK,
                "miss": COLOR_MISS,
            }
            n = len(results)
            for idx_r, nr in enumerate(results):
                dot_x = timeline_x + 2 + int(idx_r / max(n - 1, 1) * (timeline_w - 4))
                dot_y = timeline_y + timeline_h // 2
                col = judgment_colors.get(nr.get("judgment", "miss"), COLOR_MISS)
                pygame.draw.circle(surface, col, (dot_x, dot_y), 3)

        y = timeline_y + timeline_h + 15

        # Label
        draw_text(surface, "Accuracy Timeline", (cx, y), self.small_font,
                  COLOR_DARK_GRAY, center=True)

        return y + 20


# ---------------------------------------------------------------------------
# SettingsMenu
# ---------------------------------------------------------------------------

class SettingsMenu:
    """Settings screen for audio device, calibration, display toggles, etc."""

    def __init__(self, settings, audio_devices, audio_level_callback=None):
        self.settings = settings
        self.devices = audio_devices  # list of (index, name, channels, sr)
        self.audio_level_cb = audio_level_callback  # callable returning 0.0-1.0

        # Lazy fonts
        self.font = None
        self.title_font = None
        self.small_font = None
        self.label_font = None

        self.selected = 0
        self.items = self._build_items()

    def _ensure_fonts(self):
        if self.font is None:
            self.font = get_font(22)
            self.title_font = get_title_font(36)
            self.small_font = get_font(14)
            self.label_font = get_font(16)

    def _build_items(self):
        items = []

        # Audio Input device
        device_names = ["System Default"] + [d[1] for d in self.devices]
        current_dev = self.settings.get('audio_device')
        dev_idx = 0
        if current_dev is not None:
            for i, d in enumerate(self.devices):
                if d[0] == current_dev:
                    dev_idx = i + 1
                    break
        items.append({
            'label': 'Audio Input',
            'type': 'choice',
            'choices': device_names,
            'value': dev_idx,
        })

        # Latency offset
        items.append({
            'label': 'Latency Offset',
            'type': 'slider',
            'min': -100,
            'max': 100,
            'value': int(self.settings.get('calibration_offset', 0) * 1000),
            'suffix': 'ms',
        })

        # Show Note Names
        items.append({
            'label': 'Show Note Names',
            'type': 'toggle',
            'value': self.settings.get('show_note_names', True),
        })

        # Sound Effects
        items.append({
            'label': 'Sound Effects',
            'type': 'toggle',
            'value': self.settings.get('sfx_enabled', True),
        })

        # Audio Passthrough
        items.append({
            'label': 'Audio Passthrough',
            'type': 'toggle',
            'value': self.settings.get('passthrough_enabled', False),
        })

        # Show Timing Bar
        items.append({
            'label': 'Show Timing Bar',
            'type': 'toggle',
            'value': self.settings.get('show_timing_bar', True),
        })

        # Show Score Popups
        items.append({
            'label': 'Show Score Popups',
            'type': 'toggle',
            'value': self.settings.get('show_score_popups', True),
        })

        # 3D Perspective
        items.append({
            'label': '3D Perspective',
            'type': 'toggle',
            'value': self.settings.get('perspective_3d', True),
        })

        # Wait Mode
        items.append({
            'label': 'Wait Mode',
            'type': 'toggle',
            'value': self.settings.get('wait_mode', False),
        })

        # No Fail Mode
        items.append({
            'label': 'No Fail Mode',
            'type': 'toggle',
            'value': self.settings.get('no_fail', True),
        })

        # Auto-Calibrate
        items.append({
            'label': 'Auto-Calibrate',
            'type': 'action',
            'action': 'calibrate',
        })

        # Reset to Defaults
        items.append({
            'label': 'Reset to Defaults',
            'type': 'action',
            'action': 'reset_defaults',
        })

        # Back
        items.append({
            'label': 'Back',
            'type': 'action',
            'action': 'back',
        })

        return items

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(self.items)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(self.items)
        elif event.key == pygame.K_ESCAPE:
            return "back"
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            item = self.items[self.selected]
            if item['type'] == 'action':
                action = item.get('action', 'back')
                if action == 'reset_defaults':
                    self._reset_defaults()
                    return None
                return action
            elif item['type'] == 'toggle':
                item['value'] = not item['value']
                self._apply()
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            item = self.items[self.selected]
            delta = 1 if event.key == pygame.K_RIGHT else -1
            if item['type'] == 'choice':
                item['value'] = (item['value'] + delta) % len(item['choices'])
                self._apply()
            elif item['type'] == 'slider':
                step = 5
                item['value'] = max(item['min'],
                                     min(item['max'], item['value'] + delta * step))
                self._apply()
        return None

    def _apply(self):
        """Apply current values to settings dict."""
        dev_choice = self.items[0]['value']
        if dev_choice == 0:
            self.settings['audio_device'] = None
        else:
            self.settings['audio_device'] = self.devices[dev_choice - 1][0]

        self.settings['calibration_offset'] = self.items[1]['value'] / 1000.0
        self.settings['show_note_names'] = self.items[2]['value']
        self.settings['sfx_enabled'] = self.items[3]['value']
        self.settings['passthrough_enabled'] = self.items[4]['value']
        self.settings['show_timing_bar'] = self.items[5]['value']
        self.settings['show_score_popups'] = self.items[6]['value']
        self.settings['perspective_3d'] = self.items[7]['value']
        self.settings['wait_mode'] = self.items[8]['value']
        self.settings['no_fail'] = self.items[9]['value']

    def _reset_defaults(self):
        """Reset all settings to defaults and rebuild items."""
        self.settings['audio_device'] = None
        self.settings['calibration_offset'] = 0.0
        self.settings['show_note_names'] = True
        self.settings['sfx_enabled'] = True
        self.settings['passthrough_enabled'] = False
        self.settings['show_timing_bar'] = True
        self.settings['show_score_popups'] = True
        self.settings['perspective_3d'] = True
        self.settings['wait_mode'] = False
        self.settings['no_fail'] = True
        self.items = self._build_items()

    def draw(self, surface, input_level=0.0):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        draw_text(surface, "SETTINGS", (cx, 40), self.title_font,
                  COLOR_ACCENT, center=True)

        # Input level meter at top right
        if input_level > 0:
            meter_x = SCREEN_WIDTH - 50
            meter_h = 60
            meter_y = 40
            pygame.draw.rect(surface, COLOR_DARK_GRAY, (meter_x, meter_y, 20, meter_h))
            fill = int(meter_h * min(1.0, input_level * 10))
            if fill > 0:
                color = (0, 255, 0) if input_level > 0.005 else (80, 80, 80)
                pygame.draw.rect(surface, color,
                                 (meter_x, meter_y + meter_h - fill, 20, fill))
            draw_text(surface, "IN", (meter_x + 10, meter_y + meter_h + 5),
                      self.small_font, COLOR_GRAY, center=True)

        y = 120
        for i, item in enumerate(self.items):
            selected = i == self.selected
            color = COLOR_WHITE if selected else COLOR_GRAY

            if item['type'] == 'action':
                label = item['label']
                if selected:
                    draw_text(surface, ">", (cx - 140, y), self.font,
                              COLOR_ACCENT, center=True)
                draw_text(surface, label, (cx, y), self.font, color, center=True)
            elif item['type'] == 'choice':
                label = f"{item['label']}: < {item['choices'][item['value']]} >"
                draw_text(surface, label, (cx, y), self.font, color, center=True)
            elif item['type'] == 'slider':
                val = item['value']
                label = f"{item['label']}: < {val}{item['suffix']} >"
                draw_text(surface, label, (cx, y), self.font, color, center=True)
            elif item['type'] == 'toggle':
                state = "ON" if item['value'] else "OFF"
                label = f"{item['label']}: < {state} >"
                draw_text(surface, label, (cx, y), self.font, color, center=True)

            if selected and item['type'] != 'action':
                draw_text(surface, ">", (cx - 220, y), self.font,
                          COLOR_ACCENT, center=True)

            y += 48

        # ── Live input level meter ───────────────────────────────────
        meter_y = SCREEN_HEIGHT - 80
        meter_w = 400
        meter_h = 16
        meter_x = (SCREEN_WIDTH - meter_w) // 2

        draw_text(surface, "Input Level", (cx, meter_y - 12), self.small_font,
                  COLOR_DARK_GRAY, center=True)
        pygame.draw.rect(surface, (30, 15, 50),
                         (meter_x, meter_y, meter_w, meter_h), border_radius=4)

        level = 0.0
        if self.audio_level_cb:
            try:
                level = max(0.0, min(1.0, self.audio_level_cb()))
            except Exception:
                level = 0.0

        if level > 0:
            fill_w = int(level * (meter_w - 4))
            bar_color = lerp_color((0, 200, 100), (255, 50, 50), level)
            pygame.draw.rect(surface, bar_color,
                             (meter_x + 2, meter_y + 2, fill_w, meter_h - 4),
                             border_radius=3)

        # Instructions
        draw_text(surface, "UP/DOWN navigate | LEFT/RIGHT change | ENTER select | ESC back",
                  (cx, SCREEN_HEIGHT - 30), self.small_font,
                  COLOR_DARK_GRAY, center=True)


# ---------------------------------------------------------------------------
# CalibrationScreen
# ---------------------------------------------------------------------------

class CalibrationScreen:
    """Auto-calibration screen: play on each beat, compute latency offset."""

    BEATS = 4
    BPM = 100
    BEAT_INTERVAL = 60.0 / BPM

    def __init__(self):
        # Lazy fonts
        self.title_font = None
        self.font = None
        self.big_font = None
        self.small_font = None

        self.state = "waiting"  # waiting | listening | done
        self.beat_index = 0
        self._anim_time = 0.0
        self._beat_timer = 0.0
        self._onset_times = []
        self._beat_times = []
        self._computed_offset = 0.0
        self._selected_button = 0  # 0=Accept, 1=Cancel

    def _ensure_fonts(self):
        if self.title_font is None:
            self.title_font = get_title_font(36)
            self.font = get_font(22)
            self.big_font = get_title_font(48)
            self.small_font = get_font(16)

    def start(self):
        """Start the calibration listening phase."""
        self.state = "listening"
        self.beat_index = 0
        self._anim_time = 0.0
        self._beat_timer = 0.0
        self._onset_times = []
        self._beat_times = []
        self._computed_offset = 0.0

    def record_onset(self, timestamp):
        """Record an onset time from the audio system."""
        if self.state == "listening":
            self._onset_times.append(timestamp)

    def handle_event(self, event):
        """Returns 'accept', 'cancel', or None."""
        if event.type != pygame.KEYDOWN:
            return None

        if self.state == "waiting":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start()
            elif event.key == pygame.K_ESCAPE:
                return "cancel"
        elif self.state == "done":
            if event.key == pygame.K_LEFT:
                self._selected_button = 0
            elif event.key == pygame.K_RIGHT:
                self._selected_button = 1
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return "accept" if self._selected_button == 0 else "cancel"
            elif event.key == pygame.K_ESCAPE:
                return "cancel"
        return None

    def update(self, dt):
        self._anim_time += dt
        if self.state == "listening":
            self._beat_timer += dt
            if self._beat_timer >= self.BEAT_INTERVAL:
                self._beat_timer -= self.BEAT_INTERVAL
                self._beat_times.append(self._anim_time)
                self.beat_index += 1
                if self.beat_index >= self.BEATS:
                    self._finish_calibration()

    def _finish_calibration(self):
        """Compute the offset from collected onset and beat times."""
        self.state = "done"
        if not self._onset_times or not self._beat_times:
            self._computed_offset = 0.0
            return
        # Match each beat to nearest onset
        offsets = []
        for bt in self._beat_times:
            nearest = min(self._onset_times, key=lambda o: abs(o - bt))
            offsets.append(nearest - bt)
        self._computed_offset = sum(offsets) / len(offsets)

    @property
    def computed_offset_ms(self):
        return self._computed_offset * 1000.0

    def draw(self, surface):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        draw_text(surface, "AUDIO CALIBRATION", (cx, 50), self.title_font,
                  COLOR_ACCENT, center=True, shadow=True)

        if self.state == "waiting":
            draw_text(surface, "Play a note on each beat!",
                      (cx, 180), self.font, COLOR_WHITE, center=True)
            draw_text(surface, "Press ENTER to start",
                      (cx, 240), self.small_font, COLOR_GRAY, center=True)

        elif self.state == "listening":
            draw_text(surface, "Play a note on each beat!",
                      (cx, 150), self.font, COLOR_WHITE, center=True)

            # Visual metronome — 4 circles
            metro_y = 300
            spacing = 100
            start_x = cx - (self.BEATS - 1) * spacing // 2
            for b in range(self.BEATS):
                bx = start_x + b * spacing
                if b < self.beat_index:
                    # Past beat
                    pygame.draw.circle(surface, COLOR_ACCENT, (bx, metro_y), 30)
                    draw_text(surface, str(b + 1), (bx, metro_y), self.font,
                              COLOR_BLACK, center=True)
                elif b == self.beat_index:
                    # Current beat — pulsing
                    pulse = abs(math.sin(self._anim_time * 6.0))
                    radius = int(30 + 8 * pulse)
                    pygame.draw.circle(surface, COLOR_ACCENT, (bx, metro_y), radius)
                    draw_text(surface, str(b + 1), (bx, metro_y), self.font,
                              COLOR_BLACK, center=True)
                else:
                    # Future beat
                    pygame.draw.circle(surface, COLOR_DARK_GRAY, (bx, metro_y), 30, 2)
                    draw_text(surface, str(b + 1), (bx, metro_y), self.font,
                              COLOR_DARK_GRAY, center=True)

            draw_text(surface, f"Beat {min(self.beat_index + 1, self.BEATS)} / {self.BEATS}",
                      (cx, 380), self.small_font, COLOR_GRAY, center=True)

        elif self.state == "done":
            offset_ms = self.computed_offset_ms
            draw_text(surface, "Calibration Complete!", (cx, 160), self.font,
                      COLOR_ACCENT, center=True)
            draw_text(surface, f"Detected Offset: {offset_ms:+.1f} ms",
                      (cx, 220), self.big_font, COLOR_WHITE, center=True, shadow=True)

            if abs(offset_ms) < 10:
                note = "Your setup has great timing!"
            elif offset_ms > 0:
                note = "Your input arrives slightly late."
            else:
                note = "Your input arrives slightly early."
            draw_text(surface, note, (cx, 290), self.small_font,
                      COLOR_GRAY, center=True)

            # Accept / Cancel buttons
            btn_y = 370
            for bi, blabel in enumerate(["Accept", "Cancel"]):
                bx = cx - 100 + bi * 200
                if bi == self._selected_button:
                    bcolor = COLOR_ACCENT
                    pygame.draw.rect(surface, (0, 200, 255, 40),
                                     pygame.Rect(bx - 60, btn_y - 15, 120, 36),
                                     border_radius=6)
                else:
                    bcolor = COLOR_GRAY
                draw_text(surface, blabel, (bx, btn_y), self.font,
                          bcolor, center=True)

            draw_text(surface, "LEFT/RIGHT to select, ENTER to confirm",
                      (cx, SCREEN_HEIGHT - 40), self.small_font,
                      COLOR_DARK_GRAY, center=True)


# ---------------------------------------------------------------------------
# StatsScreen
# ---------------------------------------------------------------------------

class StatsScreen:
    """Player statistics overview."""

    def __init__(self, stats=None):
        self.stats = stats if stats is not None else load_stats()
        # Lazy fonts
        self.title_font = None
        self.font = None
        self.small_font = None
        self.label_font = None
        self.value_font = None

        self.stats = load_stats()

    def _ensure_fonts(self):
        if self.title_font is None:
            self.title_font = get_title_font(36)
            self.font = get_font(20)
            self.small_font = get_font(14)
            self.label_font = get_font(16)
            self.value_font = get_font(22, bold=True)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "back"
        return None

    def update(self, dt):
        pass

    def draw(self, surface):
        self._ensure_fonts()
        surface.fill(MENU_BG)
        cx = SCREEN_WIDTH // 2

        draw_text(surface, "PLAYER STATS", (cx, 40), self.title_font,
                  COLOR_ACCENT, center=True, shadow=True)

        s = self.stats
        avg_acc = get_average_accuracy(s)

        # Format play time
        total_secs = int(s.get("total_play_time", 0))
        hours = total_secs // 3600
        minutes = (total_secs % 3600) // 60
        secs = total_secs % 60
        if hours > 0:
            time_str = f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            time_str = f"{minutes}m {secs}s"
        else:
            time_str = f"{secs}s"

        # Stat rows: (label, value, color)
        rows = [
            ("Songs Played / Completed",
             f"{s.get('total_songs_played', 0)} / {s.get('total_songs_completed', 0)}",
             COLOR_WHITE),
            ("Total Notes Hit / Missed",
             f"{s.get('total_notes_hit', 0)} / {s.get('total_notes_missed', 0)}",
             COLOR_WHITE),
            ("Total Play Time", time_str, COLOR_ACCENT),
            ("Best Ever Streak", str(s.get("best_streak", 0)), COLOR_STREAK_FLAME),
            ("Five-Star Songs", str(s.get("five_star_count", 0)), COLOR_STAR_FILLED),
            ("Average Accuracy", f"{avg_acc * 100:.1f}%", COLOR_ACCENT),
        ]

        y = 105
        col_label_x = cx - 200
        col_value_x = cx + 140
        for label, value, vcolor in rows:
            draw_text(surface, label, (col_label_x, y), self.font, COLOR_GRAY)
            draw_text(surface, value, (col_value_x, y), self.value_font, vcolor)
            y += 42

        # ── Accuracy trend (last 10 sessions) ────────────────────────
        y += 15
        draw_text(surface, "Recent Accuracy Trend", (cx, y), self.font,
                  COLOR_ACCENT, center=True)
        y += 30

        history = s.get("accuracy_history", [])
        recent = history[-10:] if history else []

        if recent:
            bar_area_w = 500
            bar_area_x = (SCREEN_WIDTH - bar_area_w) // 2
            bar_h = 100
            bar_w = bar_area_w // max(len(recent), 1) - 6
            max_bar_w = 40
            bar_w = min(bar_w, max_bar_w)
            total_bars_w = len(recent) * (bar_w + 6) - 6
            start_x = (SCREEN_WIDTH - total_bars_w) // 2

            # Background
            pygame.draw.rect(surface, (25, 10, 45),
                             (start_x - 10, y, total_bars_w + 20, bar_h + 30),
                             border_radius=6)

            for idx, entry in enumerate(recent):
                acc = entry.get("accuracy", 0.0)
                bx = start_x + idx * (bar_w + 6)
                filled_h = int(acc * bar_h)
                bar_color = lerp_color((255, 50, 50), (0, 255, 100), acc)

                # Bar
                pygame.draw.rect(surface, bar_color,
                                 (bx, y + bar_h - filled_h + 5, bar_w, filled_h),
                                 border_radius=2)

                # Percentage label
                draw_text(surface, f"{int(acc * 100)}%",
                          (bx + bar_w // 2, y + bar_h + 10), self.small_font,
                          COLOR_DARK_GRAY, center=True)
        else:
            draw_text(surface, "No sessions recorded yet.", (cx, y + 30),
                      self.small_font, COLOR_DARK_GRAY, center=True)

        # Footer
        draw_text(surface, "Press ESC to go back",
                  (cx, SCREEN_HEIGHT - 35), self.small_font,
                  COLOR_DARK_GRAY, center=True)
