"""Heads-up display -- score, streak, combo announcements, timing bar,
wrong-note feedback, live accuracy, and keyboard shortcut hints."""

import math
import time
import pygame
from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, HIGHWAY_WIDTH_RATIO,
    COLOR_WHITE, COLOR_ACCENT, COLOR_PERFECT, COLOR_GOOD, COLOR_OK, COLOR_MISS,
    COLOR_STREAK_FLAME, COLOR_STAR_FILLED, COLOR_STAR_EMPTY,
    COLOR_GRAY, COLOR_DARK_GRAY, KEYBOARD_HEIGHT, COLOR_EARLY, COLOR_LATE,
    COLOR_WRONG_NOTE, COMBO_MILESTONES,
    COLOR_HEALTH_GREEN, COLOR_HEALTH_YELLOW, COLOR_HEALTH_RED,
    COLOR_STAR_POWER,
)
from piano_hero.ui.renderer import get_font, get_title_font, draw_text


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

JUDGMENT_COLORS = {
    "perfect": COLOR_PERFECT,
    "good": COLOR_GOOD,
    "ok": COLOR_OK,
    "miss": COLOR_MISS,
}

JUDGMENT_DISPLAY = {
    "perfect": "PERFECT!",
    "good": "GOOD!",
    "ok": "OK",
    "miss": "MISS",
}


class HUD:
    """Renders score, streak, combo announcements, timing bar, accuracy,
    wrong-note feedback, and keyboard shortcut hints."""

    def __init__(self):
        self.panel_x = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        self.panel_width = SCREEN_WIDTH - self.panel_x
        self._fonts_init = False

    # ------------------------------------------------------------------
    # Lazy font initialisation
    # ------------------------------------------------------------------

    def _ensure_fonts(self):
        if not self._fonts_init:
            self.score_font = get_title_font(36)
            self.label_font = get_font(16)
            self.streak_font = get_title_font(28)
            self.judgment_font = get_title_font(32)
            self.multiplier_font = get_font(20, bold=True)
            self.small_font = get_font(14)
            self.combo_font = get_title_font(44)
            self.wrong_font = get_font(13)
            self.hint_font = get_font(12)
            self._fonts_init = True

    # ------------------------------------------------------------------
    # Main draw
    # ------------------------------------------------------------------

    def draw(self, surface, score_tracker, game_session):
        """Draw the full HUD panel on the right side of the screen."""
        self._ensure_fonts()

        # Panel background
        panel_rect = pygame.Rect(
            self.panel_x, 0, self.panel_width, SCREEN_HEIGHT - KEYBOARD_HEIGHT
        )
        pygame.draw.rect(surface, (20, 5, 40), panel_rect)
        pygame.draw.line(
            surface, (50, 30, 80),
            (self.panel_x, 0), (self.panel_x, SCREEN_HEIGHT), 2,
        )

        cx = self.panel_x + self.panel_width // 2
        y = 30

        # -- Song title ----------------------------------------------------
        title = game_session.song.title
        if len(title) > 18:
            title = title[:16] + ".."
        draw_text(surface, title, (cx, y), self.label_font, COLOR_ACCENT,
                  center=True)
        y += 30

        # -- Score ---------------------------------------------------------
        draw_text(surface, "SCORE", (cx, y), self.small_font, COLOR_GRAY,
                  center=True)
        y += 18
        draw_text(surface, f"{score_tracker.score:,}", (cx, y),
                  self.score_font, COLOR_WHITE, center=True, shadow=True)
        y += 45

        # -- Live accuracy % ----------------------------------------------
        total_judged = (score_tracker.perfects + score_tracker.goods
                        + score_tracker.oks + score_tracker.misses)
        if total_judged > 0:
            accuracy = score_tracker.notes_hit / total_judged * 100
            if accuracy >= 90:
                acc_color = COLOR_PERFECT
            elif accuracy >= 70:
                acc_color = COLOR_GOOD
            elif accuracy >= 50:
                acc_color = COLOR_OK
            else:
                acc_color = COLOR_MISS
            draw_text(surface, f"{accuracy:.1f}%", (cx, y),
                      self.multiplier_font, acc_color, center=True)
        y += 28

        # -- Multiplier ----------------------------------------------------
        if score_tracker.multiplier > 1.0:
            draw_text(surface, f"x{score_tracker.multiplier:.1f}", (cx, y),
                      self.multiplier_font, COLOR_ACCENT, center=True)
        y += 30

        # -- Streak --------------------------------------------------------
        draw_text(surface, "STREAK", (cx, y), self.small_font, COLOR_GRAY,
                  center=True)
        y += 18
        streak_color = (
            COLOR_STREAK_FLAME if score_tracker.streak >= 10 else COLOR_WHITE
        )
        draw_text(surface, str(score_tracker.streak), (cx, y),
                  self.streak_font, streak_color, center=True, shadow=True)
        y += 40

        # -- Latest judgment + early/late label ----------------------------
        recent = game_session.get_recent_judgments(0.8)
        if recent:
            latest = recent[-1]
            text = JUDGMENT_DISPLAY.get(latest.judgment, "")
            color = JUDGMENT_COLORS.get(latest.judgment, COLOR_WHITE)
            age = game_session.current_time - latest.time
            alpha = max(0, 255 - int(age * 300))
            if alpha > 0:
                judge_surf = self.judgment_font.render(text, True, color)
                judge_surf.set_alpha(alpha)
                rect = judge_surf.get_rect(center=(cx, y))
                surface.blit(judge_surf, rect)

                # Early / late sub-label
                el = getattr(latest, "early_late", "")
                if el and el != "perfect":
                    el_color = COLOR_EARLY if el == "early" else COLOR_LATE
                    el_surf = self.small_font.render(el.upper(), True, el_color)
                    el_surf.set_alpha(alpha)
                    el_rect = el_surf.get_rect(center=(cx, y + 28))
                    surface.blit(el_surf, el_rect)
        y += 55

        # -- Timing tendency bar -------------------------------------------
        self._draw_timing_bar(surface, score_tracker, cx, y)
        y += 30

        # -- Stats ---------------------------------------------------------
        draw_text(surface, "\u2500" * 15, (cx, y), self.small_font,
                  COLOR_DARK_GRAY, center=True)
        y += 22
        for stat_text, stat_color in [
            (f"Perfect: {score_tracker.perfects}", COLOR_PERFECT),
            (f"Good: {score_tracker.goods}", COLOR_GOOD),
            (f"OK: {score_tracker.oks}", COLOR_OK),
            (f"Miss: {score_tracker.misses}", COLOR_MISS),
        ]:
            draw_text(surface, stat_text, (cx, y), self.small_font,
                      stat_color, center=True)
            y += 20

        # -- Progress bar --------------------------------------------------
        y += 15
        draw_text(surface, "PROGRESS", (cx, y), self.small_font, COLOR_GRAY,
                  center=True)
        y += 16
        bar_w = self.panel_width - 40
        bar_x = self.panel_x + 20
        bar_h = 8
        pygame.draw.rect(surface, COLOR_DARK_GRAY,
                         (bar_x, y, bar_w, bar_h), border_radius=4)
        total_notes = len(game_session.notes)
        hit_notes = sum(1 for n in game_session.notes if n.hit)
        if total_notes > 0:
            fill_w = int(bar_w * hit_notes / total_notes)
            if fill_w > 0:
                pygame.draw.rect(surface, COLOR_ACCENT,
                                 (bar_x, y, fill_w, bar_h), border_radius=4)

        # -- Persistent control hints (always visible) ---------------------
        hint_y = SCREEN_HEIGHT - KEYBOARD_HEIGHT - 12
        draw_text(surface, "P:Pause  SPACE:StarPower  ESC:Quit",
                  (cx, hint_y), self.hint_font, (50, 40, 60), center=True)

        # -- Wrong note display with penalty --------------------------------
        if hasattr(game_session, "get_recent_wrong_notes"):
            wrong = game_session.get_recent_wrong_notes(1.5)
            if wrong:
                latest_wrong = wrong[-1]
                age = game_session.current_time - latest_wrong.time
                alpha = max(0, 255 - int(age * 170))
                expected = getattr(latest_wrong, "expected_name", "")
                if alpha > 0 and expected:
                    penalty = getattr(latest_wrong, "penalty", 0)
                    wtext = (
                        f"Played {latest_wrong.played_name}, "
                        f"need {expected}"
                    )
                    wsurf = self.wrong_font.render(wtext, True, COLOR_WRONG_NOTE)
                    wsurf.set_alpha(alpha)
                    wy = SCREEN_HEIGHT - KEYBOARD_HEIGHT - 25
                    wrect = wsurf.get_rect(center=(cx, wy))
                    surface.blit(wsurf, wrect)
                    # Show penalty amount
                    if penalty != 0:
                        ptext = f"{penalty}"
                        psurf = self.wrong_font.render(ptext, True, COLOR_MISS)
                        psurf.set_alpha(alpha)
                        prect = psurf.get_rect(center=(cx, wy + 18))
                        surface.blit(psurf, prect)

        # -- Hold bonus display -------------------------------------------
        if hasattr(game_session, "get_recent_hold_events"):
            holds = game_session.get_recent_hold_events(1.2)
            for hold_ev in holds:
                if hold_ev.hold_bonus > 0:
                    age = game_session.current_time - hold_ev.time
                    alpha = max(0, 255 - int(age * 200))
                    if alpha > 0:
                        htext = f"+{hold_ev.hold_bonus} hold"
                        color = COLOR_PERFECT if hold_ev.hold_ratio > 0.8 else COLOR_GOOD
                        hsurf = self.small_font.render(htext, True, color)
                        hsurf.set_alpha(alpha)
                        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
                        rise = int(30 * age)
                        hrect = hsurf.get_rect(
                            center=(hw // 2, SCREEN_HEIGHT // 2 + 40 - rise))
                        surface.blit(hsurf, hrect)

        # -- Combo announcements (big centered text over highway) ----------
        # -- Health meter (left edge of highway) --------------------------
        self._draw_health_meter(surface, game_session)

        # -- Star Power meter (below health) ------------------------------
        self._draw_star_power_meter(surface, game_session)

        # -- Wait mode indicator ------------------------------------------
        if getattr(game_session, '_waiting', False):
            hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
            wait_font = get_title_font(32)
            pulse = 0.5 + 0.5 * math.sin(time.time() * 3)
            alpha = int(180 + 75 * pulse)
            wait_surf = wait_font.render("WAITING...", True, COLOR_ACCENT)
            wait_surf.set_alpha(alpha)
            wait_rect = wait_surf.get_rect(center=(hw // 2, self.highway_height - 40))
            surface.blit(wait_surf, wait_rect)

        self._draw_combo_announcements(surface, game_session)

    # ------------------------------------------------------------------
    # Timing tendency bar
    # ------------------------------------------------------------------

    def _draw_health_meter(self, surface, game_session):
        """Draw a vertical health bar on the left edge of the highway."""
        health = getattr(game_session, 'health', 0.5)
        bar_x = 8
        bar_w = 18
        bar_h = int(self.highway_height * 0.5)
        bar_y = 60

        # Background
        pygame.draw.rect(surface, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h),
                         border_radius=3)
        # Fill
        fill_h = int(bar_h * health)
        if fill_h > 0:
            if health > 0.6:
                color = COLOR_HEALTH_GREEN
            elif health > 0.3:
                color = COLOR_HEALTH_YELLOW
            else:
                color = COLOR_HEALTH_RED
            pygame.draw.rect(surface, color,
                             (bar_x, bar_y + bar_h - fill_h, bar_w, fill_h),
                             border_radius=3)
        # Border
        pygame.draw.rect(surface, (80, 80, 80), (bar_x, bar_y, bar_w, bar_h),
                         1, border_radius=3)

    def _draw_star_power_meter(self, surface, game_session):
        """Draw the star power meter below the health bar."""
        meter = getattr(game_session, 'star_power_meter', 0.0)
        active = getattr(game_session, 'star_power_active', False)
        bar_x = 8
        bar_w = 18
        bar_h = 50
        hw_h = int(self.highway_height * 0.5)
        bar_y = 60 + hw_h + 15

        # Background
        pygame.draw.rect(surface, (20, 20, 40), (bar_x, bar_y, bar_w, bar_h),
                         border_radius=3)
        # Fill
        fill_h = int(bar_h * meter)
        if fill_h > 0:
            color = COLOR_STAR_POWER if not active else (255, 255, 255)
            pygame.draw.rect(surface, color,
                             (bar_x, bar_y + bar_h - fill_h, bar_w, fill_h),
                             border_radius=3)
        # Active indicator
        if active:
            glow = pygame.Surface((bar_w + 6, bar_h + 6), pygame.SRCALPHA)
            glow.fill((0, 200, 255, 40))
            surface.blit(glow, (bar_x - 3, bar_y - 3))
        # Border
        border_color = COLOR_STAR_POWER if meter >= 0.5 else (60, 60, 60)
        pygame.draw.rect(surface, border_color, (bar_x, bar_y, bar_w, bar_h),
                         1, border_radius=3)
        # Label
        draw_text(surface, "SP", (bar_x + bar_w // 2, bar_y + bar_h + 8),
                  self.small_font, COLOR_STAR_POWER if meter >= 0.5 else COLOR_DARK_GRAY,
                  center=True)

    @property
    def highway_height(self):
        return SCREEN_HEIGHT - KEYBOARD_HEIGHT

    def _draw_timing_bar(self, surface, tracker, cx, y):
        """Draw a small horizontal bar showing early/late tendency.

        Uses tracker.early_count and tracker.late_count when available.
        """
        bar_w = self.panel_width - 50
        bar_h = 6
        bar_x = cx - bar_w // 2

        # Background track
        pygame.draw.rect(surface, COLOR_DARK_GRAY,
                         (bar_x, y, bar_w, bar_h), border_radius=3)
        # Center tick (perfect)
        pygame.draw.line(surface, COLOR_WHITE,
                         (cx, y - 2), (cx, y + bar_h + 2), 1)

        early = getattr(tracker, "early_count", 0)
        late = getattr(tracker, "late_count", 0)
        total = early + late
        if total > 0:
            bias = (late - early) / total  # -1 = all early, +1 = all late
            indicator_x = cx + int(bias * bar_w * 0.4)
            indicator_x = max(bar_x + 3, min(bar_x + bar_w - 3, indicator_x))
            if bias < -0.1:
                dot_color = COLOR_EARLY
            elif bias > 0.1:
                dot_color = COLOR_LATE
            else:
                dot_color = COLOR_PERFECT
            pygame.draw.circle(surface, dot_color,
                               (indicator_x, y + bar_h // 2), 5)

        # Labels
        draw_text(surface, "Early", (bar_x - 2, y - 2), self.small_font,
                  COLOR_DARK_GRAY)
        draw_text(surface, "Late", (bar_x + bar_w - 22, y - 2),
                  self.small_font, COLOR_DARK_GRAY)

    # ------------------------------------------------------------------
    # Combo announcements (big centred text over the highway)
    # ------------------------------------------------------------------

    def _draw_combo_announcements(self, surface, game_session):
        """Draw milestone text that scales up and fades out, centred
        over the note highway."""
        if not hasattr(game_session, "get_recent_combos"):
            return

        combos = game_session.get_recent_combos(2.0)
        if not combos:
            return

        latest_combo = combos[-1]
        age = game_session.current_time - latest_combo.time
        if age >= 2.0:
            return

        t = age / 2.0
        alpha = int(255 * (1.0 - t))

        # Pop-in scale: start at 1.4x, settle to 1.0x, then hold
        if t < 0.12:
            scale = 1.0 + 0.4 * (t / 0.12)
        elif t < 0.25:
            scale = 1.4 - 0.4 * ((t - 0.12) / 0.13)
        else:
            scale = 1.0

        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        combo_surf = self.combo_font.render(
            latest_combo.text, True, latest_combo.color
        )
        w = max(1, int(combo_surf.get_width() * scale))
        h = max(1, int(combo_surf.get_height() * scale))
        combo_scaled = pygame.transform.smoothscale(combo_surf, (w, h))
        combo_scaled.set_alpha(alpha)
        combo_rect = combo_scaled.get_rect(
            center=(hw // 2, SCREEN_HEIGHT // 2 - 80)
        )
        surface.blit(combo_scaled, combo_rect)

    # ------------------------------------------------------------------
    # Countdown
    # ------------------------------------------------------------------

    def draw_countdown(self, surface, countdown_value, lesson_tip=""):
        """Draw countdown number centred on the highway, plus shortcut hints."""
        self._ensure_fonts()

        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        cx = hw // 2
        cy = SCREEN_HEIGHT // 2 - 50

        num = max(1, int(countdown_value) + 1)
        if countdown_value <= 0:
            text, color = "GO!", COLOR_PERFECT
        else:
            text, color = str(num), COLOR_WHITE

        font = get_title_font(80)
        draw_text(surface, text, (cx, cy), font, color, center=True,
                  shadow=True)

        # Micro-lesson tip (shown during countdown, not on GO)
        if lesson_tip and countdown_value > 0.5:
            tip_font = get_font(16)
            draw_text(surface, lesson_tip, (cx, cy + 50), tip_font,
                      (150, 200, 255), center=True)

        # Keyboard shortcut hints
        draw_text(surface, "P = Pause  |  SPACE = Star Power  |  ESC = Quit", (cx, cy + 80),
                  self.hint_font, COLOR_GRAY, center=True)
