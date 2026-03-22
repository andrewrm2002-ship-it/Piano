"""Local family leaderboard system - compare scores across profiles."""
import json, os
from dataclasses import dataclass, field
from datetime import datetime

LEADERBOARD_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'data', 'leaderboard.json')

@dataclass
class LeaderboardEntry:
    profile: str
    song_title: str
    score: int
    stars: int
    grade: str
    accuracy: float
    streak: int
    timestamp: str  # ISO format
    difficulty: str = "Medium"

class Leaderboard:
    """Manages per-song and overall leaderboards across family profiles."""

    def __init__(self):
        self.entries = self._load()

    def record(self, profile: str, song_title: str, score: int, stars: int,
               grade: str, accuracy: float, streak: int, difficulty: str = "Medium"):
        """Record a new score entry."""
        entry = LeaderboardEntry(
            profile=profile,
            song_title=song_title,
            score=score,
            stars=stars,
            grade=grade,
            accuracy=accuracy,
            streak=streak,
            timestamp=datetime.now().isoformat(),
            difficulty=difficulty
        )
        self.entries.append(entry)
        self._save()
        return entry

    def get_song_leaderboard(self, song_title: str, limit: int = 10) -> list:
        """Get top scores for a specific song, across all profiles."""
        song_entries = [e for e in self.entries if e.song_title == song_title]
        song_entries.sort(key=lambda e: e.score, reverse=True)

        # Deduplicate: keep only best per profile
        seen_profiles = set()
        unique = []
        for e in song_entries:
            if e.profile not in seen_profiles:
                seen_profiles.add(e.profile)
                unique.append(e)

        return unique[:limit]

    def get_overall_leaderboard(self, limit: int = 10) -> list:
        """Get overall rankings by total score across all songs."""
        profile_totals = {}
        for e in self.entries:
            key = e.profile
            if key not in profile_totals:
                profile_totals[key] = {
                    'profile': key,
                    'total_score': 0,
                    'songs_played': set(),
                    'total_stars': 0,
                    'best_streak': 0,
                    'avg_accuracy': []
                }
            profile_totals[key]['total_score'] += e.score
            profile_totals[key]['songs_played'].add(e.song_title)
            profile_totals[key]['total_stars'] += e.stars
            profile_totals[key]['best_streak'] = max(profile_totals[key]['best_streak'], e.streak)
            profile_totals[key]['avg_accuracy'].append(e.accuracy)

        results = []
        for p in profile_totals.values():
            results.append({
                'profile': p['profile'],
                'total_score': p['total_score'],
                'songs_played': len(p['songs_played']),
                'total_stars': p['total_stars'],
                'best_streak': p['best_streak'],
                'avg_accuracy': sum(p['avg_accuracy']) / len(p['avg_accuracy']) if p['avg_accuracy'] else 0
            })

        results.sort(key=lambda r: r['total_score'], reverse=True)
        return results[:limit]

    def get_weekly_challenge(self) -> dict:
        """Generate a weekly challenge based on the current week."""
        import hashlib
        week_num = datetime.now().isocalendar()[1]
        year = datetime.now().year

        # Deterministic song selection based on week
        seed = hashlib.md5(f"{year}-{week_num}".encode()).hexdigest()

        # Pick from common songs
        challenge_songs = [
            "Twinkle Twinkle Little Star", "Ode to Joy", "Amazing Grace",
            "Jingle Bells", "Fur Elise", "Canon in D",
            "Danny Boy", "Greensleeves", "When the Saints Go Marching In",
            "Silent Night", "Mary Had a Little Lamb", "Yankee Doodle"
        ]

        song_idx = int(seed[:8], 16) % len(challenge_songs)
        speed_options = [1.0, 1.0, 1.0, 1.2, 1.2, 1.5]  # Weighted toward normal
        speed_idx = int(seed[8:16], 16) % len(speed_options)

        return {
            'week': week_num,
            'year': year,
            'song_title': challenge_songs[song_idx],
            'speed': speed_options[speed_idx],
            'description': f"Week {week_num} Challenge: Score highest on {challenge_songs[song_idx]}!",
            'leaderboard': self.get_song_leaderboard(challenge_songs[song_idx], limit=5)
        }

    def get_profile_stats(self, profile: str) -> dict:
        """Get comprehensive stats for a single profile."""
        profile_entries = [e for e in self.entries if e.profile == profile]
        if not profile_entries:
            return {'total_score': 0, 'songs_played': 0, 'total_stars': 0,
                    'best_streak': 0, 'avg_accuracy': 0, 'recent_scores': []}

        return {
            'total_score': sum(e.score for e in profile_entries),
            'songs_played': len(set(e.song_title for e in profile_entries)),
            'total_stars': sum(e.stars for e in profile_entries),
            'best_streak': max(e.streak for e in profile_entries),
            'avg_accuracy': sum(e.accuracy for e in profile_entries) / len(profile_entries),
            'recent_scores': sorted(profile_entries, key=lambda e: e.timestamp, reverse=True)[:10]
        }

    def _load(self) -> list:
        if os.path.exists(LEADERBOARD_FILE):
            try:
                with open(LEADERBOARD_FILE) as f:
                    data = json.load(f)
                return [LeaderboardEntry(**e) for e in data.get('entries', [])]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def _save(self):
        os.makedirs(os.path.dirname(LEADERBOARD_FILE), exist_ok=True)
        data = {
            'entries': [
                {
                    'profile': e.profile,
                    'song_title': e.song_title,
                    'score': e.score,
                    'stars': e.stars,
                    'grade': e.grade,
                    'accuracy': e.accuracy,
                    'streak': e.streak,
                    'timestamp': e.timestamp,
                    'difficulty': e.difficulty
                }
                for e in self.entries
            ]
        }
        with open(LEADERBOARD_FILE, 'w') as f:
            json.dump(data, f, indent=2)
