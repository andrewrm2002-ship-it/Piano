"""User settings — audio device, calibration, preferences."""

import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "settings.json")


DEFAULT_SETTINGS = {
    "audio_device": None,
    "calibration_offset": 0.0,
    "scroll_speed": 1.0,
    "volume": 0.8,
    "show_note_names": True,
    "fullscreen": False,
    "sfx_enabled": True,
    "practice_speed": 1.0,
    "show_timing_bar": True,
    "show_score_popups": True,
    "passthrough_enabled": True,
    "no_fail": True,
    "wait_mode": False,
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, 'r') as f:
            saved = json.load(f)
        settings = dict(DEFAULT_SETTINGS)
        settings.update(saved)
        return settings
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)
