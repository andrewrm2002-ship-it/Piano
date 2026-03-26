"""Global constants for Piano Hero."""

import math

# ── Display ──────────────────────────────────────────────────────────────────
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
TARGET_FPS = 60
TITLE = "Piano Hero"

# ── Colors (arcade neon theme) ───────────────────────────────────────────────
BG_COLOR = (15, 0, 30)
BG_GRADIENT_TOP = (25, 0, 50)
BG_GRADIENT_BOTTOM = (10, 0, 20)

HIT_LINE_COLOR = (255, 255, 255)
HIT_LINE_GLOW = (100, 100, 255, 80)

# Note colors by octave
OCTAVE_COLORS = {
    2: (0, 200, 255),     # Cyan
    3: (0, 255, 150),     # Teal/green
    4: (255, 255, 0),     # Yellow
    5: (255, 100, 255),   # Magenta
    6: (255, 150, 50),    # Orange
}
DEFAULT_NOTE_COLOR = (200, 200, 200)

# Judgment colors
COLOR_PERFECT = (255, 215, 0)    # Gold
COLOR_GOOD = (0, 255, 100)       # Green
COLOR_OK = (100, 150, 255)       # Blue
COLOR_MISS = (255, 50, 50)       # Red
COLOR_EARLY = (255, 180, 50)     # Orange-ish
COLOR_LATE = (180, 100, 255)     # Purple-ish

# UI colors
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (150, 150, 150)
COLOR_DARK_GRAY = (60, 60, 60)
COLOR_BLACK = (0, 0, 0)
COLOR_ACCENT = (0, 200, 255)
COLOR_STREAK_FLAME = (255, 120, 0)
COLOR_WRONG_NOTE = (255, 80, 80)

# Piano key colors
KEY_WHITE = (240, 240, 240)
KEY_WHITE_PRESSED = (180, 220, 255)
KEY_BLACK = (30, 30, 30)
KEY_BLACK_PRESSED = (80, 120, 200)
KEY_HIGHLIGHT = (0, 200, 255)

# Star colors
COLOR_STAR_FILLED = (255, 215, 0)
COLOR_STAR_EMPTY = (60, 60, 60)

# Letter grade colors
GRADE_COLORS = {
    'S': (255, 215, 0),
    'A': (0, 255, 100),
    'B': (100, 200, 255),
    'C': (255, 255, 100),
    'D': (255, 150, 50),
    'F': (255, 50, 50),
}

# ── Audio ────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100
BUFFER_SIZE = 2048         # Samples for pitch detection window
BUFFER_SIZE_HIGH = 1024    # Smaller buffer for notes above C4
HOP_SIZE = 512             # Samples between pitch estimates
CHANNELS = 1               # Mono input
CONFIDENCE_THRESHOLD = 0.3 # Min confidence to accept a pitch (YIN)
SILENCE_THRESHOLD = 0.01   # RMS below this = silence (default, adapted at runtime)
ONSET_THRESHOLD = 3.0      # RMS jump ratio to detect note onset
NOISE_FLOOR_SAMPLES = 44100  # 1 second of audio for noise floor measurement

# ── Pitch Detection ─────────────────────────────────────────────────────────
# PSR-74: 49 keys, C2 to C6
MIN_FREQ = 60.0    # Just below C2 (65.41 Hz)
MAX_FREQ = 1100.0  # Just above C6 (1046.50 Hz)
HIGH_FREQ_CUTOFF = 261.63  # C4 — above this we can use smaller buffer
MIN_MIDI = 36      # C2
MAX_MIDI = 84      # C6

# ── Note Names ───────────────────────────────────────────────────────────────
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Enharmonic equivalents for parsing song files
ENHARMONIC = {
    'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#',
    'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B',
    'B#': 'C', 'E#': 'F',
}

def note_name_to_midi(name: str) -> int:
    """Convert note name like 'C4', 'F#3', 'Bb5' to MIDI number."""
    name = name.strip()
    if len(name) == 2:
        note_part, octave = name[0], int(name[1])
    elif len(name) == 3:
        note_part, octave = name[:2], int(name[2])
    else:
        raise ValueError(f"Invalid note name: {name}")

    original_part = note_part
    if note_part in ENHARMONIC:
        note_part = ENHARMONIC[note_part]
        if original_part == 'B#':
            octave += 1
        elif original_part == 'Cb':
            octave -= 1

    if note_part not in NOTE_NAMES:
        raise ValueError(f"Unknown note: {note_part}")

    note_index = NOTE_NAMES.index(note_part)
    return (octave + 1) * 12 + note_index


def midi_to_note_name(midi: int) -> str:
    """Convert MIDI number to note name like 'C4'."""
    octave = (midi // 12) - 1
    note = NOTE_NAMES[midi % 12]
    return f"{note}{octave}"


def midi_to_freq(midi: int) -> float:
    """Convert MIDI number to frequency in Hz."""
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def freq_to_midi(freq: float) -> int:
    """Convert frequency to nearest MIDI number."""
    if freq <= 0:
        return 0
    return round(69 + 12 * math.log2(freq / 440.0))


# Build lookup table: MIDI -> frequency
MIDI_FREQUENCIES = {m: midi_to_freq(m) for m in range(MIN_MIDI, MAX_MIDI + 1)}

# ── Timing ───────────────────────────────────────────────────────────────────
PERFECT_WINDOW = 0.150
GOOD_WINDOW = 0.300
OK_WINDOW = 0.500
FIRST_NOTE_GRACE = 0.800   # Extra grace period for the first note

# Audio detection pipeline latency (seconds).
# Notes are visually shifted so they cross the hit line this far BEFORE
# their musical target time, giving the detection pipeline time to process.
# Pipeline latency compensation (seconds).
# Calibrated value: detection arrives ~15ms late on average.
# Visual notes are shifted by this amount so they cross the hit line
# at the moment the player should physically press the key.
AUDIO_PIPELINE_LATENCY = 0.0

# Points per judgment (base — continuous scoring interpolates within bands)
PERFECT_POINTS = 100
GOOD_POINTS = 60
OK_POINTS = 30
MISS_POINTS = 0

# Continuous scoring bands: (inner_edge, outer_edge, max_pts, min_pts)
# Points linearly interpolate from max_pts (near inner) to min_pts (near outer)
SCORING_BANDS = [
    (0.0, PERFECT_WINDOW, PERFECT_POINTS, PERFECT_POINTS),  # Perfect: flat 100
    (PERFECT_WINDOW, GOOD_WINDOW, 90, GOOD_POINTS),         # Good: 90→60
    (GOOD_WINDOW, OK_WINDOW, 50, OK_POINTS),                # OK: 50→30
]

# Wrong note penalty
WRONG_NOTE_PENALTY = 30        # Points deducted per wrong note
WRONG_NOTE_STREAK_RESET = True # Wrong note breaks streak

# Hold duration scoring
HOLD_BONUS_RATIO = 0.5        # Up to 50% bonus for perfect hold
HOLD_MIN_DURATION = 0.3       # Don't score holds shorter than this (seconds)

# Streak multiplier (with gradual recovery)
STREAK_MILESTONE = 10
MAX_MULTIPLIER = 4.0
MULTIPLIER_STEP = 0.5
MISS_MULTIPLIER_DROP = 0.5
MIN_MULTIPLIER = 1.0

# Star thresholds (percentage of max score)
STAR_THRESHOLDS = [0.0, 0.40, 0.60, 0.75, 0.90]

# Letter grades
GRADE_THRESHOLDS = [
    (0.95, 'S'), (0.85, 'A'), (0.70, 'B'),
    (0.55, 'C'), (0.40, 'D'), (0.0, 'F'),
]

# ── Song Difficulty ──────────────────────────────────────────────────────────
DIFFICULTY_TIERS = {
    'beginner': {'label': 'Beginner', 'color': (0, 200, 100), 'unlock': 0},
    'easy': {'label': 'Easy', 'color': (100, 200, 255), 'unlock': 0},
    'medium': {'label': 'Medium', 'color': (255, 200, 50), 'unlock': 5},
    'hard': {'label': 'Hard', 'color': (255, 100, 50), 'unlock': 15},
}

# Song categories
SONG_CATEGORIES = [
    'All', 'Nursery Rhymes', 'Folk & Traditional', 'Classical',
    'Holiday', 'Hymns & Patriotic',
]

# ── Combo Announcements ─────────────────────────────────────────────────────
COMBO_MILESTONES = {
    10: ("ON FIRE!", COLOR_STREAK_FLAME),
    25: ("AMAZING!", (255, 200, 0)),
    50: ("UNSTOPPABLE!", (255, 100, 255)),
    75: ("LEGENDARY!", (0, 255, 255)),
    100: ("GODLIKE!", (255, 255, 255)),
}

# ── Health / Performance Meter ────────────────────────────────────────────────
HEALTH_START = 0.5            # Start at 50%
HEALTH_HIT_GAIN = 0.03        # Gain per correct hit
HEALTH_PERFECT_GAIN = 0.05    # Gain for perfect hit
HEALTH_MISS_DRAIN = 0.08      # Drain per miss (3x the gain — matches Guitar Hero)
HEALTH_WRONG_DRAIN = 0.06     # Drain per wrong note
HEALTH_IDLE_DRAIN = 0.0       # No passive drain
HEALTH_MIN = 0.0
HEALTH_MAX = 1.0
HEALTH_FAIL_THRESHOLD = 0.0   # Fail when health reaches 0
NO_FAIL_DEFAULT = True         # Default to no-fail for kids

# Health meter colors
COLOR_HEALTH_GREEN = (0, 220, 60)
COLOR_HEALTH_YELLOW = (255, 220, 0)
COLOR_HEALTH_RED = (255, 50, 50)

# ── Star Power / Overdrive ───────────────────────────────────────────────────
STAR_POWER_NOTES_PER_PHRASE = 4    # Every N-th phrase of notes is a star power phrase
STAR_POWER_GAIN_PER_NOTE = 0.12   # Gain per star power note hit
STAR_POWER_DURATION = 10.0        # Seconds of active star power
STAR_POWER_MULTIPLIER = 2.0       # Doubles current multiplier when active
STAR_POWER_HEALTH_BOOST = 0.02    # Extra health gain per hit during star power
COLOR_STAR_POWER = (0, 200, 255)  # Cyan
COLOR_STAR_POWER_GLOW = (100, 220, 255)

# ── Difficulty Arrangements ──────────────────────────────────────────────────
# Easy: only on-beat quarter notes (keep ~30% of notes)
# Medium: quarter + eighth notes (keep ~60% of notes)
# Hard: full arrangement (100% of notes)
DIFFICULTY_NOTE_RATIOS = {
    'Easy': 0.30,
    'Medium': 0.60,
    'Hard': 1.0,
}

# ── Game Layout ──────────────────────────────────────────────────────────────
HIGHWAY_WIDTH_RATIO = 0.72
KEYBOARD_HEIGHT = 100
HIT_LINE_Y_RATIO = 0.82
PREVIEW_BEATS = 4.0

# ── Menu / UI ────────────────────────────────────────────────────────────────
MENU_BG = (20, 5, 40)
SONG_CARD_HEIGHT = 70
SONG_CARD_PADDING = 8
SCROLL_SPEED = 30

# ── Sound Effects ────────────────────────────────────────────────────────────
SFX_HIT_FREQ = 880       # Hz for hit sound
SFX_MISS_FREQ = 220      # Hz for miss sound
SFX_PERFECT_FREQ = 1320  # Hz for perfect sound
SFX_DURATION = 0.08      # Seconds
SFX_VOLUME = 0.3

# ── Audio Passthrough ────────────────────────────────────────────────────────
PASSTHROUGH_VOLUME = 0.25
PASSTHROUGH_DURATION = 0.4     # Sustain time for synth note playback

# ── Statistics ───────────────────────────────────────────────────────────────
STATS_FILE = "stats.json"
