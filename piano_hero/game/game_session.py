"""Core gameplay logic — note matching, hold tracking, wrong note penalties."""

import queue
import time
from dataclasses import dataclass, field
from piano_hero.game.song import Song, Note
from piano_hero.game.score import ScoreTracker, judge_timing, compute_timing_score
from piano_hero.constants import (
    OK_WINDOW, FIRST_NOTE_GRACE, COMBO_MILESTONES, midi_to_note_name,
    HOLD_MIN_DURATION, HEALTH_START, HEALTH_HIT_GAIN, HEALTH_PERFECT_GAIN,
    HEALTH_MISS_DRAIN, HEALTH_WRONG_DRAIN, HEALTH_MIN, HEALTH_MAX,
    STAR_POWER_GAIN_PER_NOTE, STAR_POWER_DURATION, STAR_POWER_MULTIPLIER,
    STAR_POWER_HEALTH_BOOST,
)


@dataclass
class JudgmentEvent:
    judgment: str        # "perfect", "good", "ok", "miss"
    early_late: str      # "early", "late", "perfect", "" (for miss)
    note: Note
    detected_midi: int
    time: float
    points_earned: int = 0
    y_pos: float = 0.0


@dataclass
class WrongNoteEvent:
    played_midi: int
    played_name: str
    expected_midi: int
    expected_name: str
    time: float
    penalty: int = 0


@dataclass
class ComboEvent:
    streak: int
    text: str
    color: tuple
    time: float


@dataclass
class HoldScoreEvent:
    """Fired when a held note is released and the hold bonus is computed."""
    note: Note
    hold_bonus: int
    hold_ratio: float      # 0.0-1.0, how much of the expected duration was held
    time: float


@dataclass
class HoldState:
    """Tracks an active note hold."""
    note_index: int
    midi: int
    start_time: float      # When the player started holding
    expected_duration: float  # How long they should hold (seconds)
    base_points: int       # Points from the initial hit (for bonus calc)


class GameSession:
    """Manages an active gameplay session for one song."""

    # MIDI split point: middle C and above = right hand, below = left hand
    HAND_SPLIT = 60

    def __init__(self, song: Song, pitch_queue: queue.Queue,
                 calibration_offset: float = 0.0,
                 speed_multiplier: float = 1.0,
                 hand_mode: str = "both"):
        self.song = song
        self.pitch_queue = pitch_queue
        self.calibration_offset = calibration_offset
        self.speed_multiplier = max(0.1, speed_multiplier)
        self.hand_mode = hand_mode  # "both", "right", "left"

        # Deep copy notes, scaling times for speed
        self.notes: list[Note] = []
        time_scale = 1.0 / self.speed_multiplier
        for n in song.notes:
            note = Note(
                note_name=n.note_name,
                midi=n.midi,
                start_beat=n.start_beat,
                duration_beat=n.duration_beat,
                start_time=n.start_time * time_scale,
                end_time=n.end_time * time_scale,
            )
            # Tag notes for auto-play based on hand_mode
            note.auto_played = self._is_auto_play_note(note.midi)
            self.notes.append(note)

        # Count only active (non-auto-played) notes for scoring
        active_count = sum(1 for n in self.notes if not n.auto_played)
        self.score_tracker = ScoreTracker(active_count if active_count > 0 else len(self.notes))
        self.judgment_events: list[JudgmentEvent] = []
        self.wrong_note_events: list[WrongNoteEvent] = []
        self.combo_events: list[ComboEvent] = []
        self.hold_events: list[HoldScoreEvent] = []
        self.recording: list[dict] = []

        # Timing
        self.start_time = 0.0
        self.current_time = 0.0
        self.playing = False
        self.finished = False
        self.paused = False
        self._pause_start = 0.0

        # Current detected note (for keyboard display and passthrough)
        self.current_detected_note = None  # (name, midi) or None
        self.current_detected_time = 0.0
        self.note_just_detected = False  # True on frames where a new note was detected

        # Miss tracking
        self._next_miss_check = 0

        # Countdown
        self.countdown = 3.0
        self.countdown_active = True

        # Health meter
        self.health = HEALTH_START
        self.no_fail = True  # Toggleable
        self.failed = False

        # Star Power
        self.star_power_meter = 0.0   # 0.0-1.0
        self.star_power_active = False
        self._star_power_end_time = 0.0

        # Section loop
        self.loop_start_beat: float | None = None
        self.loop_end_beat: float | None = None

        # Scaled duration
        self.scaled_duration = song.duration * time_scale

        # Hold tracking
        self._active_holds: dict[int, HoldState] = {}

        # Chord detection: when a note is hit and siblings share the same
        # start_time, open a short window for bonus chord points.
        self._chord_window_end: float = -1.0      # current_time when window expires
        self._chord_pending: list[int] = []        # indices of unhit chord siblings
        self._chord_bonus_per_note: int = 50       # bonus points per chord note
        self._chord_window_duration: float = 0.30  # 300ms chord window

        # Wait mode: pause song progression until next note is played
        self.wait_mode = False
        self._waiting = False  # True when waiting for player input

    def _is_auto_play_note(self, midi: int) -> bool:
        """Return True if this MIDI note should be auto-played (not scored)."""
        if self.hand_mode == "right":
            return midi < self.HAND_SPLIT  # Left-hand notes auto-play
        elif self.hand_mode == "left":
            return midi >= self.HAND_SPLIT  # Right-hand notes auto-play
        return False  # "both" mode: nothing auto-plays

    def get_auto_play_notes(self, current_time: float) -> list[int]:
        """Return list of MIDI numbers that should auto-play right now.

        Returns MIDI values for auto-played notes whose start_time falls
        within a small window around current_time and haven't been triggered yet.
        """
        window = 0.05  # 50ms tolerance
        result = []
        for note in self.notes:
            if not note.auto_played:
                continue
            if note.hit:
                continue
            if abs(note.start_time - current_time) <= window:
                result.append(note.midi)
        return result

    def _beat_to_time(self, beat: float) -> float:
        return (beat * self.song.beat_duration) / self.speed_multiplier

    def _ok_window_for_note(self, note_index: int) -> float:
        if note_index == 0:
            return OK_WINDOW + FIRST_NOTE_GRACE
        return OK_WINDOW

    def start(self):
        self.start_time = time.perf_counter()
        self.playing = True
        self.countdown_active = True
        self.current_time = -self.countdown

    def update(self, dt: float):
        if not self.playing or self.paused:
            return

        now = time.perf_counter()

        # Wait mode: freeze song time if the next note hasn't been played
        if self.wait_mode and not self.countdown_active:
            next_note = self._find_next_unhit()
            if next_note is not None:
                candidate_time = (now - self.start_time) - self.countdown
                if candidate_time >= next_note.start_time - 0.05:
                    # We've reached the next note — freeze until it's hit
                    if not next_note.hit:
                        self._waiting = True
                        # Clamp time to just before the note
                        self.current_time = next_note.start_time - 0.02
                        self._process_pitch_queue()
                        # If the note was just hit in the queue drain, unfreeze
                        if next_note.hit:
                            self._waiting = False
                            # Adjust start_time so we resume from here
                            self.start_time = now - (self.current_time + self.countdown)
                        return
            self._waiting = False

        self.current_time = (now - self.start_time) - self.countdown
        self.note_just_detected = False

        if self.countdown_active and self.current_time >= 0:
            self.countdown_active = False

        self._process_pitch_queue()
        self._check_holds()
        self._check_chord_window()
        self._check_misses()
        self._update_star_power()

        # Section loop
        if (self.loop_start_beat is not None
                and self.loop_end_beat is not None):
            loop_end_time = self._beat_to_time(self.loop_end_beat)
            if self.current_time > loop_end_time:
                loop_start_time = self._beat_to_time(self.loop_start_beat)
                offset = self.current_time - loop_end_time
                self.start_time = now - (loop_start_time + offset + self.countdown)
                self.current_time = loop_start_time + offset
                for note in self.notes:
                    if (note.start_time >= loop_start_time
                            and note.start_time <= loop_end_time):
                        note.hit = False
                        note.judgment = ""
                self._next_miss_check = 0
                self._active_holds.clear()

        if self.current_time > self.scaled_duration + 1.0:
            # Finalize any remaining holds
            self._release_all_holds()
            self.finished = True
            self.playing = False

    def _get_expected_midis(self):
        """Return set of MIDI numbers for the NEXT FEW unhit notes only.

        Tight window: only the next 3 unhit notes are considered expected.
        This prevents harmonics of the current note from matching distant
        song notes and generating false wrong-note events.
        """
        expected = set()
        count = 0
        for note in self.notes:
            if note.hit or note.auto_played:
                continue
            expected.add(note.midi)
            # Also add harmonics (detector sees these for low notes)
            expected.add(note.midi + 12)  # 2nd harmonic (octave)
            expected.add(note.midi + 19)  # 3rd harmonic (octave + fifth)
            count += 1
            if count >= 3:
                break
        return expected

    def _process_pitch_queue(self):
        # ── Song-aware pitch detection ──
        # Two paths for accepting notes:
        # 1. FAST PATH: if the detected MIDI matches an upcoming expected note,
        #    accept with just 2 confirmations (~50ms). No majority vote needed.
        # 2. SLOW PATH: for unexpected notes, use 3-vote majority to filter noise.
        from piano_hero.constants import midi_to_note_name, AUDIO_PIPELINE_LATENCY

        if not hasattr(self, '_vote_buffer'):
            self._vote_buffer = []
            self._vote_window = 0.20
            self._last_emit_midi = -1
            self._last_emit_time = -999.0
            self._silence_count = 0
            self._fast_confirm = {}  # midi -> [timestamps]

        expected_midis = self._get_expected_midis()

        while True:
            try:
                result = self.pitch_queue.get_nowait()
                if len(result) == 6:
                    name, midi, freq, confidence, is_onset, timestamp = result
                else:
                    name, midi, freq, confidence, timestamp = result
            except queue.Empty:
                break

            if name is None or midi == 0:
                self._silence_count += 1
                if self._silence_count > 5:
                    self._vote_buffer.clear()
                    self._fast_confirm.clear()
                    self.current_detected_note = None
                continue

            self._silence_count = 0

            if midi < 43:
                continue

            # Require minimum confidence to filter noise during silence
            if confidence < 0.3:
                continue

            now = timestamp if timestamp else self.current_time
            self.current_detected_note = (name, midi)

            # FAST PATH: if this MIDI matches an expected song note,
            # accept with just 2 confirmations
            if midi in expected_midis:
                if midi not in self._fast_confirm:
                    self._fast_confirm[midi] = []
                self._fast_confirm[midi].append(now)
                # Prune old confirmations
                self._fast_confirm[midi] = [
                    t for t in self._fast_confirm[midi] if now - t < 0.15]

                if len(self._fast_confirm[midi]) >= 2:
                    # Debounce same note
                    if midi == self._last_emit_midi and now - self._last_emit_time < 0.30:
                        continue
                    # Different note needs only 80ms gap
                    if midi != self._last_emit_midi and now - self._last_emit_time < 0.08:
                        continue

                    # Mark if this is a different note from last match
                    # (enables repeat-note detection in _try_match)
                    if hasattr(self, '_last_match_midi'):
                        if abs(midi - self._last_match_midi) > 1:
                            self._had_different_note_since_match = True

                    self._last_emit_midi = midi
                    self._last_emit_time = now
                    self._fast_confirm.pop(midi, None)
                    self._vote_buffer.clear()

                    note_name = midi_to_note_name(midi)
                    self.current_detected_note = (note_name, midi)
                    self.current_detected_time = self.current_time
                    self.note_just_detected = True

                    self.recording.append({
                        "name": note_name, "midi": midi, "freq": 0.0,
                        "confidence": confidence, "time": self.current_time,
                    })

                    _PL = AUDIO_PIPELINE_LATENCY
                    detect_time = ((now - self.start_time)
                                   - self.countdown + self.calibration_offset - _PL)
                    self._try_match(midi, detect_time, note_name)
                continue

            # SLOW PATH: unexpected note — use vote buffer
            self._vote_buffer.append((midi, confidence, now))

        # Process slow-path vote buffer
        if not self._vote_buffer:
            return

        now = self._vote_buffer[-1][2]
        cutoff = now - self._vote_window
        self._vote_buffer = [(m, c, t) for m, c, t in self._vote_buffer if t >= cutoff]

        if len(self._vote_buffer) < 3:
            return

        from collections import Counter
        vote_counts = Counter()
        vote_conf = {}
        for midi, conf, t in self._vote_buffer:
            vote_counts[midi] += 1
            if midi not in vote_conf or conf > vote_conf[midi]:
                vote_conf[midi] = conf

        winner_midi, winner_count = vote_counts.most_common(1)[0]
        total_votes = sum(vote_counts.values())

        if winner_count < total_votes * 0.4:
            return

        if winner_midi == self._last_emit_midi and now - self._last_emit_time < 0.30:
            return
        if winner_midi != self._last_emit_midi and now - self._last_emit_time < 0.05:
            return

        if hasattr(self, '_last_match_midi'):
            if abs(winner_midi - self._last_match_midi) > 1:
                self._had_different_note_since_match = True

        self._last_emit_midi = winner_midi
        self._last_emit_time = now
        self._vote_buffer.clear()

        name = midi_to_note_name(winner_midi)
        self.current_detected_note = (name, winner_midi)
        self.current_detected_time = self.current_time
        self.note_just_detected = True

        self.recording.append({
            "name": name, "midi": winner_midi, "freq": 0.0,
            "confidence": vote_conf[winner_midi], "time": self.current_time,
        })

        _PL = AUDIO_PIPELINE_LATENCY
        detect_time = ((now - self.start_time)
                       - self.countdown + self.calibration_offset - _PL)
        self._try_match(winner_midi, detect_time, name)

    def _try_match(self, detected_midi: int, detect_time: float,
                   detected_name: str = ""):
        best_note = None
        best_diff = float('inf')
        best_index = -1

        # Also try harmonic corrections: audio detection often picks up
        # harmonics instead of the fundamental for low notes:
        #   2nd harmonic = octave up (+12 semitones)
        #   3rd harmonic = octave + fifth up (+19 semitones)
        # If detected_midi minus these offsets matches a song note, accept it.
        midi_candidates = [detected_midi, detected_midi - 12, detected_midi - 19]

        # Prevent re-matching the same MIDI too quickly (avoids the E-C-E
        # problem where E's sustain/ring matches the second E prematurely).
        # Require either a silence gap, a different note, or 400ms since
        # the same MIDI was last matched.
        if not hasattr(self, '_last_match_midi'):
            self._last_match_midi = -1
            self._last_match_time = -999.0
            self._had_different_note_since_match = True

        same_midi_repeat = any(
            abs(self._last_match_midi - c) <= 1 for c in midi_candidates
        )
        if same_midi_repeat and not self._had_different_note_since_match:
            if detect_time - self._last_match_time < 0.4:
                return  # Too soon for same note without a gap

        for i, note in enumerate(self.notes):
            if note.hit:
                continue
            if note.auto_played:
                continue
            diff = detect_time - note.start_time
            ok_win = self._ok_window_for_note(i)

            # diff < 0 means note is in the FUTURE (player is early)
            # diff > 0 means note is in the PAST (player is late)
            # Only allow playing slightly early (up to ok_win) but not
            # absurdly early — clamp early detection to 300ms max to
            # prevent the E-C-E problem where E's ring matches a
            # future E note that shouldn't be playable yet.
            max_early = min(ok_win, 0.30)
            if diff < -max_early:
                continue  # Note is too far in the future
            if diff > ok_win:
                continue  # Note is too far in the past

            # Check if any MIDI candidate matches within ±1 semitone tolerance
            matched = False
            for candidate in midi_candidates:
                if abs(note.midi - candidate) <= 1:
                    matched = True
                    break
            if not matched:
                continue
            if abs(diff) < abs(best_diff):
                best_diff = diff
                best_note = note
                best_index = i

        if best_note is not None:
            judgment, early_late = judge_timing(best_diff)
            best_note.hit = True
            best_note.judgment = judgment
            best_note.early_late = early_late
            # Use the expected MIDI for display (octave correction)
            # so the keyboard lights up the correct key
            self.current_detected_note = (
                best_note.note_name, best_note.midi)
            # Track for repeat-note prevention
            self._last_match_midi = best_note.midi
            self._last_match_time = detect_time
            self._had_different_note_since_match = False
            # Log timing for diagnostics
            if not hasattr(self, '_timing_diffs'):
                self._timing_diffs = []
            self._timing_diffs.append(best_diff)
            points_earned = self.score_tracker.record(
                judgment, early_late=early_late, timing_diff=best_diff,
                detected_midi=detected_midi, expected_midi=best_note.midi)
            self.judgment_events.append(JudgmentEvent(
                judgment=judgment, early_late=early_late, note=best_note,
                detected_midi=detected_midi, time=self.current_time,
                points_earned=points_earned))
            self._check_combo_milestone()

            # Health gain
            gain = HEALTH_PERFECT_GAIN if judgment == "perfect" else HEALTH_HIT_GAIN
            if self.star_power_active:
                gain += STAR_POWER_HEALTH_BOOST
            self._adjust_health(gain)

            # Star power meter: gain from star power notes
            if getattr(best_note, 'star_power', False):
                self.star_power_meter = min(1.0,
                    self.star_power_meter + STAR_POWER_GAIN_PER_NOTE)

            # Start hold tracking for this note
            expected_hold = best_note.end_time - best_note.start_time
            if expected_hold >= HOLD_MIN_DURATION:
                self._active_holds[best_index] = HoldState(
                    note_index=best_index, midi=best_note.midi,
                    start_time=self.current_time,
                    expected_duration=expected_hold,
                    base_points=compute_timing_score(best_diff))

            # Chord detection: if there are other unhit notes at the same
            # start_time (within 0.05 beats), open a chord window
            chord_tolerance = 0.05 * self.song.beat_duration
            siblings = []
            for ci, cn in enumerate(self.notes):
                if cn.hit or cn.auto_played:
                    continue
                if ci == best_index:
                    continue
                if abs(cn.start_time - best_note.start_time) <= chord_tolerance:
                    siblings.append(ci)
            if siblings:
                self._chord_pending = siblings
                self._chord_window_end = (self.current_time
                                          + self._chord_window_duration)
            elif self._chord_pending:
                # We're inside a chord window — check if this hit is one of
                # the pending chord notes
                if best_index in self._chord_pending:
                    self._chord_pending.remove(best_index)
                    # Chord bonus points
                    self.score_tracker.score += self._chord_bonus_per_note
        else:
            # No match found. Before counting as wrong note, apply filters
            # to avoid penalizing harmonic/octave artifacts from detection.

            # 1. If the detected note is a harmonic (octave) of the last
            #    CORRECTLY matched note, ignore it — it's just the detector
            #    picking up overtones of what the player already played.
            if self._last_emit_midi > 0:
                diff_from_last = abs(detected_midi - self._last_emit_midi)
                if diff_from_last in (0, 12, 19):  # same, octave, or octave+fifth
                    return

            # 2. If within ±2 semitones of an upcoming note, it's likely
            #    the right note with detection error — don't penalize.
            nearest_note = self._find_nearest_upcoming(detect_time)
            if nearest_note is not None:
                semitone_diff = abs(nearest_note.midi - detected_midi)
                # Also check harmonic-offset matches
                octave_diff = abs(nearest_note.midi - (detected_midi - 12))
                third_diff = abs(nearest_note.midi - (detected_midi - 19))
                if semitone_diff <= 2 or octave_diff <= 2 or third_diff <= 2:
                    return

                expected_midi = nearest_note.midi
                expected_name = nearest_note.note_name
            else:
                # No upcoming note — playing during rest. Don't penalize.
                return

            # 3. Rate-limit wrong notes: max 1 per second (scaled by speed).
            #    At slow speeds, gaps are longer so noise has more time to
            #    accumulate false detections.
            if not hasattr(self, '_last_wrong_time'):
                self._last_wrong_time = -999.0
            wrong_rate_limit = 1.0 / max(self.speed_multiplier, 0.25)
            if self.current_time - self._last_wrong_time < wrong_rate_limit:
                return
            self._last_wrong_time = self.current_time

            penalty = self.score_tracker.record_wrong_note_penalty(
                expected_midi, detected_midi)
            self._adjust_health(-HEALTH_WRONG_DRAIN)

            self.wrong_note_events.append(WrongNoteEvent(
                played_midi=detected_midi,
                played_name=detected_name or midi_to_note_name(detected_midi),
                expected_midi=expected_midi,
                expected_name=expected_name,
                time=self.current_time,
                penalty=penalty))

    def _check_holds(self):
        """Check active holds — release if player stopped playing the note."""
        if not self._active_holds:
            return

        current_midi = self.current_detected_note[1] if self.current_detected_note else None
        finished_holds = []

        for note_idx, hold in self._active_holds.items():
            note = self.notes[note_idx]
            elapsed = self.current_time - hold.start_time

            # Release conditions: player is playing a different note,
            # or the expected hold duration has passed
            released = (current_midi != hold.midi
                        or elapsed >= hold.expected_duration)

            if released:
                actual_hold = min(elapsed, hold.expected_duration)
                hold_bonus = self.score_tracker.record_hold_bonus(
                    hold.base_points, actual_hold, hold.expected_duration)
                hold_ratio = min(1.0, actual_hold / hold.expected_duration)
                self.hold_events.append(HoldScoreEvent(
                    note=note, hold_bonus=hold_bonus,
                    hold_ratio=hold_ratio, time=self.current_time))
                finished_holds.append(note_idx)

        for idx in finished_holds:
            del self._active_holds[idx]

    def _check_chord_window(self):
        """When the chord window expires, mark any remaining pending chord
        notes as missed."""
        if not self._chord_pending:
            return
        if self.current_time < self._chord_window_end:
            return
        # Window expired — missed chord notes
        for idx in self._chord_pending:
            note = self.notes[idx]
            if not note.hit:
                note.hit = True
                note.judgment = "miss"
                self.score_tracker.record(
                    "miss", timing_diff=0.0,
                    expected_midi=note.midi)
                self.judgment_events.append(JudgmentEvent(
                    judgment="miss", early_late="", note=note,
                    detected_midi=0, time=self.current_time))
                self._adjust_health(-HEALTH_MISS_DRAIN)
        self._chord_pending.clear()
        self._chord_window_end = -1.0

    def _release_all_holds(self):
        """Release all active holds (called at song end)."""
        for note_idx, hold in list(self._active_holds.items()):
            note = self.notes[note_idx]
            elapsed = self.current_time - hold.start_time
            actual_hold = min(elapsed, hold.expected_duration)
            hold_bonus = self.score_tracker.record_hold_bonus(
                hold.base_points, actual_hold, hold.expected_duration)
            hold_ratio = min(1.0, actual_hold / hold.expected_duration)
            self.hold_events.append(HoldScoreEvent(
                note=note, hold_bonus=hold_bonus,
                hold_ratio=hold_ratio, time=self.current_time))
        self._active_holds.clear()

    def get_hold_progress(self, note_index: int) -> float:
        """Return 0.0-1.0 hold progress for a note, or -1 if not being held."""
        hold = self._active_holds.get(note_index)
        if hold is None:
            return -1.0
        elapsed = self.current_time - hold.start_time
        return min(1.0, elapsed / hold.expected_duration)

    def _find_next_unhit(self) -> Note | None:
        """Return the next unhit, non-auto-played note in sequence, or None."""
        for note in self.notes:
            if not note.hit and not note.auto_played:
                return note
        return None

    def _find_nearest_upcoming(self, detect_time: float) -> Note | None:
        best = None
        best_dist = float('inf')
        for note in self.notes:
            if note.hit:
                continue
            dist = abs(note.start_time - detect_time)
            if dist < best_dist:
                best_dist = dist
                best = note
        return best

    def _check_combo_milestone(self):
        streak = self.score_tracker.streak
        if streak in COMBO_MILESTONES:
            text, color = COMBO_MILESTONES[streak]
            self.combo_events.append(ComboEvent(
                streak=streak, text=text, color=color, time=self.current_time))

    def _check_misses(self):
        for i in range(self._next_miss_check, len(self.notes)):
            note = self.notes[i]
            if note.hit:
                self._next_miss_check = i + 1
                continue

            # Auto-played notes: silently mark as hit at the correct time
            if note.auto_played:
                if self.current_time >= note.start_time:
                    note.hit = True
                    note.judgment = "auto"
                    self._next_miss_check = i + 1
                    continue
                else:
                    break

            ok_win = self._ok_window_for_note(i)
            if self.current_time > note.start_time + ok_win:
                note.hit = True
                note.judgment = "miss"
                self.score_tracker.record(
                    "miss", timing_diff=0.0,
                    expected_midi=note.midi)
                self.judgment_events.append(JudgmentEvent(
                    judgment="miss", early_late="", note=note,
                    detected_midi=0, time=self.current_time))
                self._adjust_health(-HEALTH_MISS_DRAIN)
                self._next_miss_check = i + 1
            else:
                break

    # ── Health & Star Power ────────────────────────────────────────────────

    def _adjust_health(self, amount):
        self.health = max(HEALTH_MIN, min(HEALTH_MAX, self.health + amount))
        if self.health <= 0 and not self.no_fail:
            self.failed = True
            self.finished = True
            self.playing = False

    def _update_star_power(self):
        if self.star_power_active:
            if self.current_time >= self._star_power_end_time:
                self.star_power_active = False

    def activate_star_power(self):
        """Activate star power if meter is at least 50% full."""
        if self.star_power_meter >= 0.5 and not self.star_power_active:
            self.star_power_active = True
            self._star_power_end_time = self.current_time + STAR_POWER_DURATION
            self.star_power_meter = 0.0

    def get_effective_multiplier(self) -> float:
        """Return current multiplier including star power doubling."""
        mult = self.score_tracker.multiplier
        if self.star_power_active:
            mult *= STAR_POWER_MULTIPLIER
        return mult

    def toggle_pause(self):
        if self.paused:
            pause_duration = time.perf_counter() - self._pause_start
            self.start_time += pause_duration
            self.paused = False
        else:
            self._pause_start = time.perf_counter()
            self.paused = True

    def set_loop(self, start_beat, end_beat):
        self.loop_start_beat = start_beat
        self.loop_end_beat = end_beat

    def get_recent_judgments(self, max_age=1.0):
        cutoff = self.current_time - max_age
        return [e for e in self.judgment_events if e.time > cutoff]

    def get_recent_combos(self, max_age=2.0):
        cutoff = self.current_time - max_age
        return [e for e in self.combo_events if e.time > cutoff]

    def get_recent_wrong_notes(self, max_age=1.5):
        cutoff = self.current_time - max_age
        return [e for e in self.wrong_note_events if e.time > cutoff]

    def get_recent_hold_events(self, max_age=1.5):
        cutoff = self.current_time - max_age
        return [e for e in self.hold_events if e.time > cutoff]
