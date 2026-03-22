"""Family profile system — supports 2-4 player profiles."""

import json
import os

PROFILES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "profiles.json")

DEFAULT_PROFILES = {
    "active_profile": "Player 1",
    "profiles": {
        "Player 1": {"color": [0, 200, 255]},
        "Player 2": {"color": [255, 100, 255]},
    }
}


def load_profiles() -> dict:
    if not os.path.exists(PROFILES_FILE):
        return dict(DEFAULT_PROFILES)
    try:
        with open(PROFILES_FILE, 'r') as f:
            data = json.load(f)
        for name, prof in data.get('profiles', {}).items():
            if 'color' in prof and isinstance(prof['color'], list):
                prof['color'] = tuple(prof['color'])
        return data
    except Exception:
        return dict(DEFAULT_PROFILES)


def save_profiles(profiles: dict):
    os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
    with open(PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)


def get_active_profile(profiles: dict) -> str:
    return profiles.get('active_profile', 'Player 1')


def set_active_profile(profiles: dict, name: str):
    profiles['active_profile'] = name
    save_profiles(profiles)


def get_all_profile_names(profiles: dict) -> list:
    """Return a list of all profile names, useful for leaderboard lookups."""
    return list(profiles.get('profiles', {}).keys())


def get_profile_color(profiles: dict, name: str) -> tuple:
    """Return the color tuple for a profile, defaulting to white."""
    prof = profiles.get('profiles', {}).get(name, {})
    color = prof.get('color', [255, 255, 255])
    return tuple(color) if isinstance(color, list) else color


def get_profile_data_dir(profile_name: str) -> str:
    """Return the data directory for a specific profile."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    safe_name = "".join(c if c.isalnum() or c in ' _-' else '_' for c in profile_name)
    profile_dir = os.path.join(base, "data", "profiles", safe_name)
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir
