"""MIDI USB keyboard input — zero-latency note detection via pygame.midi.

Connects to a USB MIDI keyboard and pushes note events directly into the
pitch queue, bypassing the audio detection pipeline entirely. This gives
sub-millisecond accuracy compared to ~50ms for audio pitch detection.
"""

import time
import queue
import threading
import pygame.midi
from piano_hero.constants import midi_to_note_name, midi_to_freq
from piano_hero.input.keyboard_input import YAMAHA_CONTROLS


class MidiInput:
    """Reads from a USB MIDI keyboard and pushes notes to the pitch queue."""

    def __init__(self, pitch_queue: queue.Queue, device_id=None):
        self.pitch_queue = pitch_queue
        self.device_id = device_id
        self._running = False
        self._thread = None
        self._midi_in = None
        self.enabled = True
        self._last_action = ""  # Latest Yamaha control action detected

    @staticmethod
    def list_devices():
        """Return list of available MIDI input devices.

        Returns list of (device_id, name, is_input) tuples.
        """
        devices = []
        try:
            if not pygame.midi.get_init():
                pygame.midi.init()
            for i in range(pygame.midi.get_count()):
                info = pygame.midi.get_device_info(i)
                # info: (interface, name, is_input, is_output, opened)
                if info[2]:  # is_input
                    name = info[1].decode('utf-8', errors='replace')
                    devices.append((i, name, True))
        except Exception:
            pass
        return devices

    def start(self):
        """Open the MIDI device and start reading events."""
        if self._running:
            return

        if not pygame.midi.get_init():
            pygame.midi.init()

        # Auto-detect device if not specified
        if self.device_id is None:
            devices = self.list_devices()
            if devices:
                self.device_id = devices[0][0]
            else:
                return  # No MIDI devices available

        try:
            self._midi_in = pygame.midi.Input(self.device_id)
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"MIDI input error: {e}")
            self._midi_in = None

    def stop(self):
        """Stop reading and close the MIDI device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._midi_in:
            try:
                self._midi_in.close()
            except Exception:
                pass
            self._midi_in = None

    def is_running(self):
        return self._running and self._midi_in is not None

    def get_last_action(self) -> str:
        """Get and clear the latest Yamaha control action."""
        action = self._last_action
        self._last_action = ""
        return action

    def _read_loop(self):
        """Background thread that polls for MIDI events."""
        while self._running and self._midi_in:
            try:
                if self._midi_in.poll():
                    events = self._midi_in.read(32)
                    timestamp = time.perf_counter()
                    for event in events:
                        data, _ = event
                        status = data[0] & 0xF0
                        midi_note = data[1]
                        velocity = data[2]

                        if status == 0x90 and velocity > 0:
                            # Note On
                            # Check for Yamaha control key
                            action = YAMAHA_CONTROLS.get(midi_note, '')
                            if action:
                                self._last_action = action
                                continue

                            name = midi_to_note_name(midi_note)
                            freq = midi_to_freq(midi_note)
                            confidence = min(1.0, velocity / 100.0)

                            # Push as 6-tuple matching audio engine format
                            result = (name, midi_note, freq, confidence,
                                      True, timestamp)
                            try:
                                self.pitch_queue.put_nowait(result)
                            except queue.Full:
                                try:
                                    self.pitch_queue.get_nowait()
                                    self.pitch_queue.put_nowait(result)
                                except (queue.Empty, queue.Full):
                                    pass

                        elif status == 0x80 or (status == 0x90 and velocity == 0):
                            # Note Off — push silence
                            result = (None, 0, 0.0, 0.0, False, timestamp)
                            try:
                                self.pitch_queue.put_nowait(result)
                            except queue.Full:
                                pass

                else:
                    time.sleep(0.001)  # 1ms poll interval

            except Exception:
                time.sleep(0.01)
