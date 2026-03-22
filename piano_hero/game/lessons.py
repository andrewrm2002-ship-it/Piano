"""Micro-lesson tips shown before songs start."""

from piano_hero.constants import midi_to_note_name
from collections import Counter


def get_lesson_tip(song) -> str:
    """Generate a brief lesson tip for the song about to be played."""
    if not song.notes:
        return ""

    unique = song.unique_notes()
    note_names = [midi_to_note_name(m) for m in unique]
    lowest = note_names[0] if note_names else "C4"
    highest = note_names[-1] if note_names else "C4"

    tips = []

    # Range tip
    if len(unique) <= 5:
        names_str = ", ".join(note_names)
        tips.append(f"Uses just {len(unique)} notes: {names_str}")
    else:
        tips.append(f"Notes: {lowest} to {highest} ({len(unique)} different)")

    # Tempo tip
    if song.tempo <= 80:
        tips.append("Slow tempo - take your time")
    elif song.tempo >= 120:
        tips.append("Fast tempo - stay focused!")

    # Chord tip
    starts = Counter(n.start_beat for n in song.notes)
    chord_count = sum(1 for c in starts.values() if c > 1)
    if chord_count > 5:
        tips.append(f"{chord_count} chords - press multiple keys together")

    # Hold tip
    long_notes = sum(1 for n in song.notes if n.duration_beat >= 2.0)
    if long_notes > 3:
        tips.append(f"{long_notes} held notes - keep keys pressed!")

    # Sharp/flat tip
    has_sharps = any('#' in n.note_name for n in song.notes)
    if has_sharps:
        sharp_notes = sorted(set(n.note_name for n in song.notes if '#' in n.note_name))
        tips.append(f"Uses sharps: {', '.join(sharp_notes)}")
    else:
        tips.append("White keys only")

    return " | ".join(tips[:2])
