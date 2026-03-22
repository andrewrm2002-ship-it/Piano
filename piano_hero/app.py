"""Application orchestrator — state machine and main game loop."""

import os
import sys
import queue
import pygame

from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, TARGET_FPS, TITLE, BG_COLOR,
    HIGHWAY_WIDTH_RATIO, KEYBOARD_HEIGHT, COLOR_WHITE, COLOR_ACCENT,
    COLOR_DARK_GRAY, COLOR_GRAY, COLOR_PERFECT, COLOR_GOOD, COLOR_MISS,
    COMBO_MILESTONES,
)
from piano_hero.audio.audio_engine import AudioEngine
from piano_hero.audio.sound_effects import SoundEffects
from piano_hero.game.song import load_all_songs, compute_song_difficulty_multiplier
from piano_hero.game.game_session import GameSession
from piano_hero.game.score import save_high_score
from piano_hero.game.statistics import load_stats, record_session, save_stats
from piano_hero.config.settings import load_settings, save_settings
from piano_hero.ui.renderer import init_display, get_gradient_bg, get_font, get_title_font, draw_text
from piano_hero.ui.note_highway import NoteHighway
from piano_hero.ui.keyboard_display import KeyboardDisplay
from piano_hero.ui.hud import HUD
from piano_hero.ui.effects import EffectsManager
from piano_hero.input.keyboard_input import KeyboardNoteInput
from piano_hero.input.midi_input import MidiInput

# States
STATE_MENU = "menu"
STATE_SONG_SELECT = "song_select"
STATE_SETTINGS = "settings"
STATE_PLAYING = "playing"
STATE_RESULTS = "results"
STATE_STATS = "stats"
STATE_CALIBRATE = "calibrate"
STATE_CONFIRM_QUIT = "confirm_quit"


class App:
    """Main application class."""

    def __init__(self):
        self.screen = None
        self.clock = None
        self.running = False
        self.state = STATE_MENU

        self.settings = load_settings()
        self.stats = load_stats()

        # Audio
        self.pitch_queue = queue.Queue(maxsize=16)
        self.audio_engine = None
        self.sfx = SoundEffects()
        self.keyboard_input = KeyboardNoteInput(self.pitch_queue)
        self.midi_input = MidiInput(self.pitch_queue)

        # Songs
        self.songs_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "songs")
        self.songs = []

        # Game components (initialized in run() after pygame.init)
        self.game_session = None
        self.highway = None
        self.keyboard_display = None
        self.hud = None
        self.effects = None

        # Screens (lazy init)
        self.main_menu = None
        self.song_select = None
        self.results_screen = None
        self.settings_menu = None
        self.stats_screen = None
        self.calibration_screen = None

        self._bg_surface = None
        self._last_judgment_count = 0
        self._last_combo_count = 0
        self._last_wrong_count = 0
        self._last_hold_count = 0
        self._last_detected_midi = None
        self._practice_mode = False
        self._practice_speed = 1.0

    def run(self):
        """Main entry point."""
        self.screen = init_display(self.settings.get('fullscreen', False))
        self.clock = pygame.time.Clock()
        self.running = True
        self._bg_surface = get_gradient_bg(SCREEN_WIDTH, SCREEN_HEIGHT)

        # Init UI components
        self.highway = NoteHighway()
        self.keyboard_display = KeyboardDisplay()
        self.hud = HUD()
        self.effects = EffectsManager()

        # Init sound effects
        self.sfx.init()
        self.sfx.enabled = self.settings.get('sfx_enabled', True)

        # Load songs
        self.songs = load_all_songs(self.songs_dir)

        # Init menus (lazy import to avoid circular)
        from piano_hero.ui.menu import (MainMenu, SongSelect, ResultsScreen,
                                         SettingsMenu, StatsScreen, CalibrationScreen)
        self.main_menu = MainMenu()
        self.song_select = SongSelect(self.songs)

        # Init audio
        self._init_audio()

        # Start MIDI input if a device is available
        midi_device = self.settings.get('midi_device')
        self.midi_input = MidiInput(self.pitch_queue, device_id=midi_device)
        try:
            self.midi_input.start()
            if self.midi_input.is_running():
                print(f"MIDI input connected")
        except Exception:
            pass

        # Main loop
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()
            pygame.display.flip()

        self._cleanup()

    def _init_audio(self):
        if self.audio_engine is not None:
            self.audio_engine.stop()
        device = self.settings.get('audio_device')
        self.audio_engine = AudioEngine(self.pitch_queue, device_index=device)
        try:
            self.audio_engine.start()
        except RuntimeError as e:
            print(f"Audio error: {e}")
            print("Continuing without audio input.")

    def _cleanup(self):
        if self.audio_engine:
            self.audio_engine.stop()
        if self.midi_input:
            self.midi_input.stop()
        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            # Global: F11 toggle fullscreen
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self.settings['fullscreen'] = not self.settings.get('fullscreen', False)
                flags = pygame.FULLSCREEN if self.settings['fullscreen'] else 0
                self.screen = pygame.display.set_mode(
                    (SCREEN_WIDTH, SCREEN_HEIGHT), flags)
                continue

            if self.state == STATE_MENU:
                action = self.main_menu.handle_event(event)
                if action == "play":
                    self._practice_mode = False
                    from piano_hero.ui.menu import SongSelect
                    self.song_select = SongSelect(self.songs, practice_mode=False)
                    self.state = STATE_SONG_SELECT
                elif action == "practice":
                    self._practice_mode = True
                    self._practice_speed = self.settings.get('practice_speed', 1.0)
                    from piano_hero.ui.menu import SongSelect
                    self.song_select = SongSelect(self.songs, practice_mode=True)
                    self.state = STATE_SONG_SELECT
                elif action == "stats":
                    from piano_hero.ui.menu import StatsScreen
                    self.stats_screen = StatsScreen(self.stats)
                    self.state = STATE_STATS
                elif action == "settings":
                    from piano_hero.ui.menu import SettingsMenu
                    devices = AudioEngine.list_input_devices()
                    self.settings_menu = SettingsMenu(self.settings, devices)
                    self.state = STATE_SETTINGS
                elif action == "quit":
                    self.running = False

            elif self.state == STATE_SONG_SELECT:
                action = self.song_select.handle_event(event)
                if action == "play":
                    song = self.song_select.get_selected_song()
                    if song:
                        speed = self.song_select.get_speed() if self._practice_mode else 1.0
                        diff = getattr(self.song_select, 'get_difficulty', lambda: 'Hard')()
                        self._start_game(song, speed, diff)
                elif action == "back":
                    self.state = STATE_MENU

            elif self.state == STATE_SETTINGS:
                action = self.settings_menu.handle_event(event)
                if action == "back":
                    save_settings(self.settings_menu.settings)
                    self.settings = self.settings_menu.settings
                    self.sfx.enabled = self.settings.get('sfx_enabled', True)
                    self._init_audio()
                    self.state = STATE_MENU
                elif action == "calibrate":
                    from piano_hero.ui.menu import CalibrationScreen
                    self.calibration_screen = CalibrationScreen()
                    self.state = STATE_CALIBRATE

            elif self.state == STATE_CALIBRATE:
                if self.calibration_screen:
                    action = self.calibration_screen.handle_event(event)
                    if action == "accept":
                        offset = self.calibration_screen.computed_offset
                        self.settings['calibration_offset'] = offset
                        self.settings_menu.settings['calibration_offset'] = offset
                        save_settings(self.settings)
                        self.state = STATE_SETTINGS
                    elif action == "cancel":
                        self.state = STATE_SETTINGS

            elif self.state == STATE_STATS:
                if self.stats_screen:
                    action = self.stats_screen.handle_event(event)
                    if action == "back":
                        self.state = STATE_MENU

            elif self.state == STATE_PLAYING:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.game_session and self.game_session.paused:
                            # ESC while paused = go to song select
                            self.game_session = None
                            while not self.pitch_queue.empty():
                                try: self.pitch_queue.get_nowait()
                                except queue.Empty: break
                            self.state = STATE_SONG_SELECT
                        else:
                            self.state = STATE_CONFIRM_QUIT
                    elif event.key == pygame.K_p:
                        if self.game_session:
                            self.game_session.toggle_pause()
                    elif event.key == pygame.K_r:
                        if self.game_session and self.game_session.paused:
                            song = self.game_session.song
                            self._start_game(song, self._practice_speed)
                    elif event.key == pygame.K_SPACE:
                        if self.game_session:
                            self.game_session.activate_star_power()
                    else:
                        # Try computer keyboard note input
                        self.keyboard_input.handle_event(event)
                elif event.type == pygame.KEYUP:
                    self.keyboard_input.handle_event(event)

            elif self.state == STATE_CONFIRM_QUIT:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_y:
                        self.game_session = None
                        while not self.pitch_queue.empty():
                            try: self.pitch_queue.get_nowait()
                            except queue.Empty: break
                        self.state = STATE_SONG_SELECT
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        self.state = STATE_PLAYING

            elif self.state == STATE_RESULTS:
                action = self.results_screen.handle_event(event)
                if action == "continue":
                    self.state = STATE_SONG_SELECT
                elif action == "retry":
                    song = self.game_session.song if self.game_session else None
                    if song:
                        speed = self._practice_speed if self._practice_mode else 1.0
                        self._start_game(song, speed)

    def _start_game(self, song, speed=1.0, difficulty='Hard'):
        while not self.pitch_queue.empty():
            try: self.pitch_queue.get_nowait()
            except queue.Empty: break

        calibration = self.settings.get('calibration_offset', 0.0)
        self._practice_speed = speed

        # Generate difficulty arrangement if not Hard
        from piano_hero.game.song import generate_difficulty_arrangement, mark_star_power_notes
        if difficulty != 'Hard':
            arranged_notes = generate_difficulty_arrangement(song, difficulty)
            # Create a modified copy of the song with the arranged notes
            import copy
            modified_song = copy.copy(song)
            modified_song.notes = arranged_notes
            game_song = modified_song
        else:
            game_song = song

        self.game_session = GameSession(game_song, self.pitch_queue, calibration, speed)
        # Mark star power notes
        mark_star_power_notes(self.game_session.notes)
        # Set no-fail from settings
        self.game_session.no_fail = self.settings.get('no_fail', True)
        self.game_session.wait_mode = self.settings.get('wait_mode', False)

        self.highway.setup_for_song(game_song, game_song.tempo / speed)
        self.keyboard_display.setup_for_song(game_song)
        self.effects = EffectsManager()
        self._last_judgment_count = 0
        self._last_combo_count = 0
        self._last_wrong_count = 0
        self._last_hold_count = 0
        self._last_detected_midi = None
        self.game_session.start()
        self.state = STATE_PLAYING

    def _update(self, dt):
        if self.state == STATE_MENU:
            self.main_menu.update(dt)

        elif self.state == STATE_PLAYING and self.game_session:
            if self.game_session.paused:
                return
            self.game_session.update(dt)
            self.effects.update(dt)

            # Process new judgments for effects
            events = self.game_session.judgment_events
            while self._last_judgment_count < len(events):
                ev = events[self._last_judgment_count]
                self._last_judgment_count += 1

                if ev.judgment in ("perfect", "good", "ok"):
                    if ev.note.midi in self.highway.column_map:
                        x = (self.highway.column_map[ev.note.midi] +
                             self.highway.column_width // 2)
                        y = self.highway.hit_line_y
                        self.effects.spawn_hit_burst(x, y, ev.judgment)
                    self.keyboard_display.trigger_hit_flash(
                        ev.note.midi,
                        {'perfect': COLOR_PERFECT, 'good': COLOR_GOOD,
                         'ok': (100, 150, 255)}.get(ev.judgment, COLOR_GOOD))
                    self.sfx.play_judgment(ev.judgment)
                elif ev.judgment == "miss":
                    self.effects.spawn_miss_flash()
                    self.sfx.play("miss")
                    # Break streak fire if active
                    if self.game_session.score_tracker.streak == 0:
                        self.effects.set_streak_fire(False)

            # Process combos
            combos = self.game_session.combo_events
            while self._last_combo_count < len(combos):
                combo = combos[self._last_combo_count]
                self._last_combo_count += 1
                hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
                self.effects.spawn_streak_flames(hw // 2, self.highway.hit_line_y)
                self.sfx.play("combo")
                if combo.streak >= 10:
                    self.effects.set_streak_fire(True)

            # Process wrong notes
            wrongs = self.game_session.wrong_note_events
            while self._last_wrong_count < len(wrongs):
                w = wrongs[self._last_wrong_count]
                self._last_wrong_count += 1
                self.keyboard_display.trigger_wrong_flash(w.played_midi)

            # Process hold events (for HUD display)
            holds = self.game_session.hold_events
            while self._last_hold_count < len(holds):
                self._last_hold_count += 1

            # Check for Yamaha keyboard game controls
            if self.game_session.note_just_detected and self.game_session.current_detected_note:
                from piano_hero.input.keyboard_input import KeyboardNoteInput
                detected_midi = self.game_session.current_detected_note[1]
                yamaha_action = KeyboardNoteInput.get_yamaha_action(detected_midi)
                if yamaha_action == 'restart':
                    song = self.game_session.song
                    self._start_game(song, self._practice_speed)
                    return
                elif yamaha_action == 'pause':
                    self.game_session.toggle_pause()
                elif yamaha_action == 'star_power':
                    self.game_session.activate_star_power()
                elif yamaha_action == 'back_to_menu':
                    self.game_session = None
                    self.state = STATE_SONG_SELECT
                    return
                elif yamaha_action == 'next_song':
                    # Find next song in list
                    if self.song_select and self.song_select.songs:
                        idx = self.song_select.selected
                        if idx < len(self.song_select.songs) - 1:
                            self.song_select.selected = idx + 1
                            next_song = self.song_select.get_selected_song()
                            if next_song:
                                self._start_game(next_song, self._practice_speed)
                                return
                elif yamaha_action == 'prev_song':
                    if self.song_select and self.song_select.songs:
                        idx = self.song_select.selected
                        if idx > 0:
                            self.song_select.selected = idx - 1
                            prev_song = self.song_select.get_selected_song()
                            if prev_song:
                                self._start_game(prev_song, self._practice_speed)
                                return

            # Also check MIDI input for Yamaha control actions
            if self.midi_input and self.midi_input.is_running():
                midi_action = self.midi_input.get_last_action()
                if midi_action == 'restart':
                    self._start_game(self.game_session.song, self._practice_speed)
                    return
                elif midi_action == 'pause':
                    self.game_session.toggle_pause()
                elif midi_action == 'star_power':
                    self.game_session.activate_star_power()
                elif midi_action == 'back_to_menu':
                    self.game_session = None
                    self.state = STATE_SONG_SELECT
                    return

            # Audio passthrough: play detected notes through speakers
            if self.settings.get('passthrough_enabled', True):
                detected = self.game_session.current_detected_note
                if detected and self.game_session.note_just_detected:
                    detected_midi = detected[1]
                    if detected_midi != self._last_detected_midi:
                        self.sfx.play_note(detected_midi)
                        self._last_detected_midi = detected_midi
                elif not detected:
                    self._last_detected_midi = None

            # Check if song finished
            if self.game_session.finished:
                # Apply difficulty multiplier
                diff_mult = compute_song_difficulty_multiplier(self.game_session.song)
                tracker = self.game_session.score_tracker
                tracker.score = int(tracker.score * diff_mult)

                save_high_score(self.game_session.song.filepath, tracker)
                self.stats = record_session(
                    self.stats,
                    self.game_session.song.title,
                    tracker,
                    self.game_session.scaled_duration,
                )
                # Check achievements
                from piano_hero.game.achievements import check_achievements
                session_data = {
                    'score_tracker': tracker,
                    'song_title': self.game_session.song.title,
                    'practice_mode': self._practice_mode,
                }
                new_achievements = check_achievements(self.stats, session_data)
                if new_achievements:
                    self.effects.spawn_celebration(SCREEN_WIDTH, SCREEN_HEIGHT)

                from piano_hero.ui.menu import ResultsScreen
                self.results_screen = ResultsScreen(
                    self.game_session.song, tracker, diff_mult)
                self.state = STATE_RESULTS

        elif self.state == STATE_RESULTS and self.results_screen:
            self.results_screen.update(dt)

    def _draw(self):
        if self.state == STATE_MENU:
            self.main_menu.draw(self.screen)

        elif self.state == STATE_SONG_SELECT:
            self.song_select.draw(self.screen)

        elif self.state == STATE_SETTINGS:
            self.settings_menu.draw(self.screen,
                                     self.audio_engine.get_input_level()
                                     if self.audio_engine and self.audio_engine.is_running()
                                     else 0.0)

        elif self.state == STATE_CALIBRATE and self.calibration_screen:
            self.calibration_screen.draw(self.screen)

        elif self.state == STATE_STATS and self.stats_screen:
            self.stats_screen.draw(self.screen)

        elif self.state in (STATE_PLAYING, STATE_CONFIRM_QUIT) and self.game_session:
            self.screen.blit(self._bg_surface, (0, 0))

            show_names = self.settings.get('show_note_names', True)
            star_power = getattr(self.game_session, 'star_power_active', False)
            self.highway.perspective_enabled = self.settings.get('perspective_3d', True)
            self.highway.draw(self.screen, self.game_session.current_time,
                              self.game_session.notes, show_names,
                              game_session=self.game_session,
                              star_power_active=star_power)

            # Only highlight the next note on the keyboard when it's
            # within 1.5 beats of the hit line (not when it's far away)
            target_midi = None
            beat_dur = self.game_session.song.beat_duration / self.game_session.speed_multiplier
            approach_window = beat_dur * 1.5
            for n in self.game_session.notes:
                if not n.hit:
                    time_until = n.start_time - self.game_session.current_time
                    if time_until <= approach_window:
                        target_midi = n.midi
                    break
            # Get active hold midis for keyboard glow
            active_hold_midis = set()
            if hasattr(self.game_session, '_active_holds'):
                for hold in self.game_session._active_holds.values():
                    active_hold_midis.add(hold.midi)

            self.keyboard_display.draw(
                self.screen,
                self.game_session.current_detected_note,
                target_midi,
                set(self.game_session.song.unique_notes()),
                show_key_labels=True,
                active_hold_midis=active_hold_midis,
            )

            self.hud.draw(self.screen, self.game_session.score_tracker,
                          self.game_session)
            self.effects.draw(self.screen)

            if self.game_session.countdown_active and self.game_session.current_time < 0:
                from piano_hero.game.lessons import get_lesson_tip
                tip = get_lesson_tip(self.game_session.song)
                self.hud.draw_countdown(self.screen, -self.game_session.current_time, tip)

            if self.game_session.paused:
                self._draw_pause_overlay()

            # Audio level indicator
            if self.audio_engine and self.audio_engine.is_running():
                level = self.audio_engine.get_input_level()
                bar_x = SCREEN_WIDTH - 30
                bar_h = 60
                bar_y = SCREEN_HEIGHT - KEYBOARD_HEIGHT - bar_h - 10
                pygame.draw.rect(self.screen, (40, 40, 40),
                                 (bar_x, bar_y, 15, bar_h))
                fill_h = int(bar_h * min(1.0, level * 10))
                if fill_h > 0:
                    color = (0, 255, 0) if level > 0.005 else (80, 80, 80)
                    pygame.draw.rect(self.screen, color,
                                     (bar_x, bar_y + bar_h - fill_h, 15, fill_h))

            # Practice mode indicator
            if self._practice_mode and self._practice_speed != 1.0:
                font = get_font(14)
                draw_text(self.screen, f"Speed: {int(self._practice_speed*100)}%",
                          (10, 10), font, COLOR_ACCENT)

            # Confirm quit overlay
            if self.state == STATE_CONFIRM_QUIT:
                self._draw_confirm_quit()

        elif self.state == STATE_RESULTS:
            self.results_screen.draw(self.screen)

    def _draw_pause_overlay(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        font = get_title_font(48)
        draw_text(self.screen, "PAUSED", (cx, cy - 80), font,
                  COLOR_WHITE, center=True, shadow=True)

        # Pause menu options
        menu_font = get_font(24, bold=True)
        options = [
            ("Resume (P)", COLOR_ACCENT),
            ("Restart (R)", COLOR_ACCENT),
            ("Song Select (ESC)", COLOR_GRAY),
        ]
        for i, (text, color) in enumerate(options):
            draw_text(self.screen, text, (cx, cy - 10 + i * 40),
                      menu_font, color, center=True)

        # Yamaha keyboard hints
        hint_font = get_font(14)
        draw_text(self.screen, "Yamaha: F2=Pause  C2=Restart  B2=Song Select",
                  (cx, cy + 120), hint_font, COLOR_DARK_GRAY, center=True)

    def _draw_confirm_quit(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        font = get_title_font(36)
        draw_text(self.screen, "Quit this song?",
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30),
                  font, COLOR_WHITE, center=True, shadow=True)
        small = get_font(20)
        draw_text(self.screen, "Y = Yes  |  N = No",
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20),
                  small, COLOR_ACCENT, center=True)
