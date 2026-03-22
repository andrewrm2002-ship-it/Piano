"""Scoring system — continuous timing scores, hold bonuses, wrong note penalties."""

import json
import os
from piano_hero.constants import (
    PERFECT_POINTS, GOOD_POINTS, OK_POINTS, MISS_POINTS,
    STREAK_MILESTONE, MAX_MULTIPLIER, MULTIPLIER_STEP,
    STAR_THRESHOLDS, PERFECT_WINDOW, GOOD_WINDOW, OK_WINDOW,
    GRADE_THRESHOLDS, MISS_MULTIPLIER_DROP, MIN_MULTIPLIER,
    FIRST_NOTE_GRACE, SCORING_BANDS, WRONG_NOTE_PENALTY,
    WRONG_NOTE_STREAK_RESET, HOLD_BONUS_RATIO, HOLD_MIN_DURATION,
)


def judge_timing(time_diff: float) -> tuple[str, str]:
    """Judge timing accuracy. Returns (judgment, early_late)."""
    dt = abs(time_diff)
    if dt <= PERFECT_WINDOW:
        return ("perfect", "perfect")
    elif dt <= GOOD_WINDOW:
        early_late = "early" if time_diff < 0 else "late"
        return ("good", early_late)
    elif dt <= OK_WINDOW:
        early_late = "early" if time_diff < 0 else "late"
        return ("ok", early_late)
    return ("miss", "")


def compute_timing_score(time_diff: float) -> int:
    """Compute continuous points based on timing accuracy.

    Instead of discrete buckets (100/60/30), interpolates within each band
    so a barely-good hit scores less than an almost-perfect one.
    """
    dt = abs(time_diff)
    for inner, outer, max_pts, min_pts in SCORING_BANDS:
        if dt <= outer:
            if outer <= inner:
                return max_pts
            t = (dt - inner) / (outer - inner)  # 0 at inner edge, 1 at outer
            return int(max_pts + (min_pts - max_pts) * t)
    return 0  # miss


def judgment_points(judgment: str) -> int:
    """Return base points for a judgment tier (for display/max calculation)."""
    return {
        "perfect": PERFECT_POINTS,
        "good": GOOD_POINTS,
        "ok": OK_POINTS,
        "miss": MISS_POINTS,
    }.get(judgment, 0)


def compute_hold_bonus(base_points: int, actual_hold: float,
                       expected_hold: float) -> int:
    """Compute bonus points for holding a note for its full duration.

    Returns 0 for short notes (< HOLD_MIN_DURATION expected).
    Up to base_points * HOLD_BONUS_RATIO for a perfect hold.
    """
    if expected_hold < HOLD_MIN_DURATION:
        return 0
    hold_ratio = min(1.0, max(0.0, actual_hold / expected_hold))
    return int(base_points * HOLD_BONUS_RATIO * hold_ratio)


def get_letter_grade(percentage: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if percentage >= threshold:
            return grade
    return "F"


def compute_difficulty_score(song) -> float:
    """Compute a difficulty multiplier (1.0-2.0) for final score scaling."""
    if not song.notes or song.duration <= 0:
        return 1.0
    note_density = len(song.notes) / song.duration
    density_factor = min(note_density / 4.0, 1.0)
    tempo_factor = max(0.0, min((song.tempo - 60) / 120.0, 1.0))
    midis = [n.midi for n in song.notes]
    span = max(midis) - min(midis)
    range_factor = min(span / 36.0, 1.0)
    unique_count = len(set(midis))
    unique_factor = max(0.0, min((unique_count - 5) / 15.0, 1.0))
    combined = (density_factor * 0.35 + tempo_factor * 0.25
                + range_factor * 0.20 + unique_factor * 0.20)
    return 1.0 + max(0.0, min(combined, 1.0))


class ScoreTracker:
    """Tracks score with continuous timing, hold bonuses, and wrong note penalties."""

    def __init__(self, total_notes: int):
        self.total_notes = total_notes
        self.score = 0
        self.streak = 0
        self.max_streak = 0
        self.multiplier = 1.0
        self.perfects = 0
        self.goods = 0
        self.oks = 0
        self.misses = 0

        # Extended statistics
        self.early_count = 0
        self.late_count = 0
        self.wrong_notes: list[tuple[int, int]] = []
        self.wrong_note_penalties = 0
        self.total_hold_bonus = 0
        self.note_results: list[dict] = []

        # Compute realistic max (perfect run with hold bonuses)
        self.max_possible = 0
        sim_streak = 0
        for _ in range(total_notes):
            sim_streak += 1
            sim_mult = min(MAX_MULTIPLIER,
                           1.0 + (sim_streak // STREAK_MILESTONE) * MULTIPLIER_STEP)
            # Base + max hold bonus
            base = PERFECT_POINTS
            hold = int(base * HOLD_BONUS_RATIO)
            self.max_possible += int((base + hold) * sim_mult)

    def record(self, judgment: str, early_late: str = "",
               timing_diff: float = 0.0, detected_midi: int = 0,
               expected_midi: int = 0) -> int:
        """Record a judgment with continuous scoring. Returns points earned."""
        points_earned = 0

        if judgment == "miss":
            self.misses += 1
            self.streak = 0
            self.multiplier = max(MIN_MULTIPLIER,
                                  self.multiplier - MISS_MULTIPLIER_DROP)
        else:
            if judgment == "perfect":
                self.perfects += 1
            elif judgment == "good":
                self.goods += 1
            elif judgment == "ok":
                self.oks += 1

            if early_late == "early":
                self.early_count += 1
            elif early_late == "late":
                self.late_count += 1

            self.streak += 1
            self.max_streak = max(self.max_streak, self.streak)
            self.multiplier = min(
                MAX_MULTIPLIER,
                1.0 + (self.streak // STREAK_MILESTONE) * MULTIPLIER_STEP)

            # Continuous scoring based on actual timing
            base_pts = compute_timing_score(timing_diff)
            points_earned = int(base_pts * self.multiplier)
            self.score += points_earned

        self.note_results.append({
            "judgment": judgment, "early_late": early_late,
            "timing_diff": timing_diff, "points_earned": points_earned,
            "multiplier": self.multiplier, "streak": self.streak,
            "detected_midi": detected_midi, "expected_midi": expected_midi,
        })
        return points_earned

    def record_hold_bonus(self, base_points: int, actual_hold: float,
                          expected_hold: float) -> int:
        """Record hold duration bonus. Returns bonus points earned."""
        bonus = compute_hold_bonus(base_points, actual_hold, expected_hold)
        if bonus > 0:
            bonus_with_mult = int(bonus * self.multiplier)
            self.score += bonus_with_mult
            self.total_hold_bonus += bonus_with_mult
            return bonus_with_mult
        return 0

    def record_wrong_note_penalty(self, expected_midi: int, played_midi: int) -> int:
        """Record a wrong note with score penalty. Returns penalty (negative)."""
        self.wrong_notes.append((expected_midi, played_midi))
        penalty = WRONG_NOTE_PENALTY
        self.score = max(0, self.score - penalty)
        self.wrong_note_penalties += penalty

        if WRONG_NOTE_STREAK_RESET:
            self.streak = 0
            self.multiplier = max(MIN_MULTIPLIER,
                                  self.multiplier - MISS_MULTIPLIER_DROP)
        return -penalty

    def record_wrong_note(self, expected_midi: int, played_midi: int):
        """Legacy: record without penalty (used by some callers)."""
        self.wrong_notes.append((expected_midi, played_midi))

    @property
    def stars(self) -> int:
        if self.max_possible <= 0:
            return 1
        pct = self.score / self.max_possible
        rating = 1
        for i, threshold in enumerate(STAR_THRESHOLDS):
            if pct >= threshold:
                rating = i + 1
        return min(5, rating)

    @property
    def percentage(self) -> float:
        if self.max_possible <= 0:
            return 0.0
        return self.score / self.max_possible

    @property
    def notes_hit(self) -> int:
        return self.perfects + self.goods + self.oks

    @property
    def letter_grade(self) -> str:
        return get_letter_grade(self.percentage)


# ── High Score Persistence ───────────────────────────────────────────────────

SCORES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "scores.json")


def load_high_scores() -> dict:
    if not os.path.exists(SCORES_FILE):
        return {}
    try:
        with open(SCORES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_high_score(song_filename: str, tracker: ScoreTracker):
    os.makedirs(os.path.dirname(SCORES_FILE), exist_ok=True)
    scores = load_high_scores()
    key = os.path.basename(song_filename)
    existing = scores.get(key, {})

    if tracker.score > existing.get("score", 0):
        scores[key] = {
            "score": tracker.score,
            "stars": tracker.stars,
            "grade": tracker.letter_grade,
            "max_streak": tracker.max_streak,
            "perfects": tracker.perfects,
            "goods": tracker.goods,
            "oks": tracker.oks,
            "misses": tracker.misses,
            "early_count": tracker.early_count,
            "late_count": tracker.late_count,
            "wrong_note_count": len(tracker.wrong_notes),
            "wrong_note_penalties": tracker.wrong_note_penalties,
            "total_hold_bonus": tracker.total_hold_bonus,
            "percentage": round(tracker.percentage, 4),
        }
        with open(SCORES_FILE, "w") as f:
            json.dump(scores, f, indent=2)
