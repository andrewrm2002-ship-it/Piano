"""Ghost note system - shows previous best performance as translucent overlay."""
import json, os
from dataclasses import dataclass

GHOST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'data', 'ghosts')

@dataclass
class GhostNote:
    midi: int
    timestamp: float      # When the note was actually played
    expected_time: float   # When it should have been played
    judgment: str          # "perfect", "good", "ok", "miss"

class GhostRecorder:
    """Records a performance for future ghost playback."""
    def __init__(self):
        self.notes = []

    def record(self, midi: int, timestamp: float, expected_time: float, judgment: str):
        self.notes.append(GhostNote(midi, timestamp, expected_time, judgment))

    def save(self, song_title: str, score: int, profile: str = "default"):
        """Save ghost data if this is a new high score."""
        os.makedirs(GHOST_DIR, exist_ok=True)
        safe_name = song_title.lower().replace(' ', '_').replace("'", '')
        filepath = os.path.join(GHOST_DIR, f"{profile}_{safe_name}.json")

        # Only save if better than existing
        existing = self.load(song_title, profile)
        if existing and existing.get('score', 0) >= score:
            return False

        data = {
            'song_title': song_title,
            'score': score,
            'profile': profile,
            'notes': [{'midi': n.midi, 'timestamp': n.timestamp,
                       'expected_time': n.expected_time, 'judgment': n.judgment}
                      for n in self.notes]
        }
        with open(filepath, 'w') as f:
            json.dump(data, f)
        return True

    @staticmethod
    def load(song_title: str, profile: str = "default") -> dict:
        safe_name = song_title.lower().replace(' ', '_').replace("'", '')
        filepath = os.path.join(GHOST_DIR, f"{profile}_{safe_name}.json")
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
        return None

class GhostPlayback:
    """Plays back a saved ghost performance."""
    def __init__(self, ghost_data: dict):
        self.notes = [GhostNote(**n) for n in ghost_data.get('notes', [])]
        self.score = ghost_data.get('score', 0)
        self.index = 0

    def get_visible_notes(self, current_time: float, window: float = 4.0):
        """Get ghost notes visible in the current time window."""
        visible = []
        for note in self.notes:
            if note.expected_time < current_time - 1.0:
                continue
            if note.expected_time > current_time + window:
                break
            visible.append(note)
        return visible

    def get_ghost_score_at(self, current_time: float) -> int:
        """Get what the ghost's score was at this point in the song."""
        # Approximate: count scored notes up to current_time
        count = sum(1 for n in self.notes if n.expected_time <= current_time and n.judgment != 'miss')
        # Rough estimate
        return int(self.score * (count / max(len(self.notes), 1)))
