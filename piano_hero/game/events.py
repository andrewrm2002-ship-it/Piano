"""Seasonal events system - time-limited themed challenges with exclusive badges."""

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

EVENT_PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "event_progress.json")


@dataclass
class SeasonalEvent:
    """A time-limited seasonal event with featured songs and a badge reward.

    Events are active during a calendar window (start_month/start_day
    through end_month/end_day) every year. Players earn a badge by
    completing the challenge (e.g., getting 3+ stars on a certain
    number of featured songs).
    """

    id: str
    name: str
    description: str
    start_month: int       # 1-12
    start_day: int
    end_month: int         # 1-12
    end_day: int
    featured_songs: list   # Song filenames highlighted during the event
    badge_name: str        # Achievement name awarded on completion
    badge_description: str
    challenge: str         # Human-readable challenge description
    accent_color: tuple    # RGB theme accent override during event
    songs_required: int = 0  # Number of songs that must hit the star threshold

    def __post_init__(self) -> None:
        """Derive songs_required from the challenge string if not set."""
        if self.songs_required == 0:
            self.songs_required = self._parse_songs_required()

    def _parse_songs_required(self) -> int:
        """Extract the required song count from the challenge text.

        Looks for patterns like "3+ stars on 5 holiday songs" and
        returns the count (5). Falls back to len(featured_songs) // 2.
        """
        match = re.search(r"on\s+(\d+)\s+", self.challenge)
        if match:
            return int(match.group(1))
        return max(1, len(self.featured_songs) // 2)


# --------------------------------------------------------------------------
# Event definitions
# --------------------------------------------------------------------------

SEASONAL_EVENTS: list[SeasonalEvent] = [
    SeasonalEvent(
        id="holiday_concert",
        name="Holiday Concert",
        description="Celebrate the season with festive tunes!",
        start_month=12,
        start_day=1,
        end_month=12,
        end_day=31,
        featured_songs=[
            "jingle_bells.json",
            "silent_night.json",
            "joy_to_the_world.json",
            "deck_the_halls.json",
            "we_wish_you.json",
            "o_christmas_tree.json",
            "away_in_a_manger.json",
        ],
        badge_name="Holiday Star",
        badge_description="Complete the Holiday Concert event",
        challenge="Get 3+ stars on 5 holiday songs",
        accent_color=(200, 50, 50),
    ),

    SeasonalEvent(
        id="spring_classical",
        name="Spring Classical Festival",
        description="Classical masterpieces bloom!",
        start_month=3,
        start_day=1,
        end_month=5,
        end_day=31,
        featured_songs=[
            "ode_to_joy.json",
            "fur_elise.json",
            "canon_in_d.json",
            "moonlight_sonata.json",
            "brahms_lullaby.json",
            "morning_grieg.json",
            "spring_vivaldi.json",
        ],
        badge_name="Classical Virtuoso",
        badge_description="Complete the Spring Classical Festival",
        challenge="Get 3+ stars on 4 classical pieces",
        accent_color=(180, 100, 220),
    ),

    SeasonalEvent(
        id="summer_folk",
        name="Summer Folk Fest",
        description="Sing-along favorites for sunny days!",
        start_month=6,
        start_day=1,
        end_month=8,
        end_day=31,
        featured_songs=[
            "oh_susanna.json",
            "camptown_races.json",
            "home_on_the_range.json",
            "clementine.json",
            "buffalo_gals.json",
            "shenandoah.json",
            "my_bonnie.json",
        ],
        badge_name="Folk Legend",
        badge_description="Complete the Summer Folk Fest",
        challenge="Get 3+ stars on 4 folk songs",
        accent_color=(50, 180, 80),
    ),

    SeasonalEvent(
        id="fall_patriotic",
        name="Fall Patriotic Salute",
        description="Honor tradition with classic hymns!",
        start_month=9,
        start_day=1,
        end_month=11,
        end_day=30,
        featured_songs=[
            "america_the_beautiful.json",
            "battle_hymn.json",
            "amazing_grace.json",
            "auld_lang_syne.json",
            "swing_low.json",
            "simple_gifts.json",
        ],
        badge_name="Patriot's Pride",
        badge_description="Complete the Fall Patriotic Salute",
        challenge="Get 3+ stars on 4 patriotic/hymn songs",
        accent_color=(50, 80, 180),
    ),
]


class EventManager:
    """Manages seasonal event detection, progress tracking, and badge awards.

    Events activate based on the current calendar date. Progress
    (which featured songs the player completed with 3+ stars) is
    saved to data/event_progress.json so it persists across sessions.
    """

    STAR_THRESHOLD: int = 3  # Minimum stars on a song for it to count

    def __init__(self) -> None:
        self.events: list[SeasonalEvent] = SEASONAL_EVENTS
        self.progress: dict = self._load_progress()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_active_event(self) -> Optional[SeasonalEvent]:
        """Return the currently active event based on today's date, or None."""
        today = date.today()
        for event in self.events:
            if self._is_date_in_range(today, event):
                return event
        return None

    def is_event_active(self, event: SeasonalEvent) -> bool:
        """Check if a specific event is active based on today's date."""
        return self._is_date_in_range(date.today(), event)

    def get_event_progress(self, event_id: str) -> dict:
        """Return progress details for an event.

        Returns:
            {
                "songs_completed": int,  # featured songs with 3+ stars
                "songs_required": int,   # how many needed for the badge
                "songs_total": int,      # total featured songs
                "completed_songs": list, # filenames meeting threshold
                "badge_earned": bool,
            }
        """
        event = self._event_by_id(event_id)
        if event is None:
            return {
                "songs_completed": 0,
                "songs_required": 0,
                "songs_total": 0,
                "completed_songs": [],
                "badge_earned": False,
            }

        ep = self.progress.get(event_id, {})
        song_results = ep.get("songs", {})
        completed = [
            song for song in event.featured_songs
            if song_results.get(song, 0) >= self.STAR_THRESHOLD
        ]

        return {
            "songs_completed": len(completed),
            "songs_required": event.songs_required,
            "songs_total": len(event.featured_songs),
            "completed_songs": completed,
            "badge_earned": ep.get("badge_earned", False),
        }

    def record_song_play(self, event_id: str, song_file: str, stars: int) -> None:
        """Record that a featured song was played during the event.

        Only the best star result per song is kept. After recording,
        automatically checks if the badge should be awarded.

        Args:
            event_id: The event to record against.
            song_file: The song filename (e.g., "jingle_bells.json").
            stars: The star count earned on this play.
        """
        if event_id not in self.progress:
            self.progress[event_id] = {"songs": {}, "badge_earned": False}

        ep = self.progress[event_id]
        current_best = ep["songs"].get(song_file, 0)
        if stars > current_best:
            ep["songs"][song_file] = stars

        # Check if the badge should be awarded
        if not ep["badge_earned"] and self.check_completion(event_id):
            ep["badge_earned"] = True

        self._save_progress()

    def check_completion(self, event_id: str) -> bool:
        """Check whether the event challenge has been completed.

        Returns True if the player has earned STAR_THRESHOLD+ stars
        on at least songs_required featured songs.
        """
        event = self._event_by_id(event_id)
        if event is None:
            return False

        ep = self.progress.get(event_id, {})
        song_results = ep.get("songs", {})
        qualifying = sum(
            1 for song in event.featured_songs
            if song_results.get(song, 0) >= self.STAR_THRESHOLD
        )
        return qualifying >= event.songs_required

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_progress(self) -> dict:
        """Load event progress from disk.

        Returns:
            Dict mapping event_id -> {"songs": {file: best_stars}, "badge_earned": bool}
        """
        if not os.path.exists(EVENT_PROGRESS_FILE):
            return {}
        try:
            with open(EVENT_PROGRESS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_progress(self) -> None:
        """Persist event progress to disk."""
        os.makedirs(os.path.dirname(EVENT_PROGRESS_FILE), exist_ok=True)
        with open(EVENT_PROGRESS_FILE, "w") as f:
            json.dump(self.progress, f, indent=2)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _event_by_id(self, event_id: str) -> Optional[SeasonalEvent]:
        """Look up an event by its unique id."""
        for event in self.events:
            if event.id == event_id:
                return event
        return None

    @staticmethod
    def _is_date_in_range(today: date, event: SeasonalEvent) -> bool:
        """Check whether today falls within the event's date window.

        Handles same-year ranges only (no wrap-around from Dec to Jan).
        Each event is assumed to start and end within the same calendar
        year.
        """
        start = date(today.year, event.start_month, event.start_day)
        end = date(today.year, event.end_month, event.end_day)
        return start <= today <= end
