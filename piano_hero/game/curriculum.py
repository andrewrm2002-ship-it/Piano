"""
Structured piano learning curriculum.
Organizes songs and exercises into progressive lessons.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Lesson:
    id: str                    # e.g., "1.1", "1.2", "2.1"
    title: str                 # e.g., "Finding Middle C"
    unit: int                  # Unit number (1-8)
    description: str           # What you'll learn
    tip: str                   # Pre-lesson educational tip
    song_file: str             # Which song to play
    difficulty: str            # "Easy", "Medium", "Hard"
    hand_mode: str             # "right", "left", "both"
    target_accuracy: float     # Required accuracy to pass (0.0-1.0)
    target_stars: int          # Required stars to pass (1-5)
    unlocks: list = field(default_factory=list)    # Lesson IDs this unlocks
    concepts: list = field(default_factory=list)   # Tags: ["middle_c", "quarter_notes", etc.]


# ── Unit names ──────────────────────────────────────────────────────────────

UNIT_NAMES = {
    1: "Getting Started",
    2: "Reading Rhythms",
    3: "Expanding Range",
    4: "Left Hand Introduction",
    5: "Hands Together",
    6: "Intermediate Melodies",
    7: "Advanced Pieces",
    8: "Performance",
}

UNIT_DESCRIPTIONS = {
    1: "Learn the basics with your right hand in C position.",
    2: "Explore different note durations and rhythmic patterns.",
    3: "Move beyond five notes and encounter sharps and flats.",
    4: "Introduce your left hand with simple chord patterns.",
    5: "Coordinate both hands playing together for the first time.",
    6: "Take on more complex pieces with both hands.",
    7: "Challenge yourself with famous classical arrangements.",
    8: "Put it all together in full performance pieces.",
}


def _build_curriculum() -> list[Lesson]:
    """Construct the full curriculum of lessons."""
    lessons = []

    # ── Unit 1: Getting Started (Right Hand, C Position) ────────────────

    lessons.append(Lesson(
        id="1.1", title="Finding Middle C", unit=1,
        description="Play your first notes using middle C and nearby keys.",
        tip="Middle C is the white key just left of the group of two black keys in the center of the keyboard. Place your right thumb on it.",
        song_file="hot_cross_buns.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.60, target_stars=1,
        unlocks=["1.2"],
        concepts=["middle_c", "right_hand", "c_position"],
    ))

    lessons.append(Lesson(
        id="1.2", title="Three Note Songs", unit=1,
        description="Play simple melodies using three notes: C, D, and E.",
        tip="Keep your fingers curved and relaxed. Each finger gets its own key.",
        song_file="mary_had_a_little_lamb.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.65, target_stars=1,
        unlocks=["1.3"],
        concepts=["three_notes", "right_hand", "c_position"],
    ))

    lessons.append(Lesson(
        id="1.3", title="Five Finger Position", unit=1,
        description="Use all five fingers of your right hand: C through G.",
        tip="Assign one finger per key: thumb on C, index on D, middle on E, ring on F, pinky on G.",
        song_file="twinkle_twinkle.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["1.4"],
        concepts=["five_finger", "right_hand", "c_position"],
    ))

    lessons.append(Lesson(
        id="1.4", title="Stepping Up and Down", unit=1,
        description="Practice smooth stepwise motion up and down the keys.",
        tip="When moving between neighboring notes, keep your hand steady and let your fingers do the work.",
        song_file="london_bridge.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["1.5"],
        concepts=["stepwise_motion", "right_hand"],
    ))

    lessons.append(Lesson(
        id="1.5", title="Putting It Together", unit=1,
        description="Combine everything from Unit 1 in a fun song.",
        tip="Focus on keeping a steady tempo. Try counting along: 1, 2, 3, 4.",
        song_file="row_row_row.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.75, target_stars=2,
        unlocks=["2.1"],
        concepts=["review", "right_hand", "steady_tempo"],
    ))

    # ── Unit 2: Reading Rhythms (Right Hand) ────────────────────────────

    lessons.append(Lesson(
        id="2.1", title="Quarter and Half Notes", unit=2,
        description="Learn the difference between quarter notes and half notes.",
        tip="A quarter note gets one beat. A half note gets two beats — hold it twice as long!",
        song_file="frere_jacques.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["2.2"],
        concepts=["quarter_notes", "half_notes", "rhythm"],
    ))

    lessons.append(Lesson(
        id="2.2", title="Whole Notes", unit=2,
        description="Practice holding notes for four full beats.",
        tip="A whole note fills an entire measure. Count 1-2-3-4 while holding the key down.",
        song_file="amazing_grace.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.65, target_stars=2,
        unlocks=["2.3"],
        concepts=["whole_notes", "sustain", "rhythm"],
    ))

    lessons.append(Lesson(
        id="2.3", title="Dotted Notes", unit=2,
        description="A dot after a note makes it 50% longer.",
        tip="A dotted half note = 3 beats instead of 2. Listen for the longer, flowing feel.",
        song_file="greensleeves.json",
        difficulty="Easy", hand_mode="right",
        target_accuracy=0.65, target_stars=2,
        unlocks=["2.4"],
        concepts=["dotted_notes", "compound_time", "rhythm"],
    ))

    lessons.append(Lesson(
        id="2.4", title="Eighth Notes", unit=2,
        description="Play faster notes — two eighth notes per beat.",
        tip="Eighth notes move twice as fast as quarter notes. Count: 1-and-2-and-3-and-4-and.",
        song_file="old_macdonald.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.65, target_stars=2,
        unlocks=["2.5"],
        concepts=["eighth_notes", "faster_rhythm", "subdivisions"],
    ))

    lessons.append(Lesson(
        id="2.5", title="Mixed Rhythms", unit=2,
        description="Combine quarter, half, whole, and eighth notes together.",
        tip="When rhythms change, keep your internal pulse steady. Tap your foot to stay on beat.",
        song_file="yankee_doodle.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["3.1"],
        concepts=["mixed_rhythms", "right_hand"],
    ))

    # ── Unit 3: Expanding Range (Right Hand) ────────────────────────────

    lessons.append(Lesson(
        id="3.1", title="Moving Beyond Five Notes", unit=3,
        description="Shift your hand position to reach new notes.",
        tip="When a melody goes beyond five notes, smoothly shift your hand. Practice the shift slowly first.",
        song_file="oh_susanna.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.65, target_stars=2,
        unlocks=["3.2"],
        concepts=["hand_shift", "extended_range", "right_hand"],
    ))

    lessons.append(Lesson(
        id="3.2", title="Larger Intervals", unit=3,
        description="Jump between notes that are further apart.",
        tip="An interval is the distance between two notes. Practice skipping keys to build accuracy.",
        song_file="ode_to_joy.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["3.3"],
        concepts=["intervals", "skips", "right_hand"],
    ))

    lessons.append(Lesson(
        id="3.3", title="Sharps and Flats", unit=3,
        description="Use the black keys for sharps and flats.",
        tip="Sharp (#) means one key higher, flat (b) means one key lower. Black keys are just half steps!",
        song_file="greensleeves.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.65, target_stars=2,
        unlocks=["3.4"],
        concepts=["sharps", "flats", "accidentals", "black_keys"],
    ))

    lessons.append(Lesson(
        id="3.4", title="Wider Melodies", unit=3,
        description="Play melodies that span a wider range of notes.",
        tip="Keep your wrist relaxed and floating above the keys. Let your arm guide larger movements.",
        song_file="danny_boy.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.70, target_stars=2,
        unlocks=["3.5"],
        concepts=["wide_range", "expression", "right_hand"],
    ))

    lessons.append(Lesson(
        id="3.5", title="Challenge Song", unit=3,
        description="Test all your right-hand skills in a lively tune.",
        tip="This one moves fast! Start at a slower speed, then work your way up.",
        song_file="camptown_races.json",
        difficulty="Medium", hand_mode="right",
        target_accuracy=0.75, target_stars=3,
        unlocks=["4.1"],
        concepts=["challenge", "right_hand", "review"],
    ))

    # ── Unit 4: Left Hand Introduction ──────────────────────────────────

    lessons.append(Lesson(
        id="4.1", title="Left Hand Basics", unit=4,
        description="Introduce your left hand with simple bass notes and chords.",
        tip="Place your left pinky on the C below middle C. Your left hand mirrors your right hand position.",
        song_file="hot_cross_buns.json",
        difficulty="Easy", hand_mode="left",
        target_accuracy=0.60, target_stars=1,
        unlocks=["4.2"],
        concepts=["left_hand", "bass_clef", "introduction"],
    ))

    lessons.append(Lesson(
        id="4.2", title="Left Hand Patterns", unit=4,
        description="Play repeating left-hand accompaniment patterns.",
        tip="Many songs use simple repeating patterns in the left hand. Find the pattern and it becomes easy!",
        song_file="twinkle_chords.json",
        difficulty="Easy", hand_mode="left",
        target_accuracy=0.65, target_stars=2,
        unlocks=["4.3"],
        concepts=["left_hand", "patterns", "accompaniment"],
    ))

    lessons.append(Lesson(
        id="4.3", title="Chord Shapes", unit=4,
        description="Learn basic chord shapes: C major, F major, G major.",
        tip="A chord is three or more notes played together. Keep your fingers curved and press all keys at once.",
        song_file="amazing_grace_chords.json",
        difficulty="Easy", hand_mode="left",
        target_accuracy=0.65, target_stars=2,
        unlocks=["4.4"],
        concepts=["chords", "left_hand", "c_major", "f_major", "g_major"],
    ))

    lessons.append(Lesson(
        id="4.4", title="Moving Chords", unit=4,
        description="Transition smoothly between different chord shapes.",
        tip="Move your whole hand as a unit when switching chords. Lift slightly, shift, and place all fingers together.",
        song_file="jingle_bells_chords.json",
        difficulty="Medium", hand_mode="left",
        target_accuracy=0.65, target_stars=2,
        unlocks=["4.5"],
        concepts=["chord_changes", "left_hand", "transitions"],
    ))

    lessons.append(Lesson(
        id="4.5", title="Left Hand Challenge", unit=4,
        description="Put your left hand skills to the test.",
        tip="Relax your shoulders and breathe. Tension is the enemy of good piano playing.",
        song_file="silent_night_chords.json",
        difficulty="Medium", hand_mode="left",
        target_accuracy=0.70, target_stars=2,
        unlocks=["5.1"],
        concepts=["left_hand", "challenge", "review"],
    ))

    # ── Unit 5: Hands Together (Easy) ───────────────────────────────────

    lessons.append(Lesson(
        id="5.1", title="First Hands Together", unit=5,
        description="Play with both hands for the first time!",
        tip="Start very slowly. Practice each hand separately first, then combine them at half speed.",
        song_file="twinkle_chords.json",
        difficulty="Easy", hand_mode="both",
        target_accuracy=0.55, target_stars=1,
        unlocks=["5.2"],
        concepts=["hands_together", "coordination", "introduction"],
    ))

    lessons.append(Lesson(
        id="5.2", title="Slow and Steady", unit=5,
        description="Build two-hand coordination at a comfortable pace.",
        tip="If you make a mistake, don't stop — keep going! Stopping breaks your rhythm more than a wrong note.",
        song_file="amazing_grace_chords.json",
        difficulty="Easy", hand_mode="both",
        target_accuracy=0.60, target_stars=2,
        unlocks=["5.3"],
        concepts=["hands_together", "slow_practice", "persistence"],
    ))

    lessons.append(Lesson(
        id="5.3", title="Simple Coordination", unit=5,
        description="Right hand melody with left hand chords.",
        tip="Your left hand plays the chord on beat 1, then your right hand carries the melody. Think of them as partners.",
        song_file="jingle_bells_chords.json",
        difficulty="Easy", hand_mode="both",
        target_accuracy=0.60, target_stars=2,
        unlocks=["5.4"],
        concepts=["hands_together", "melody_and_chords"],
    ))

    lessons.append(Lesson(
        id="5.4", title="Building Confidence", unit=5,
        description="Gain confidence with both hands on a marching tune.",
        tip="March along with the beat! A strong sense of pulse helps keep both hands synchronized.",
        song_file="when_saints_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.60, target_stars=2,
        unlocks=["5.5"],
        concepts=["hands_together", "confidence", "marching"],
    ))

    lessons.append(Lesson(
        id="5.5", title="Hands Together Challenge", unit=5,
        description="A beautiful song to celebrate your two-hand skills.",
        tip="This piece has a flowing feel. Let the melody sing while the chords support underneath.",
        song_file="auld_lang_syne_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.65, target_stars=2,
        unlocks=["6.1"],
        concepts=["hands_together", "challenge", "expression"],
    ))

    # ── Unit 6: Intermediate Melodies ───────────────────────────────────

    lessons.append(Lesson(
        id="6.1", title="Classical Introduction", unit=6,
        description="Play your first classical piece with both hands.",
        tip="Beethoven wrote Ode to Joy as a celebration of humanity. Play it with warmth and joy!",
        song_file="ode_to_joy_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.65, target_stars=2,
        unlocks=["6.2"],
        concepts=["classical", "beethoven", "both_hands"],
    ))

    lessons.append(Lesson(
        id="6.2", title="Minor Keys", unit=6,
        description="Explore the emotional sound of minor keys.",
        tip="Minor keys have a darker, more emotional sound. Listen for how the mood changes compared to major keys.",
        song_file="scarborough_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.65, target_stars=2,
        unlocks=["6.3"],
        concepts=["minor_key", "emotion", "both_hands"],
    ))

    lessons.append(Lesson(
        id="6.3", title="Waltz Time", unit=6,
        description="Play in 3/4 time with a gentle waltz feel.",
        tip="Waltz time has three beats per measure: strong-weak-weak. Feel the gentle sway of 1-2-3, 1-2-3.",
        song_file="brahms_lullaby_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.65, target_stars=2,
        unlocks=["6.4"],
        concepts=["waltz", "three_four_time", "gentle"],
    ))

    lessons.append(Lesson(
        id="6.4", title="Expression", unit=6,
        description="Add feeling and dynamics to your playing.",
        tip="Music isn't just about the right notes — it's about how you play them. Try playing some parts softer and others louder.",
        song_file="danny_boy_chords.json",
        difficulty="Medium", hand_mode="both",
        target_accuracy=0.70, target_stars=3,
        unlocks=["6.5"],
        concepts=["dynamics", "expression", "phrasing"],
    ))

    lessons.append(Lesson(
        id="6.5", title="Intermediate Challenge", unit=6,
        description="A soulful spiritual to test your intermediate skills.",
        tip="This spiritual has a deep, swinging feel. Let the melody breathe between phrases.",
        song_file="swing_low_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.65, target_stars=2,
        unlocks=["7.1"],
        concepts=["challenge", "spiritual", "swing_feel"],
    ))

    # ── Unit 7: Advanced Pieces ─────────────────────────────────────────

    lessons.append(Lesson(
        id="7.1", title="Fur Elise", unit=7,
        description="Tackle Beethoven's beloved piano piece.",
        tip="The opening motif of Fur Elise is one of the most recognized melodies in music. Take it slowly and nail the pattern.",
        song_file="fur_elise_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.60, target_stars=2,
        unlocks=["7.2"],
        concepts=["beethoven", "classical", "advanced"],
    ))

    lessons.append(Lesson(
        id="7.2", title="Canon in D", unit=7,
        description="Play Pachelbel's famous Canon arrangement.",
        tip="The Canon's beauty is in its repeating bass line. Master the left hand pattern first, then add the melody.",
        song_file="canon_in_d_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.60, target_stars=2,
        unlocks=["7.3"],
        concepts=["pachelbel", "baroque", "repeating_bass"],
    ))

    lessons.append(Lesson(
        id="7.3", title="Greensleeves Full", unit=7,
        description="The complete arrangement with melody and accompaniment.",
        tip="This English folk tune is in 3/4 time with a minor key. Let it flow like a gentle river.",
        song_file="greensleeves_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.65, target_stars=3,
        unlocks=["7.4"],
        concepts=["folk", "minor_key", "full_arrangement"],
    ))

    lessons.append(Lesson(
        id="7.4", title="Simple Gifts", unit=7,
        description="A beautiful Shaker hymn in a full arrangement.",
        tip="Simple Gifts is about finding joy in simplicity. Play it cleanly and let the melody shine.",
        song_file="simple_gifts_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.65, target_stars=3,
        unlocks=["7.5"],
        concepts=["hymn", "simplicity", "clarity"],
    ))

    lessons.append(Lesson(
        id="7.5", title="Graduation Piece", unit=7,
        description="Your graduation from the structured curriculum.",
        tip="You've come so far! Play this with all the expression and skill you've developed.",
        song_file="silent_night_chords.json",
        difficulty="Hard", hand_mode="both",
        target_accuracy=0.70, target_stars=3,
        unlocks=["8.1"],
        concepts=["graduation", "expression", "mastery"],
    ))

    # ── Unit 8: Performance ─────────────────────────────────────────────

    performance_songs = [
        ("8.1", "Performance: Turkish March", "turkish_march_chords.json",
         "Mozart's famous Turkish March — a true test of speed and precision.",
         "Start slow and build up speed gradually. Accuracy first, tempo second."),
        ("8.2", "Performance: The Entertainer", "entertainer_chords.json",
         "Scott Joplin's ragtime classic demands crisp rhythm and swing.",
         "Ragtime has a bouncy, syncopated feel. Keep the left hand steady while the right hand plays off the beat."),
        ("8.3", "Performance: Habanera", "habanera_chords.json",
         "Bizet's sultry opera melody with dramatic flair.",
         "This piece has a slow, sultry Spanish rhythm. Let the chromatic melody slither downward."),
        ("8.4", "Performance: Blue Danube", "blue_danube_chords.json",
         "Strauss's famous waltz in a full piano arrangement.",
         "The quintessential waltz. Feel the elegant 1-2-3 sway of Viennese ballroom dancing."),
        ("8.5", "Performance: Prelude in C", "prelude_c_major_chords.json",
         "Bach's Prelude in C Major — a masterful rolling arpeggio pattern.",
         "Each measure is a broken chord. Let your fingers roll smoothly across the pattern."),
    ]

    for i, (lid, title, song, desc, tip) in enumerate(performance_songs):
        next_id = performance_songs[i + 1][0] if i < len(performance_songs) - 1 else []
        unlocks = [next_id] if isinstance(next_id, str) else next_id
        lessons.append(Lesson(
            id=lid, title=title, unit=8,
            description=desc, tip=tip,
            song_file=song,
            difficulty="Hard", hand_mode="both",
            target_accuracy=0.70, target_stars=3,
            unlocks=unlocks,
            concepts=["performance", "mastery"],
        ))

    return lessons


class CurriculumManager:
    """Manages curriculum progression, unlocking, and persistence."""

    PROGRESS_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "curriculum_progress.json"
    )

    def __init__(self):
        self.lessons: list[Lesson] = _build_curriculum()
        self._lesson_map: dict[str, Lesson] = {l.id: l for l in self.lessons}
        self.progress: dict = self._load_progress()

    # ── Query methods ───────────────────────────────────────────────────

    def get_units(self) -> list[dict]:
        """Return list of unit dicts with id, name, description, and lesson count."""
        units = []
        for unit_num in sorted(UNIT_NAMES.keys()):
            unit_lessons = self.get_lessons_for_unit(unit_num)
            units.append({
                "unit": unit_num,
                "name": UNIT_NAMES[unit_num],
                "description": UNIT_DESCRIPTIONS.get(unit_num, ""),
                "lesson_count": len(unit_lessons),
                "completed": sum(1 for l in unit_lessons if self.is_lesson_completed(l.id)),
                "progress": self.get_unit_progress(unit_num),
            })
        return units

    def get_lessons_for_unit(self, unit: int) -> list[Lesson]:
        """Return all lessons belonging to a unit, ordered by lesson id."""
        return [l for l in self.lessons if l.unit == unit]

    def is_lesson_unlocked(self, lesson_id: str) -> bool:
        """A lesson is unlocked if it's 1.1 or if any lesson that unlocks it is completed."""
        if lesson_id == "1.1":
            return True
        for lesson in self.lessons:
            if lesson_id in lesson.unlocks and self.is_lesson_completed(lesson.id):
                return True
        return False

    def is_lesson_completed(self, lesson_id: str) -> bool:
        """A lesson is completed if the player met accuracy and star targets."""
        entry = self.progress.get("lessons", {}).get(lesson_id)
        if entry is None:
            return False
        return entry.get("completed", False)

    def complete_lesson(self, lesson_id: str, accuracy: float, stars: int):
        """Record a lesson attempt. Marks completed if targets are met."""
        lesson = self._lesson_map.get(lesson_id)
        if lesson is None:
            return

        lessons_dict = self.progress.setdefault("lessons", {})
        entry = lessons_dict.setdefault(lesson_id, {
            "completed": False,
            "best_accuracy": 0.0,
            "best_stars": 0,
            "attempts": 0,
        })

        entry["attempts"] = entry.get("attempts", 0) + 1
        entry["best_accuracy"] = max(entry.get("best_accuracy", 0.0), accuracy)
        entry["best_stars"] = max(entry.get("best_stars", 0), stars)

        if accuracy >= lesson.target_accuracy and stars >= lesson.target_stars:
            entry["completed"] = True

        self._save_progress()

    def get_next_lesson(self) -> Optional[Lesson]:
        """Return the next uncompleted, unlocked lesson (in order)."""
        for lesson in self.lessons:
            if not self.is_lesson_completed(lesson.id) and self.is_lesson_unlocked(lesson.id):
                return lesson
        return None

    def get_current_unit(self) -> int:
        """Return the unit number of the next uncompleted lesson."""
        next_lesson = self.get_next_lesson()
        if next_lesson is None:
            return 8  # All done
        return next_lesson.unit

    def get_unit_progress(self, unit: int) -> float:
        """Return 0.0-1.0 progress for a unit."""
        unit_lessons = self.get_lessons_for_unit(unit)
        if not unit_lessons:
            return 0.0
        completed = sum(1 for l in unit_lessons if self.is_lesson_completed(l.id))
        return completed / len(unit_lessons)

    def get_total_progress(self) -> float:
        """Return 0.0-1.0 overall curriculum progress."""
        if not self.lessons:
            return 0.0
        completed = sum(1 for l in self.lessons if self.is_lesson_completed(l.id))
        return completed / len(self.lessons)

    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        """Look up a lesson by ID."""
        return self._lesson_map.get(lesson_id)

    def get_lesson_progress(self, lesson_id: str) -> Optional[dict]:
        """Return progress dict for a lesson, or None if never attempted."""
        return self.progress.get("lessons", {}).get(lesson_id)

    # ── Persistence ─────────────────────────────────────────────────────

    def _load_progress(self) -> dict:
        """Load progress from data/curriculum_progress.json."""
        if os.path.exists(self.PROGRESS_FILE):
            try:
                with open(self.PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"lessons": {}}

    def _save_progress(self):
        """Save progress to data/curriculum_progress.json."""
        os.makedirs(os.path.dirname(self.PROGRESS_FILE), exist_ok=True)
        with open(self.PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.progress, f, indent=2)
