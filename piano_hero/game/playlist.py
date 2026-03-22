"""Playlist/setlist management for playing multiple songs in sequence."""
import json, os
from dataclasses import dataclass, field

PLAYLIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'data', 'playlists')

@dataclass
class PlaylistEntry:
    song_file: str          # Filename (e.g., "twinkle_twinkle.json")
    difficulty: str = "Medium"
    speed: float = 1.0

@dataclass
class Playlist:
    name: str
    entries: list = field(default_factory=list)  # List of PlaylistEntry
    created_by: str = "default"

    def add_song(self, song_file: str, difficulty: str = "Medium", speed: float = 1.0):
        self.entries.append(PlaylistEntry(song_file, difficulty, speed))

    def remove_song(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries.pop(index)

    def move_up(self, index: int):
        if index > 0:
            self.entries[index], self.entries[index-1] = self.entries[index-1], self.entries[index]

    def move_down(self, index: int):
        if index < len(self.entries) - 1:
            self.entries[index], self.entries[index+1] = self.entries[index+1], self.entries[index]

class PlaylistManager:
    def __init__(self):
        os.makedirs(PLAYLIST_DIR, exist_ok=True)
        self.playlists = self._load_all()

    def _load_all(self) -> list:
        playlists = []
        for f in os.listdir(PLAYLIST_DIR):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(PLAYLIST_DIR, f)) as fh:
                        data = json.load(fh)
                        pl = Playlist(
                            name=data['name'],
                            entries=[PlaylistEntry(**e) for e in data.get('entries', [])],
                            created_by=data.get('created_by', 'default')
                        )
                        playlists.append(pl)
                except (json.JSONDecodeError, KeyError):
                    pass
        return playlists

    def create(self, name: str, profile: str = "default") -> Playlist:
        pl = Playlist(name=name, created_by=profile)
        self.playlists.append(pl)
        self._save(pl)
        return pl

    def delete(self, name: str):
        self.playlists = [p for p in self.playlists if p.name != name]
        safe = name.lower().replace(' ', '_')
        path = os.path.join(PLAYLIST_DIR, f"{safe}.json")
        if os.path.exists(path):
            os.remove(path)

    def _save(self, playlist: Playlist):
        safe = playlist.name.lower().replace(' ', '_')
        path = os.path.join(PLAYLIST_DIR, f"{safe}.json")
        data = {
            'name': playlist.name,
            'created_by': playlist.created_by,
            'entries': [{'song_file': e.song_file, 'difficulty': e.difficulty, 'speed': e.speed}
                        for e in playlist.entries]
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def save_all(self):
        for pl in self.playlists:
            self._save(pl)

    def get_default_playlists(self) -> list:
        """Create default playlists if none exist."""
        if not self.playlists:
            # Beginner's Journey
            beginner = self.create("Beginner's Journey")
            for song in ['hot_cross_buns.json', 'mary_had_a_little_lamb.json',
                         'twinkle_twinkle.json', 'london_bridge.json', 'row_row_row.json']:
                beginner.add_song(song, "Easy")

            # Classical Sampler
            classical = self.create("Classical Sampler")
            for song in ['ode_to_joy.json', 'fur_elise.json', 'canon_in_d.json',
                         'moonlight_sonata.json', 'brahms_lullaby.json']:
                classical.add_song(song, "Medium")

            # Holiday Favorites
            holiday = self.create("Holiday Favorites")
            for song in ['jingle_bells.json', 'silent_night.json', 'joy_to_the_world.json',
                         'deck_the_halls.json', 'we_wish_you.json']:
                holiday.add_song(song, "Easy")

            self.save_all()
        return self.playlists
