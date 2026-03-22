"""Achievement and daily streak system."""
import json
import os
from datetime import datetime, timedelta

ACHIEVEMENTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "achievements.json")

# Achievement definitions: (id, name, description, condition_check_key)
ACHIEVEMENT_DEFS = [
    ("first_song", "First Steps", "Complete your first song", "songs_completed"),
    ("first_perfect", "Perfection", "Get a Perfect judgment", "has_perfect"),
    ("streak_10", "On Fire", "Get a 10-note streak", "best_streak_10"),
    ("streak_25", "Combo Master", "Get a 25-note streak", "best_streak_25"),
    ("streak_50", "Unstoppable", "Get a 50-note streak", "best_streak_50"),
    ("five_star", "Gold Star", "Earn 5 stars on any song", "has_five_star"),
    ("ten_songs", "Song Collector", "Play 10 different songs", "songs_played_10"),
    ("all_perfect", "Flawless", "Complete a song with 100% accuracy", "flawless"),
    ("grade_s", "S-Rank", "Earn an S grade on any song", "has_grade_s"),
    ("grade_a", "Honor Roll", "Earn an A grade on any song", "has_grade_a"),
    ("hold_master", "Sustained", "Earn 500+ hold bonus in one song", "hold_master"),
    ("no_wrong", "Clean Hands", "Complete a song with zero wrong notes", "no_wrong_notes"),
    ("speed_demon", "Speed Demon", "Complete a song at 50% speed then 100%", "speed_demon"),
    ("chord_player", "Chord Master", "Complete a chord song with 3+ stars", "chord_master"),
    ("star_power", "Supercharged", "Activate Star Power 3 times in one song", "star_power_3"),
    ("daily_3", "Three Day Streak", "Play 3 days in a row", "streak_3"),
    ("daily_7", "Weekly Warrior", "Play 7 days in a row", "streak_7"),
    ("daily_30", "Monthly Maestro", "Play 30 days in a row", "streak_30"),
    ("songs_25", "Quarter Century", "Play 25 different songs", "songs_played_25"),
    ("total_1000", "Score Hunter", "Earn 1,000 total points across all songs", "total_score_1000"),
    ("total_10000", "Point Master", "Earn 10,000 total points", "total_score_10000"),
    ("night_owl", "Night Owl", "Play after 9 PM", "night_play"),
    ("early_bird", "Early Bird", "Play before 7 AM", "early_play"),
    ("practice_pro", "Practice Pro", "Use practice mode 5 times", "practice_5"),
]


def load_achievements() -> dict:
    """Load unlocked achievements. Returns {achievement_id: unlock_timestamp}."""
    if not os.path.exists(ACHIEVEMENTS_FILE):
        return {}
    try:
        with open(ACHIEVEMENTS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_achievements(achievements: dict):
    os.makedirs(os.path.dirname(ACHIEVEMENTS_FILE), exist_ok=True)
    with open(ACHIEVEMENTS_FILE, 'w') as f:
        json.dump(achievements, f, indent=2)


def check_achievements(stats: dict, session_data: dict = None) -> list:
    """Check which new achievements have been unlocked.

    Args:
        stats: The full stats dict from statistics.py
        session_data: Optional dict with session-specific data:
            - score_tracker: the ScoreTracker from the just-completed session
            - song_title: title of the song
            - practice_mode: bool

    Returns: list of newly unlocked (id, name, description) tuples.
    """
    unlocked = load_achievements()
    newly_unlocked = []
    now = datetime.now()

    def unlock(aid):
        if aid not in unlocked:
            unlocked[aid] = now.isoformat()
            defn = next((d for d in ACHIEVEMENT_DEFS if d[0] == aid), None)
            if defn:
                newly_unlocked.append((defn[0], defn[1], defn[2]))

    # Stats-based achievements
    if stats.get('total_songs_completed', 0) >= 1:
        unlock('first_song')
    if stats.get('total_songs_completed', 0) >= 10:
        unlock('ten_songs')
    if stats.get('total_songs_played', 0) >= 25:
        unlock('songs_25')
    if stats.get('best_streak', 0) >= 10:
        unlock('streak_10')
    if stats.get('best_streak', 0) >= 25:
        unlock('streak_25')
    if stats.get('best_streak', 0) >= 50:
        unlock('streak_50')
    if stats.get('five_star_count', 0) >= 1:
        unlock('five_star')
    if stats.get('total_score', 0) >= 1000:
        unlock('total_1000')
    if stats.get('total_score', 0) >= 10000:
        unlock('total_10000')

    # Time-based
    if now.hour >= 21:
        unlock('night_owl')
    if now.hour < 7:
        unlock('early_bird')

    # Daily streak
    streak = compute_daily_streak(stats)
    if streak >= 3:
        unlock('daily_3')
    if streak >= 7:
        unlock('daily_7')
    if streak >= 30:
        unlock('daily_30')

    # Session-based achievements
    if session_data:
        tracker = session_data.get('score_tracker')
        if tracker:
            if tracker.perfects > 0:
                unlock('first_perfect')
            if tracker.misses == 0 and tracker.notes_hit > 0:
                unlock('all_perfect')
            if len(tracker.wrong_notes) == 0 and tracker.notes_hit > 0:
                unlock('no_wrong')
            if tracker.letter_grade == 'S':
                unlock('grade_s')
            if tracker.letter_grade in ('S', 'A'):
                unlock('grade_a')
            if tracker.total_hold_bonus >= 500:
                unlock('hold_master')

        song_title = session_data.get('song_title', '')
        if 'chord' in song_title.lower() and tracker and tracker.stars >= 3:
            unlock('chord_master')

    if newly_unlocked:
        save_achievements(unlocked)

    return newly_unlocked


def compute_daily_streak(stats: dict) -> int:
    """Compute consecutive days played ending today (or yesterday)."""
    daily = stats.get('daily_plays', {})
    if not daily:
        return 0

    today = datetime.now().date()
    streak = 0
    check_date = today

    # Allow yesterday to count (in case they haven't played today yet)
    if check_date.isoformat() not in daily:
        check_date = today - timedelta(days=1)

    while check_date.isoformat() in daily:
        streak += 1
        check_date -= timedelta(days=1)

    return streak


def get_achievement_progress() -> list:
    """Return list of (id, name, description, unlocked) for display."""
    unlocked = load_achievements()
    result = []
    for aid, name, desc, _ in ACHIEVEMENT_DEFS:
        result.append((aid, name, desc, aid in unlocked))
    return result
