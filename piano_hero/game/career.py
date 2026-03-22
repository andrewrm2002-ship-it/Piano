"""Career mode with venue progression - play through increasingly prestigious venues."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

CAREER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "career_progress.json")


@dataclass
class Venue:
    """A performance venue in career mode.

    Each venue has a visual identity (colors for BackgroundRenderer),
    a star threshold to unlock, and a setlist of 5 songs the player
    must complete to clear the venue.
    """

    id: str
    name: str
    description: str
    stars_required: int
    songs: list  # List of {"file": str, "difficulty": str, "required_stars": int}
    bg_color_top: tuple  # RGB for background gradient top
    bg_color_bottom: tuple  # RGB for background gradient bottom
    accent_color: tuple  # RGB accent for UI highlights
    cleared: bool = False


class CareerManager:
    """Manages career mode progression through venues.

    Tracks which venues are unlocked, which songs have been played,
    and how many stars the player has earned at each venue. Progress
    is persisted to data/career_progress.json.
    """

    def __init__(self) -> None:
        self.venues: list[Venue] = self._build_venues()
        self.progress: dict = self._load_progress()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_venues(self) -> list[Venue]:
        """Return the full ordered list of venues."""
        return list(self.venues)

    def is_venue_unlocked(self, venue_id: str, total_stars: int) -> bool:
        """Check whether the player has enough stars to access a venue."""
        for venue in self.venues:
            if venue.id == venue_id:
                return total_stars >= venue.stars_required
        return False

    def is_venue_cleared(self, venue_id: str) -> bool:
        """A venue is cleared when every song in its setlist has 3+ stars."""
        vp = self.progress.get(venue_id, {})
        venue = self._venue_by_id(venue_id)
        if venue is None:
            return False
        for song_entry in venue.songs:
            song_file = song_entry["file"]
            if vp.get(song_file, 0) < song_entry["required_stars"]:
                return False
        return True

    def get_venue_progress(self, venue_id: str) -> dict:
        """Return a summary of the player's progress at a venue.

        Returns:
            {
                "songs_completed": int,   # songs meeting required_stars
                "songs_total": int,
                "stars_earned": int,       # sum of best stars per song
                "stars_possible": int,     # 5 * number of songs
                "cleared": bool,
            }
        """
        venue = self._venue_by_id(venue_id)
        if venue is None:
            return {"songs_completed": 0, "songs_total": 0,
                    "stars_earned": 0, "stars_possible": 0, "cleared": False}

        vp = self.progress.get(venue_id, {})
        songs_completed = 0
        stars_earned = 0
        for song_entry in venue.songs:
            best = vp.get(song_entry["file"], 0)
            stars_earned += best
            if best >= song_entry["required_stars"]:
                songs_completed += 1

        return {
            "songs_completed": songs_completed,
            "songs_total": len(venue.songs),
            "stars_earned": stars_earned,
            "stars_possible": 5 * len(venue.songs),
            "cleared": self.is_venue_cleared(venue_id),
        }

    def record_song_result(self, venue_id: str, song_file: str, stars: int) -> None:
        """Record a song play, keeping only the best star count."""
        if venue_id not in self.progress:
            self.progress[venue_id] = {}
        current_best = self.progress[venue_id].get(song_file, 0)
        if stars > current_best:
            self.progress[venue_id][song_file] = stars
            self._save_progress()

    def get_current_venue(self, total_stars: int) -> Optional[Venue]:
        """Return the highest-tier venue the player has unlocked.

        If all venues are cleared the last venue is returned so the
        player can keep replaying it.
        """
        current: Optional[Venue] = None
        for venue in self.venues:
            if total_stars >= venue.stars_required:
                current = venue
        return current

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_progress(self) -> dict:
        """Load career progress from disk.

        Returns:
            Dict mapping venue_id -> {song_file: best_stars, ...}
        """
        if not os.path.exists(CAREER_FILE):
            return {}
        try:
            with open(CAREER_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_progress(self) -> None:
        """Persist career progress to disk."""
        os.makedirs(os.path.dirname(CAREER_FILE), exist_ok=True)
        with open(CAREER_FILE, "w") as f:
            json.dump(self.progress, f, indent=2)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _venue_by_id(self, venue_id: str) -> Optional[Venue]:
        """Look up a venue by its unique id."""
        for venue in self.venues:
            if venue.id == venue_id:
                return venue
        return None

    @staticmethod
    def _build_venues() -> list[Venue]:
        """Define the six career venues and their setlists.

        Songs are assigned from the existing song library. Difficulty
        labels are informational — the actual note data comes from the
        JSON files.
        """
        return [
            # ----------------------------------------------------------
            # 1. Living Room  (0 stars) — beginner-friendly nursery songs
            # ----------------------------------------------------------
            Venue(
                id="living_room",
                name="Living Room",
                description="Your musical journey begins at home",
                stars_required=0,
                songs=[
                    {"file": "hot_cross_buns.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "mary_had_a_little_lamb.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "twinkle_twinkle.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "baa_baa_black_sheep.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "row_row_row.json", "difficulty": "Easy", "required_stars": 2},
                ],
                bg_color_top=(60, 40, 30),
                bg_color_bottom=(30, 20, 15),
                accent_color=(200, 160, 100),
            ),

            # ----------------------------------------------------------
            # 2. School Recital  (10 stars) — easy-to-medium
            # ----------------------------------------------------------
            Venue(
                id="school_recital",
                name="School Recital",
                description="Time to perform for your classmates!",
                stars_required=10,
                songs=[
                    {"file": "london_bridge.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "frere_jacques.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "old_macdonald.json", "difficulty": "Easy", "required_stars": 2},
                    {"file": "humpty_dumpty.json", "difficulty": "Easy-Medium", "required_stars": 2},
                    {"file": "itsy_bitsy_spider.json", "difficulty": "Easy-Medium", "required_stars": 2},
                ],
                bg_color_top=(50, 50, 80),
                bg_color_bottom=(25, 25, 50),
                accent_color=(100, 180, 255),
            ),

            # ----------------------------------------------------------
            # 3. Community Center  (25 stars) — medium folk tunes
            # ----------------------------------------------------------
            Venue(
                id="community_center",
                name="Community Center",
                description="The whole neighborhood is watching",
                stars_required=25,
                songs=[
                    {"file": "oh_susanna.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "yankee_doodle.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "clementine.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "camptown_races.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "skip_to_my_lou.json", "difficulty": "Medium", "required_stars": 2},
                ],
                bg_color_top=(60, 50, 40),
                bg_color_bottom=(35, 30, 25),
                accent_color=(220, 180, 80),
            ),

            # ----------------------------------------------------------
            # 4. Coffee House  (45 stars) — medium traditional songs
            # ----------------------------------------------------------
            Venue(
                id="coffee_house",
                name="Coffee House",
                description="Playing for a real audience now",
                stars_required=45,
                songs=[
                    {"file": "greensleeves.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "danny_boy.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "scarborough_fair.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "amazing_grace.json", "difficulty": "Medium", "required_stars": 2},
                    {"file": "shenandoah.json", "difficulty": "Medium", "required_stars": 2},
                ],
                bg_color_top=(40, 25, 20),
                bg_color_bottom=(20, 12, 10),
                accent_color=(180, 120, 60),
            ),

            # ----------------------------------------------------------
            # 5. Concert Hall  (70 stars) — medium-hard classical
            # ----------------------------------------------------------
            Venue(
                id="concert_hall",
                name="Concert Hall",
                description="The big stage awaits",
                stars_required=70,
                songs=[
                    {"file": "ode_to_joy.json", "difficulty": "Medium-Hard", "required_stars": 3},
                    {"file": "minuet_in_g.json", "difficulty": "Medium-Hard", "required_stars": 3},
                    {"file": "brahms_lullaby.json", "difficulty": "Medium-Hard", "required_stars": 3},
                    {"file": "canon_in_d.json", "difficulty": "Medium-Hard", "required_stars": 3},
                    {"file": "morning_grieg.json", "difficulty": "Medium-Hard", "required_stars": 3},
                ],
                bg_color_top=(20, 20, 40),
                bg_color_bottom=(10, 10, 25),
                accent_color=(255, 215, 0),
            ),

            # ----------------------------------------------------------
            # 6. Grand Theater  (100 stars) — hard classical showpieces
            # ----------------------------------------------------------
            Venue(
                id="grand_theater",
                name="Grand Theater",
                description="You're a star!",
                stars_required=100,
                songs=[
                    {"file": "fur_elise.json", "difficulty": "Hard", "required_stars": 3},
                    {"file": "moonlight_sonata.json", "difficulty": "Hard", "required_stars": 3},
                    {"file": "spring_vivaldi.json", "difficulty": "Hard", "required_stars": 3},
                    {"file": "trumpet_voluntary.json", "difficulty": "Hard", "required_stars": 3},
                    {"file": "william_tell.json", "difficulty": "Hard", "required_stars": 3},
                ],
                bg_color_top=(15, 5, 25),
                bg_color_bottom=(5, 0, 10),
                accent_color=(255, 50, 50),
            ),
        ]
