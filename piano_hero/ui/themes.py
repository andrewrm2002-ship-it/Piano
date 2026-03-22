"""Unlockable visual themes - cosmetic rewards earned through gameplay."""

import json
import os
from dataclasses import dataclass
from typing import Optional

ACTIVE_THEME_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "active_theme.json")


@dataclass
class Theme:
    """A visual theme that controls the game's color palette.

    Themes are purely cosmetic rewards unlocked by accumulating stars.
    Each theme provides a complete color override set that can be fed
    into BackgroundRenderer, NoteHighway, KeyboardDisplay, and HUD.
    """

    id: str
    name: str
    stars_required: int
    description: str
    bg_top: tuple          # Background gradient top RGB
    bg_bottom: tuple       # Background gradient bottom RGB
    highway_bg: tuple      # Note highway background RGB
    note_colors: dict      # {"primary": RGB} or per-octave overrides
    hit_line_color: tuple  # NOW zone / hit line color RGB
    text_color: tuple      # Primary text color RGB
    accent_color: tuple    # Highlights, buttons RGB
    beat_grid_color: tuple  # Beat line color RGB
    key_white: tuple       # Piano white key RGB
    key_black: tuple       # Piano black key RGB


class ThemeManager:
    """Manages unlockable visual themes.

    Handles theme selection, persistence, and star-gated unlocking.
    The active theme is saved to data/active_theme.json so it persists
    across sessions.
    """

    def __init__(self) -> None:
        self.themes: list[Theme] = self._build_themes()
        self.active_theme_id: str = self._load_active()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_themes(self) -> list[Theme]:
        """Return all defined themes in unlock order."""
        return list(self.themes)

    def get_active_theme(self) -> Theme:
        """Return the currently selected theme.

        Falls back to the Default theme if the saved theme id is
        invalid or no longer available.
        """
        for theme in self.themes:
            if theme.id == self.active_theme_id:
                return theme
        # Fallback to default
        return self.themes[0]

    def set_active_theme(self, theme_id: str) -> None:
        """Set the active theme and persist the choice.

        Args:
            theme_id: The id of the theme to activate. Must be a valid
                theme id — if not found the call is silently ignored.
        """
        for theme in self.themes:
            if theme.id == theme_id:
                self.active_theme_id = theme_id
                self._save_active()
                return

    def is_unlocked(self, theme_id: str, total_stars: int) -> bool:
        """Check whether the player has enough stars to use a theme."""
        for theme in self.themes:
            if theme.id == theme_id:
                return total_stars >= theme.stars_required
        return False

    def get_unlocked_themes(self, total_stars: int) -> list[Theme]:
        """Return the subset of themes the player can currently use."""
        return [t for t in self.themes if total_stars >= t.stars_required]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_active(self) -> str:
        """Load the active theme id from disk. Defaults to 'default'."""
        if not os.path.exists(ACTIVE_THEME_FILE):
            return "default"
        try:
            with open(ACTIVE_THEME_FILE, "r") as f:
                data = json.load(f)
            return data.get("active_theme", "default")
        except (json.JSONDecodeError, OSError):
            return "default"

    def _save_active(self) -> None:
        """Persist the active theme selection to disk."""
        os.makedirs(os.path.dirname(ACTIVE_THEME_FILE), exist_ok=True)
        with open(ACTIVE_THEME_FILE, "w") as f:
            json.dump({"active_theme": self.active_theme_id}, f, indent=2)

    # ------------------------------------------------------------------
    # Theme definitions
    # ------------------------------------------------------------------

    @staticmethod
    def _build_themes() -> list[Theme]:
        """Define all visual themes.

        The order here determines display order in the theme picker.
        """
        return [
            # 1. Default — current neon arcade look
            Theme(
                id="default",
                name="Default",
                stars_required=0,
                description="Classic neon arcade vibes",
                bg_top=(30, 10, 60),
                bg_bottom=(10, 5, 30),
                highway_bg=(20, 8, 45),
                note_colors={"primary": (0, 220, 255)},
                hit_line_color=(0, 255, 200),
                text_color=(255, 255, 255),
                accent_color=(0, 200, 255),
                beat_grid_color=(60, 30, 90),
                key_white=(240, 240, 245),
                key_black=(30, 30, 35),
            ),

            # 2. Ocean — deep blue, teal notes, white accents
            Theme(
                id="ocean",
                name="Ocean",
                stars_required=10,
                description="Deep blue depths with teal highlights",
                bg_top=(5, 30, 80),
                bg_bottom=(2, 15, 45),
                highway_bg=(4, 20, 60),
                note_colors={"primary": (0, 200, 180)},
                hit_line_color=(100, 255, 230),
                text_color=(220, 240, 255),
                accent_color=(255, 255, 255),
                beat_grid_color=(10, 50, 100),
                key_white=(210, 230, 245),
                key_black=(10, 30, 50),
            ),

            # 3. Sunset — warm orange/red gradient, gold notes
            Theme(
                id="sunset",
                name="Sunset",
                stars_required=25,
                description="Warm orange and red with golden notes",
                bg_top=(120, 40, 10),
                bg_bottom=(50, 15, 5),
                highway_bg=(80, 25, 8),
                note_colors={"primary": (255, 200, 50)},
                hit_line_color=(255, 160, 30),
                text_color=(255, 240, 220),
                accent_color=(255, 180, 60),
                beat_grid_color=(100, 40, 15),
                key_white=(255, 240, 220),
                key_black=(60, 25, 10),
            ),

            # 4. Forest — dark green, lime green notes, brown accents
            Theme(
                id="forest",
                name="Forest",
                stars_required=40,
                description="Lush greens and earthy tones",
                bg_top=(10, 45, 20),
                bg_bottom=(5, 25, 10),
                highway_bg=(8, 35, 15),
                note_colors={"primary": (120, 255, 80)},
                hit_line_color=(80, 220, 60),
                text_color=(220, 255, 220),
                accent_color=(160, 120, 60),
                beat_grid_color=(20, 60, 30),
                key_white=(230, 240, 225),
                key_black=(30, 40, 25),
            ),

            # 5. Galaxy — deep space, star-white notes, nebula pink
            Theme(
                id="galaxy",
                name="Galaxy",
                stars_required=60,
                description="Deep space with nebula colors",
                bg_top=(15, 5, 35),
                bg_bottom=(5, 2, 15),
                highway_bg=(10, 4, 25),
                note_colors={"primary": (240, 240, 255)},
                hit_line_color=(200, 100, 255),
                text_color=(230, 220, 255),
                accent_color=(255, 100, 180),
                beat_grid_color=(30, 15, 50),
                key_white=(220, 215, 240),
                key_black=(20, 10, 35),
            ),

            # 6. Retro — CRT green-on-black, scanline aesthetic
            Theme(
                id="retro",
                name="Retro",
                stars_required=80,
                description="Classic CRT green-on-black terminal",
                bg_top=(5, 10, 5),
                bg_bottom=(0, 5, 0),
                highway_bg=(3, 8, 3),
                note_colors={"primary": (0, 255, 65)},
                hit_line_color=(0, 200, 50),
                text_color=(0, 255, 65),
                accent_color=(0, 180, 45),
                beat_grid_color=(0, 40, 10),
                key_white=(30, 60, 30),
                key_black=(5, 15, 5),
            ),

            # 7. Candy — pastel pink/purple, bright multicolor
            Theme(
                id="candy",
                name="Candy",
                stars_required=100,
                description="Sweet pastels and bright multicolor notes",
                bg_top=(80, 40, 90),
                bg_bottom=(50, 20, 60),
                highway_bg=(65, 30, 75),
                note_colors={
                    "primary": (255, 150, 200),
                    "alt1": (150, 200, 255),
                    "alt2": (200, 255, 150),
                    "alt3": (255, 200, 100),
                },
                hit_line_color=(255, 180, 220),
                text_color=(255, 240, 250),
                accent_color=(255, 130, 200),
                beat_grid_color=(100, 50, 110),
                key_white=(255, 240, 245),
                key_black=(80, 40, 60),
            ),

            # 8. Gold — premium black/gold, metallic shimmer
            Theme(
                id="gold",
                name="Gold",
                stars_required=150,
                description="Premium black and gold elegance",
                bg_top=(20, 18, 10),
                bg_bottom=(8, 6, 2),
                highway_bg=(15, 13, 7),
                note_colors={"primary": (255, 215, 0)},
                hit_line_color=(255, 200, 50),
                text_color=(255, 230, 150),
                accent_color=(255, 215, 0),
                beat_grid_color=(50, 45, 20),
                key_white=(255, 245, 210),
                key_black=(30, 25, 10),
            ),
        ]
