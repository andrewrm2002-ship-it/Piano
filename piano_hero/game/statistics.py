"""Player statistics tracking and persistence."""

import json
import os
from datetime import datetime


STATS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "stats.json")


def _default_stats():
    return {
        "total_songs_played": 0,
        "total_songs_completed": 0,
        "total_notes_hit": 0,
        "total_notes_missed": 0,
        "total_perfects": 0,
        "total_goods": 0,
        "total_oks": 0,
        "total_score": 0,
        "total_play_time": 0.0,
        "best_streak": 0,
        "five_star_count": 0,
        "songs_with_stars": {},
        "daily_plays": {},
        "accuracy_history": [],
        "first_play_date": None,
        "last_play_date": None,
    }


def load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        return _default_stats()
    try:
        with open(STATS_FILE, 'r') as f:
            saved = json.load(f)
        stats = _default_stats()
        stats.update(saved)
        return stats
    except Exception:
        return _default_stats()


def save_stats(stats: dict):
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)


def record_session(stats: dict, song_title: str, score_tracker, song_duration: float,
                   completed: bool = True):
    """Record a play session into cumulative stats."""
    today = datetime.now().strftime("%Y-%m-%d")

    stats["total_songs_played"] += 1
    if completed:
        stats["total_songs_completed"] += 1
    stats["total_notes_hit"] += score_tracker.notes_hit
    stats["total_notes_missed"] += score_tracker.misses
    stats["total_perfects"] += score_tracker.perfects
    stats["total_goods"] += score_tracker.goods
    stats["total_oks"] += score_tracker.oks
    stats["total_score"] += score_tracker.score
    stats["total_play_time"] += song_duration
    stats["best_streak"] = max(stats["best_streak"], score_tracker.max_streak)

    if score_tracker.stars >= 5:
        stats["five_star_count"] += 1

    # Track stars per song
    stars = stats.get("songs_with_stars", {})
    old_stars = stars.get(song_title, 0)
    if score_tracker.stars > old_stars:
        stars[song_title] = score_tracker.stars
    stats["songs_with_stars"] = stars

    # Daily play count
    daily = stats.get("daily_plays", {})
    daily[today] = daily.get(today, 0) + 1
    stats["daily_plays"] = daily

    # Accuracy history (last 50 sessions)
    history = stats.get("accuracy_history", [])
    total = score_tracker.notes_hit + score_tracker.misses
    if total > 0:
        accuracy = score_tracker.notes_hit / total
    else:
        accuracy = 0.0
    history.append({
        "date": today,
        "song": song_title,
        "accuracy": round(accuracy, 3),
        "score": score_tracker.score,
        "stars": score_tracker.stars,
    })
    stats["accuracy_history"] = history[-50:]

    if stats["first_play_date"] is None:
        stats["first_play_date"] = today
    stats["last_play_date"] = today

    save_stats(stats)
    return stats


def get_stars_earned(stats: dict) -> int:
    """Total number of stars earned across all songs (for unlock thresholds)."""
    return sum(stats.get("songs_with_stars", {}).values())


def get_average_accuracy(stats: dict) -> float:
    """Average accuracy across recent sessions."""
    history = stats.get("accuracy_history", [])
    if not history:
        return 0.0
    return sum(h["accuracy"] for h in history) / len(history)


def get_difficulty_suggestion(stats: dict, current_song_accuracy: float = 0.0) -> str:
    """Suggest difficulty adjustments based on recent performance.

    Returns one of: 'easier', 'harder', 'same', or '' (no suggestion).
    """
    history = stats.get('accuracy_history', [])
    if len(history) < 3:
        return ''

    recent = history[-3:]
    avg_acc = sum(h['accuracy'] for h in recent) / len(recent)

    if avg_acc < 0.5:
        return 'easier'  # Struggling — suggest slower speed or easier arrangement
    elif avg_acc > 0.9 and all(h.get('stars', 0) >= 4 for h in recent):
        return 'harder'  # Crushing it — suggest harder songs
    return 'same'


def get_trouble_spots(note_results: list, song_notes: list,
                      max_spots: int = 3) -> list:
    """Identify the hardest passages in a song based on note_results.

    Returns list of (start_beat, end_beat, miss_count) tuples for the
    worst sections, suitable for setting loop_start_beat/loop_end_beat.
    """
    if not note_results or not song_notes:
        return []

    # Divide the song into 4-beat windows and count misses per window
    if not song_notes:
        return []

    max_beat = max(n.start_beat for n in song_notes)
    window_size = 4.0  # beats per window
    windows = {}

    for i, result in enumerate(note_results):
        if i < len(song_notes):
            beat = song_notes[i].start_beat
            window_idx = int(beat / window_size)
            if window_idx not in windows:
                windows[window_idx] = {'misses': 0, 'total': 0, 'start': window_idx * window_size}
            windows[window_idx]['total'] += 1
            if result.get('judgment') in ('miss', 'ok'):
                windows[window_idx]['misses'] += 1

    # Sort by miss ratio, take worst spots
    bad_windows = [(w['start'], w['start'] + window_size, w['misses'])
                   for w in windows.values() if w['misses'] > 0]
    bad_windows.sort(key=lambda x: -x[2])

    return bad_windows[:max_spots]
