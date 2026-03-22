"""Convert a MIDI file to Piano Hero JSON song format.

Usage:
    python tools/midi_to_json.py input.mid [--title "Song Name"] [--composer "Composer"]
    python tools/midi_to_json.py input.mid -o songs/output.json

Extracts the melody (highest note track or specified track) and writes
a Piano Hero compatible JSON song file.
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import mido
except ImportError:
    print("Error: mido library required. Install with: pip install mido")
    sys.exit(1)

from piano_hero.constants import midi_to_note_name, MIN_MIDI, MAX_MIDI


def midi_to_song(midi_path, track_index=None, title=None, composer=None):
    """Convert a MIDI file to Piano Hero song dict."""
    mid = mido.MidiFile(midi_path)

    # Get tempo from the file (default 120 BPM)
    tempo_us = 500000  # microseconds per beat (default = 120 BPM)
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo_us = msg.tempo
                break

    bpm = round(60_000_000 / tempo_us)
    ticks_per_beat = mid.ticks_per_beat

    # Determine time signature
    time_sig = [4, 4]
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'time_signature':
                time_sig = [msg.numerator, msg.denominator]
                break

    # Extract notes from all tracks or specified track
    all_notes = []

    tracks_to_scan = [mid.tracks[track_index]] if track_index is not None else mid.tracks

    for track in tracks_to_scan:
        current_tick = 0
        active_notes = {}  # midi -> start_tick

        for msg in track:
            current_tick += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes[msg.note] = current_tick
            elif msg.type in ('note_off', 'note_on') and msg.note in active_notes:
                start_tick = active_notes.pop(msg.note)
                dur_ticks = current_tick - start_tick
                if dur_ticks > 0 and MIN_MIDI <= msg.note <= MAX_MIDI:
                    start_beat = start_tick / ticks_per_beat
                    dur_beat = dur_ticks / ticks_per_beat
                    all_notes.append({
                        'note': midi_to_note_name(msg.note),
                        'start': round(start_beat, 4),
                        'duration': round(dur_beat, 4),
                        'midi': msg.note,
                    })

    # Sort by start time, then by pitch (highest first for melody extraction)
    all_notes.sort(key=lambda n: (n['start'], -n['midi']))

    # If multiple simultaneous notes, keep the highest (melody)
    filtered = []
    last_start = -1
    for note in all_notes:
        if abs(note['start'] - last_start) < 0.01:
            continue  # Skip lower simultaneous notes
        filtered.append(note)
        last_start = note['start']

    # Remove the midi key (not part of the song format)
    for note in filtered:
        del note['midi']

    # Build song dict
    basename = os.path.splitext(os.path.basename(midi_path))[0]
    song = {
        'title': title or basename.replace('_', ' ').title(),
        'composer': composer or 'Unknown',
        'tempo': bpm,
        'time_signature': time_sig,
        'difficulty': 'grade2',
        'notes': filtered,
    }

    return song


def main():
    parser = argparse.ArgumentParser(description='Convert MIDI to Piano Hero JSON')
    parser.add_argument('input', help='Input MIDI file path')
    parser.add_argument('-o', '--output', help='Output JSON file path')
    parser.add_argument('--title', help='Song title')
    parser.add_argument('--composer', help='Composer name')
    parser.add_argument('--track', type=int, help='Track index to extract (default: all)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        sys.exit(1)

    song = midi_to_song(args.input, track_index=args.track,
                        title=args.title, composer=args.composer)

    output_path = args.output
    if not output_path:
        basename = os.path.splitext(os.path.basename(args.input))[0]
        output_path = os.path.join('songs', f'{basename}.json')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(song, f, indent=2)

    print(f"Converted: {args.input}")
    print(f"  Title: {song['title']}")
    print(f"  Tempo: {song['tempo']} BPM")
    print(f"  Notes: {len(song['notes'])}")
    print(f"  Output: {output_path}")


if __name__ == '__main__':
    main()
