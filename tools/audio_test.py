"""Standalone audio input + pitch detection tester.

Run this to verify your keyboard is detected and notes are identified correctly.
Usage: python tools/audio_test.py
"""

import sys
import os
import queue
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from piano_hero.audio.audio_engine import AudioEngine


def main():
    print("=" * 50)
    print("  Piano Hero — Audio Test Tool")
    print("=" * 50)
    print()

    # List devices
    devices = AudioEngine.list_input_devices()
    if not devices:
        print("ERROR: No audio input devices found!")
        print("Make sure your microphone/line-in is connected.")
        return

    print("Available input devices:")
    for i, (idx, name, ch, sr) in enumerate(devices):
        print(f"  [{idx}] {name} (channels={ch}, rate={sr})")
    print()

    # Let user pick device
    choice = input("Enter device number (or press Enter for default): ").strip()
    device_idx = None
    if choice:
        try:
            device_idx = int(choice)
        except ValueError:
            print("Invalid choice, using default.")

    # Start audio
    pitch_queue = queue.Queue(maxsize=16)
    engine = AudioEngine(pitch_queue, device_index=device_idx)

    print()
    print("Starting audio capture...")
    try:
        engine.start()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return

    print("Listening for notes. Play your keyboard!")
    print("Press Ctrl+C to stop.")
    print()
    print(f"{'Time':>8}  {'Note':>5}  {'MIDI':>4}  {'Freq':>8}  {'Conf':>5}  {'Level':>6}")
    print("-" * 50)

    last_note = None
    start = time.time()

    try:
        while True:
            try:
                name, midi, freq, conf, ts = pitch_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if name is None:
                if last_note is not None:
                    last_note = None
                continue

            elapsed = time.time() - start
            level = engine.get_input_level()

            # Only print if note changed (reduce spam)
            if name != last_note:
                print(f"{elapsed:8.2f}  {name:>5}  {midi:>4}  {freq:8.2f}  {conf:5.2f}  {level:6.4f}")
                last_note = name

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        engine.stop()
        print("Done.")


if __name__ == "__main__":
    main()
