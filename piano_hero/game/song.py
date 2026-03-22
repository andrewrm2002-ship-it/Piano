"""Song data model and JSON loader with difficulty calculation and categories."""

import json
import os
import math
from dataclasses import dataclass, field
from piano_hero.constants import note_name_to_midi


@dataclass
class Note:
    """A single note in a song."""
    note_name: str
    midi: int
    start_beat: float
    duration_beat: float
    start_time: float = 0.0
    end_time: float = 0.0
    # Runtime state
    hit: bool = False
    judgment: str = ""
    early_late: str = ""
    star_power: bool = False  # True if this is a star power note


@dataclass
class Song:
    """A complete song with metadata and notes."""
    title: str
    composer: str
    tempo: float
    time_signature: tuple
    difficulty: str
    notes: list = field(default_factory=list)
    filepath: str = ""
    duration: float = 0.0
    category: str = "Uncategorized"
    # Computed difficulty metrics
    difficulty_score: float = 0.0
    difficulty_tier: str = "easy"
    notes_per_second: float = 0.0
    range_span: int = 0

    @property
    def beat_duration(self) -> float:
        return 60.0 / self.tempo

    def unique_notes(self) -> list:
        return sorted(set(n.midi for n in self.notes))

    @property
    def duration_str(self) -> str:
        """Format duration as M:SS."""
        m = int(self.duration) // 60
        s = int(self.duration) % 60
        return f"{m}:{s:02d}"


def _guess_category(title: str, composer: str) -> str:
    """Guess song category from title/composer."""
    title_lower = title.lower()
    composer_lower = composer.lower()

    nursery_keywords = ['twinkle', 'mary had', 'london bridge', 'row row',
                        'hot cross', 'baa baa', 'jack and jill', 'humpty',
                        'three blind', 'itsy bitsy', 'frere', 'old macdonald',
                        'spider']
    folk_keywords = ['yankee', 'susanna', 'camptown', 'home on the range',
                     'scarborough', 'greensleeves', 'danny boy', 'auld lang',
                     'bonnie', 'shenandoah', 'saints', 'buffalo', 'skip to',
                     'coming round', 'clementine', 'aura lee']
    classical_keywords = ['ode to joy', 'minuet', 'canon in', 'fur elise',
                          'lullaby', 'morning', 'william tell', 'spring',
                          'trumpet voluntary', 'moonlight']
    classical_composers = ['beethoven', 'bach', 'petzold', 'pachelbel',
                           'brahms', 'grieg', 'rossini', 'vivaldi', 'clarke']
    holiday_keywords = ['jingle', 'silent night', 'christmas', 'joy to the world',
                        'deck the hall', 'o christmas', 'away in a manger']
    hymn_keywords = ['amazing grace', 'america the beautiful', 'battle hymn',
                     'swing low', 'simple gifts']

    for kw in nursery_keywords:
        if kw in title_lower:
            return "Nursery Rhymes"
    for kw in holiday_keywords:
        if kw in title_lower:
            return "Holiday"
    for kw in classical_keywords:
        if kw in title_lower:
            return "Classical"
    for comp in classical_composers:
        if comp in composer_lower:
            return "Classical"
    for kw in folk_keywords:
        if kw in title_lower:
            return "Folk & Traditional"
    for kw in hymn_keywords:
        if kw in title_lower:
            return "Hymns & Patriotic"

    return "Folk & Traditional"


def _compute_difficulty(song: Song):
    """Compute difficulty metrics for a song."""
    if not song.notes or song.duration <= 0:
        return

    song.notes_per_second = len(song.notes) / song.duration
    midis = [n.midi for n in song.notes]
    song.range_span = max(midis) - min(midis) if midis else 0
    unique = len(set(midis))

    # Difficulty score: 0-100 scale
    # Factors: note density, tempo, range, unique notes
    density_score = min(40, song.notes_per_second * 15)
    tempo_score = min(25, (song.tempo - 60) / 4)
    range_score = min(20, song.range_span * 1.2)
    unique_score = min(15, unique * 1.0)

    song.difficulty_score = density_score + tempo_score + range_score + unique_score

    # Map to tiers (generous thresholds so most songs are accessible)
    if song.difficulty_score < 30:
        song.difficulty_tier = 'beginner'
    elif song.difficulty_score < 55:
        song.difficulty_tier = 'easy'
    elif song.difficulty_score < 75:
        song.difficulty_tier = 'medium'
    else:
        song.difficulty_tier = 'hard'


def compute_song_difficulty_multiplier(song: Song) -> float:
    """Return a score multiplier (1.0-2.0) based on song difficulty."""
    # Normalized difficulty 0-1
    norm = min(1.0, song.difficulty_score / 80.0)
    return 1.0 + norm


def load_song(filepath: str) -> Song:
    """Load a song from a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tempo = float(data['tempo'])
    beat_dur = 60.0 / tempo
    ts = data.get('time_signature', [4, 4])

    notes = []
    for n in data['notes']:
        name = n['note']
        midi = note_name_to_midi(name)
        start_beat = float(n['start'])
        dur_beat = float(n['duration'])
        start_time = start_beat * beat_dur
        end_time = (start_beat + dur_beat) * beat_dur
        notes.append(Note(
            note_name=name,
            midi=midi,
            start_beat=start_beat,
            duration_beat=dur_beat,
            start_time=start_time,
            end_time=end_time,
        ))

    notes.sort(key=lambda n: n.start_time)

    category = data.get('category', '')

    song = Song(
        title=data.get('title', os.path.basename(filepath)),
        composer=data.get('composer', 'Unknown'),
        tempo=tempo,
        time_signature=tuple(ts),
        difficulty=data.get('difficulty', 'grade2'),
        notes=notes,
        filepath=filepath,
        category=category,
    )

    if notes:
        song.duration = max(n.end_time for n in notes)

    if not category:
        song.category = _guess_category(song.title, song.composer)

    _compute_difficulty(song)

    return song


def generate_difficulty_arrangement(song: Song, difficulty: str) -> list:
    """Generate a simplified note arrangement for Easy/Medium difficulty.

    Easy: Keep ~30% of notes (only on-beat quarter notes, no chords)
    Medium: Keep ~60% of notes (quarter + some eighth notes, basic chords)
    Hard: Keep all notes (100%)

    Returns a new list of Note objects (does not modify the original song).
    """
    from piano_hero.constants import DIFFICULTY_NOTE_RATIOS
    ratio = DIFFICULTY_NOTE_RATIOS.get(difficulty, 1.0)

    if ratio >= 1.0:
        return list(song.notes)  # Hard = full arrangement

    beat_dur = song.beat_duration
    notes = sorted(song.notes, key=lambda n: n.start_time)

    if ratio <= 0.35:
        # Easy: only notes that land on whole beats, skip chords (keep highest)
        beat_groups = {}
        for n in notes:
            beat = round(n.start_beat)
            if abs(n.start_beat - beat) < 0.1:
                if beat not in beat_groups or n.midi > beat_groups[beat].midi:
                    beat_groups[beat] = n
        kept = sorted(beat_groups.values(), key=lambda n: n.start_time)
    else:
        # Medium: keep notes on beats and half-beats, simplify chords to top note
        time_groups = {}
        for n in notes:
            # Quantize to half-beat
            half_beat = round(n.start_beat * 2) / 2
            if abs(n.start_beat - half_beat) < 0.15:
                if half_beat not in time_groups or n.midi > time_groups[half_beat].midi:
                    time_groups[half_beat] = n
        kept = sorted(time_groups.values(), key=lambda n: n.start_time)

    return kept


def mark_star_power_notes(notes: list, phrase_interval: int = 4):
    """Mark every Nth group of notes as star power notes.

    Modifies notes in-place by setting a `star_power` attribute.
    A 'phrase' is ~4 consecutive notes. Every phrase_interval-th phrase
    becomes a star power phrase.
    """
    from piano_hero.constants import STAR_POWER_NOTES_PER_PHRASE
    phrase_size = STAR_POWER_NOTES_PER_PHRASE
    for i, note in enumerate(notes):
        phrase_num = i // phrase_size
        note.star_power = (phrase_num % phrase_interval == 0)


def load_all_songs(songs_dir: str) -> list:
    """Load all .json song files from a directory."""
    songs = []
    if not os.path.isdir(songs_dir):
        return songs

    for filename in sorted(os.listdir(songs_dir)):
        if filename.endswith('.json'):
            try:
                song = load_song(os.path.join(songs_dir, filename))
                songs.append(song)
            except Exception as e:
                print(f"Warning: Failed to load {filename}: {e}")
    return songs


def is_song_unlocked(song: Song, total_stars: int) -> bool:
    """Check if a song is unlocked based on total stars earned.

    Beginner/Easy: always unlocked
    Medium: requires 5 total stars
    Hard: requires 15 total stars
    """
    from piano_hero.constants import DIFFICULTY_TIERS
    tier = getattr(song, 'difficulty_tier', 'easy')
    tier_info = DIFFICULTY_TIERS.get(tier, {})
    required = tier_info.get('unlock', 0)
    return total_stars >= required
