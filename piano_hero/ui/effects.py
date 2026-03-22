"""Visual effects -- particles, screen shake, sparkle trails, miss crack,
combo fire border, reactive background, star power visuals, and stage lighting."""

import random
import math
import pygame
from piano_hero.constants import (
    COLOR_PERFECT, COLOR_GOOD, COLOR_OK, COLOR_MISS, COLOR_STREAK_FLAME,
    SCREEN_WIDTH, SCREEN_HEIGHT, HIGHWAY_WIDTH_RATIO, KEYBOARD_HEIGHT,
    COLOR_ACCENT, BG_GRADIENT_TOP, BG_GRADIENT_BOTTOM, BG_COLOR,
)


# ---------------------------------------------------------------------------
# Particle
# ---------------------------------------------------------------------------

class Particle:
    """A single particle for burst / trail / fire effects."""

    __slots__ = ("x", "y", "color", "vx", "vy", "lifetime", "age", "size",
                 "no_gravity")

    def __init__(self, x, y, color, vx=0, vy=0, lifetime=0.5, size=4,
                 no_gravity=False):
        self.x = x
        self.y = y
        self.color = color
        self.vx = vx
        self.vy = vy
        self.lifetime = lifetime
        self.age = 0.0
        self.size = size
        self.no_gravity = no_gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not self.no_gravity:
            self.vy += 200 * dt  # gravity
        self.age += dt

    @property
    def alive(self):
        return self.age < self.lifetime

    @property
    def alpha(self):
        return max(0.0, 1.0 - self.age / self.lifetime)


# ---------------------------------------------------------------------------
# Crack shard (for streak-break shatter)
# ---------------------------------------------------------------------------

class CrackShard:
    """A short line segment that flies outward then fades."""

    __slots__ = ("x", "y", "vx", "vy", "length", "angle", "color",
                 "lifetime", "age")

    def __init__(self, x, y, angle, speed, length, color, lifetime=0.4):
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.length = length
        self.angle = angle
        self.color = color
        self.lifetime = lifetime
        self.age = 0.0

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.age += dt

    @property
    def alive(self):
        return self.age < self.lifetime

    @property
    def alpha(self):
        return max(0.0, 1.0 - self.age / self.lifetime)


# ---------------------------------------------------------------------------
# Spotlight (for stage lighting)
# ---------------------------------------------------------------------------

class _Spotlight:
    """A sweeping colored beam for stage lighting."""

    __slots__ = ("color", "speed", "phase", "width", "intensity")

    def __init__(self, color, speed, phase, width=0.15, intensity=0.35):
        self.color = color
        self.speed = speed       # radians per second
        self.phase = phase       # initial phase offset
        self.width = width       # beam width as fraction of highway
        self.intensity = intensity

    def get_x_fraction(self, t):
        """Return 0..1 position across highway at time *t*."""
        return 0.5 + 0.45 * math.sin(self.speed * t + self.phase)


# ---------------------------------------------------------------------------
# Background Renderer
# ---------------------------------------------------------------------------

class BackgroundRenderer:
    """Draws the reactive background behind the highway: gradient, pulse,
    stage lights, and crowd silhouettes."""

    def __init__(self):
        # Spotlights with different speeds and colors
        self._spotlights = [
            _Spotlight((80, 60, 200), speed=0.7, phase=0.0, width=0.12, intensity=0.30),
            _Spotlight((200, 40, 120), speed=1.1, phase=2.1, width=0.10, intensity=0.25),
            _Spotlight((40, 160, 220), speed=0.5, phase=4.2, width=0.14, intensity=0.28),
            _Spotlight((180, 180, 60), speed=0.9, phase=1.0, width=0.11, intensity=0.22),
        ]

        # Pre-build crowd silhouette y-offsets (fixed random heights)
        self._crowd_count = 30
        self._crowd_heights = [random.uniform(18, 35) for _ in range(self._crowd_count)]
        self._crowd_widths = [random.uniform(8, 14) for _ in range(self._crowd_count)]
        self._crowd_phases = [random.uniform(0, 2 * math.pi) for _ in range(self._crowd_count)]

        # Cached gradient surface (rebuilt on size change)
        self._grad_cache = None
        self._grad_size = (0, 0)

    # ---- colour helpers ----

    @staticmethod
    def _lerp_color(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def _performance_gradient(self, performance_pct):
        """Return (top, bottom) gradient colours tinted by performance."""
        # Neutral purple -> blue-purple (good) / red-tinted (poor)
        if performance_pct >= 0.5:
            # 0.5..1.0 -> neutral to blue-purple
            t = (performance_pct - 0.5) * 2.0
            top = self._lerp_color(BG_GRADIENT_TOP, (15, 0, 60), t)
            bot = self._lerp_color(BG_GRADIENT_BOTTOM, (5, 0, 40), t)
        else:
            # 0.0..0.5 -> neutral to red-tinted
            t = (0.5 - performance_pct) * 2.0
            top = self._lerp_color(BG_GRADIENT_TOP, (50, 0, 20), t)
            bot = self._lerp_color(BG_GRADIENT_BOTTOM, (30, 0, 10), t)
        return top, bot

    def _star_power_gradient(self):
        """Deep blue gradient for star power."""
        return (5, 10, 50), (0, 5, 30)

    # ---- main draw ----

    def draw_background(self, surface, highway_width, highway_height,
                        performance_pct, beat_time, star_power_active):
        """Draw the full reactive background onto *surface*.

        Parameters
        ----------
        surface : pygame.Surface
            Target surface (highway-sized or full screen).
        highway_width, highway_height : int
            Pixel dimensions of the highway area.
        performance_pct : float
            0.0 (terrible) to 1.0 (perfect).
        beat_time : float
            Monotonic time in seconds used for pulsing / animation sync.
        star_power_active : bool
            Whether star power is currently engaged.
        """
        w, h = highway_width, highway_height

        # -- 1. Base gradient --
        if star_power_active:
            top_col, bot_col = self._star_power_gradient()
        else:
            top_col, bot_col = self._performance_gradient(performance_pct)

        # Performance pulse: subtle brightness oscillation on beat
        pulse = 0.5 + 0.5 * math.sin(beat_time * math.pi * 2.0)  # 0..1
        pulse_boost = int(8 * pulse)

        # Build gradient column (1-pixel wide) and scale — cache when size unchanged
        need_rebuild = (self._grad_size != (w, h))
        if need_rebuild:
            self._grad_size = (w, h)
        # We always rebuild because colours shift each frame (cheap enough for 1-col scale)
        col_surf = pygame.Surface((1, h), pygame.SRCALPHA)
        for row in range(h):
            t = row / max(h - 1, 1)
            r = min(255, int(top_col[0] + (bot_col[0] - top_col[0]) * t) + pulse_boost)
            g = min(255, int(top_col[1] + (bot_col[1] - top_col[1]) * t) + pulse_boost)
            b = min(255, int(top_col[2] + (bot_col[2] - top_col[2]) * t) + pulse_boost)
            col_surf.set_at((0, row), (r, g, b, 255))
        grad = pygame.transform.scale(col_surf, (w, h))
        surface.blit(grad, (0, 0))

        # -- 2. Stage spotlights --
        spot_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for spot in self._spotlights:
            frac = spot.get_x_fraction(beat_time)
            cx = int(frac * w)
            beam_half = max(1, int(spot.width * w * 0.5))

            # Intensity reacts to performance (better = brighter beams)
            eff_intensity = spot.intensity * (0.5 + 0.5 * performance_pct)
            if star_power_active:
                eff_intensity = min(1.0, eff_intensity * 1.5)

            alpha_peak = int(255 * eff_intensity)

            for dx in range(-beam_half, beam_half + 1):
                px = cx + dx
                if px < 0 or px >= w:
                    continue
                dist = abs(dx) / max(beam_half, 1)
                a = int(alpha_peak * (1.0 - dist * dist))  # quadratic falloff
                # Draw a vertical strip
                strip = pygame.Surface((1, h), pygame.SRCALPHA)
                for row in range(0, h, 4):  # every 4 pixels for speed
                    fade = 1.0 - (row / max(h, 1))  # brighter at top
                    sa = max(0, min(255, int(a * fade)))
                    strip.set_at((0, row), (*spot.color, sa))
                    if row + 1 < h:
                        strip.set_at((0, min(row + 1, h - 1)), (*spot.color, sa))
                    if row + 2 < h:
                        strip.set_at((0, min(row + 2, h - 1)), (*spot.color, sa))
                    if row + 3 < h:
                        strip.set_at((0, min(row + 3, h - 1)), (*spot.color, sa))
                spot_surf.blit(strip, (px, 0))

        surface.blit(spot_surf, (0, 0))

        # -- 3. Crowd silhouettes --
        crowd_y_base = h - 20
        sway_amount = 3.0 * performance_pct  # sway more when playing well
        bounce_amount = 2.0 * performance_pct

        crowd_surf = pygame.Surface((w, 50), pygame.SRCALPHA)
        spacing = max(1, w / max(self._crowd_count, 1))
        for i in range(self._crowd_count):
            cx = int(i * spacing + spacing * 0.5)
            ch = self._crowd_heights[i]
            cw = self._crowd_widths[i]

            sway_x = sway_amount * math.sin(beat_time * 1.8 + self._crowd_phases[i])
            bounce_y = bounce_amount * abs(math.sin(beat_time * 2.5 + self._crowd_phases[i]))

            bx = int(cx + sway_x)
            by = int(50 - bounce_y)

            # Body (ellipse)
            body_rect = pygame.Rect(bx - int(cw // 2), by - int(ch * 0.6),
                                    int(cw), int(ch * 0.6))
            pygame.draw.ellipse(crowd_surf, (10, 5, 18, 200), body_rect)

            # Head (circle)
            head_r = max(2, int(cw * 0.35))
            head_y = by - int(ch * 0.6) - head_r
            pygame.draw.circle(crowd_surf, (10, 5, 18, 200), (bx, head_y), head_r)

        surface.blit(crowd_surf, (0, crowd_y_base - 30))


# ---------------------------------------------------------------------------
# Effects manager
# ---------------------------------------------------------------------------

class EffectsManager:
    """Manages all visual effects: particles, sparkle trails, screen shake,
    miss crack, combo fire border, star power, and reactive background."""

    def __init__(self):
        self.particles: list[Particle] = []
        self.shards: list[CrackShard] = []

        self._flash_alpha = 0.0
        self._flash_color = (255, 255, 255)

        # Screen shake
        self._screen_shake = 0.0

        # Combo fire state
        self._streak_fire = False
        self._fire_timer = 0.0

        # Performance / beat / star power state
        self._performance_pct = 0.5
        self._beat_time = 0.0
        self._star_power_active = False

        # Current streak (for enhanced fire + lightning)
        self._current_streak = 0

        # Lightning flash state
        self._lightning_timer = 0.0
        self._lightning_bolts: list[tuple] = []  # list of (segments, age, lifetime)

        # Background renderer
        self.background = BackgroundRenderer()

        # Star-power edge flame timer
        self._sp_edge_timer = 0.0

    # ------------------------------------------------------------------
    # State setters (called from game loop)
    # ------------------------------------------------------------------

    def set_performance(self, pct):
        """Set current performance percentage (0.0 to 1.0)."""
        self._performance_pct = max(0.0, min(1.0, pct))

    def set_beat_time(self, t):
        """Set current beat time for pulse synchronisation."""
        self._beat_time = t

    def set_star_power(self, active):
        """Enable or disable star power visuals."""
        self._star_power_active = bool(active)

    def set_streak(self, streak):
        """Update current streak count for enhanced fire effects."""
        self._current_streak = max(0, int(streak))

    # ------------------------------------------------------------------
    # Spawn helpers
    # ------------------------------------------------------------------

    def spawn_hit_burst(self, x, y, judgment):
        """Spawn particles for a note hit."""
        colors = {
            "perfect": COLOR_PERFECT,
            "good": COLOR_GOOD,
            "ok": COLOR_OK,
        }
        color = colors.get(judgment, COLOR_GOOD)
        count = {"perfect": 20, "good": 12, "ok": 6}.get(judgment, 6)

        # Star power: more intense bursts
        if self._star_power_active:
            count = int(count * 1.6)

        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(50, 200)
            if self._star_power_active:
                speed *= 1.3
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - 100  # bias upward
            size = random.uniform(2, 6)
            lifetime = random.uniform(0.3, 0.7)
            self.particles.append(Particle(x, y, color, vx, vy, lifetime, size))

        # Star power: extra sparkle overlay
        if self._star_power_active:
            self._spawn_star_sparkles(x, y)

    def spawn_hit_trail(self, x, y, judgment):
        """Spawn a sparkle trail at the hit location -- small particles
        with no gravity that fade in place."""
        colors = {
            "perfect": COLOR_PERFECT,
            "good": COLOR_GOOD,
            "ok": COLOR_OK,
        }
        color = colors.get(judgment, COLOR_GOOD)
        count = {"perfect": 8, "good": 5, "ok": 3}.get(judgment, 3)

        for _ in range(count):
            sx = x + random.uniform(-15, 15)
            sy = y + random.uniform(-10, 10)
            size = random.uniform(2, 5)
            lifetime = random.uniform(0.2, 0.5)
            # Sparkle: tiny stationary particle with no gravity
            self.particles.append(
                Particle(sx, sy, color, 0, 0, lifetime, size, no_gravity=True)
            )

    def spawn_miss_flash(self):
        """Brief red flash for a miss."""
        self._flash_alpha = 80.0
        self._flash_color = COLOR_MISS

    def spawn_miss_crack(self, x, y):
        """Crack / shatter effect when breaking a streak."""
        num_shards = random.randint(6, 12)
        for _ in range(num_shards):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(80, 250)
            length = random.uniform(8, 20)
            lifetime = random.uniform(0.25, 0.5)
            color = random.choice([COLOR_MISS, (255, 120, 80), (200, 50, 50)])
            self.shards.append(
                CrackShard(x, y, angle, speed, length, color, lifetime)
            )

    def spawn_streak_flames(self, x, y):
        """Flame particles for streak milestones. Also triggers screen shake."""
        for _ in range(12):
            vx = random.uniform(-40, 40)
            vy = random.uniform(-180, -50)
            color = random.choice(
                [COLOR_STREAK_FLAME, COLOR_PERFECT, (255, 200, 50)]
            )
            self.particles.append(
                Particle(x, y, color, vx, vy, 0.7, random.uniform(3, 8))
            )
        self._screen_shake = max(self._screen_shake, 6.0)

    def spawn_streak_break(self, x, y):
        """Visual effect when a streak is broken -- particles + crack."""
        for _ in range(8):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(30, 100)
            self.particles.append(Particle(
                x, y, COLOR_MISS,
                math.cos(angle) * speed, math.sin(angle) * speed,
                0.4, random.uniform(2, 5),
            ))
        self.spawn_miss_crack(x, y)
        self._screen_shake = max(self._screen_shake, 4.0)

    def spawn_star_power_burst(self, x, y):
        """Special cyan/white burst for star power activation or hits."""
        sp_colors = [(0, 220, 255), (100, 240, 255), (200, 255, 255),
                     (255, 255, 255), COLOR_ACCENT]
        for _ in range(25):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(80, 280)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - 80
            color = random.choice(sp_colors)
            size = random.uniform(3, 7)
            lifetime = random.uniform(0.4, 0.9)
            self.particles.append(Particle(x, y, color, vx, vy, lifetime, size))

        # Add a few no-gravity sparkles
        for _ in range(10):
            sx = x + random.uniform(-30, 30)
            sy = y + random.uniform(-20, 20)
            color = random.choice([(255, 255, 255), (150, 240, 255)])
            self.particles.append(
                Particle(sx, sy, color, 0, random.uniform(-20, -5),
                         random.uniform(0.3, 0.6), random.uniform(2, 4),
                         no_gravity=True)
            )

    def spawn_celebration(self, width, height):
        """Full-screen celebration effect for new achievements/high scores."""
        colors = [
            (255, 215, 0), (255, 100, 100), (100, 255, 100),
            (100, 100, 255), (255, 100, 255), (0, 255, 255),
            (255, 200, 50), (255, 150, 0),
        ]
        # Fireworks from bottom
        for _ in range(60):
            x = random.randint(50, width - 50)
            y = height
            vx = random.uniform(-80, 80)
            vy = random.uniform(-400, -200)
            color = random.choice(colors)
            size = random.uniform(3, 7)
            lifetime = random.uniform(0.8, 1.5)
            self.particles.append(Particle(x, y, color, vx, vy, lifetime, size))

    def set_streak_fire(self, active):
        """Enable or disable the combo fire border (streak >= 10)."""
        self._streak_fire = active

    # ------------------------------------------------------------------
    # Internal spawn helpers
    # ------------------------------------------------------------------

    def _spawn_star_sparkles(self, x, y):
        """Extra sparkle particles on hit during star power."""
        sparkle_colors = [(200, 240, 255), (150, 220, 255), (255, 255, 255)]
        for _ in range(6):
            sx = x + random.uniform(-20, 20)
            sy = y + random.uniform(-15, 15)
            color = random.choice(sparkle_colors)
            self.particles.append(
                Particle(sx, sy, color,
                         random.uniform(-15, 15), random.uniform(-30, -5),
                         random.uniform(0.3, 0.6), random.uniform(1.5, 3.5),
                         no_gravity=True)
            )

    def _emit_fire_particle(self):
        """Emit a single flame particle along the highway edges."""
        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        highway_bottom = SCREEN_HEIGHT - KEYBOARD_HEIGHT

        # Determine intensity based on streak
        intense = self._current_streak >= 25
        super_intense = self._current_streak >= 50

        # Pick a random edge (left or right of highway)
        if random.random() < 0.5:
            x = random.uniform(0, 6)
        else:
            x = random.uniform(hw - 6, hw)
        y = random.uniform(highway_bottom * 0.4, highway_bottom)
        vx = random.uniform(-10, 10)
        vy = random.uniform(-80, -25)
        color = random.choice(
            [COLOR_STREAK_FLAME, (255, 180, 30), (255, 80, 0), COLOR_PERFECT]
        )
        lifetime = random.uniform(0.3, 0.55)
        size = random.uniform(2, 5)

        # Bigger, more particles at high streaks
        if intense:
            size *= 1.4
            lifetime *= 1.2
            vy *= 1.3
        if super_intense:
            size *= 1.2
            lifetime *= 1.1

        self.particles.append(
            Particle(x, y, color, vx, vy, lifetime, size, no_gravity=True)
        )

        # At high streaks, emit an extra particle for density
        if intense:
            # Second particle on the opposite edge
            if x < hw / 2:
                x2 = random.uniform(hw - 6, hw)
            else:
                x2 = random.uniform(0, 6)
            y2 = random.uniform(highway_bottom * 0.3, highway_bottom)
            self.particles.append(
                Particle(x2, y2, color,
                         random.uniform(-10, 10), random.uniform(-90, -30),
                         lifetime, size, no_gravity=True)
            )

    def _emit_star_power_edge_flames(self):
        """Emit blue flame particles along highway edges during star power."""
        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        highway_bottom = SCREEN_HEIGHT - KEYBOARD_HEIGHT

        sp_colors = [(0, 100, 255), (30, 150, 255), (80, 180, 255),
                     (0, 200, 255), (100, 220, 255)]

        for _ in range(2):
            # Left edge
            x = random.uniform(0, 8)
            y = random.uniform(highway_bottom * 0.3, highway_bottom)
            color = random.choice(sp_colors)
            self.particles.append(
                Particle(x, y, color,
                         random.uniform(-8, 8), random.uniform(-100, -30),
                         random.uniform(0.35, 0.6), random.uniform(2.5, 5.5),
                         no_gravity=True)
            )
            # Right edge
            x = random.uniform(hw - 8, hw)
            y = random.uniform(highway_bottom * 0.3, highway_bottom)
            color = random.choice(sp_colors)
            self.particles.append(
                Particle(x, y, color,
                         random.uniform(-8, 8), random.uniform(-100, -30),
                         random.uniform(0.35, 0.6), random.uniform(2.5, 5.5),
                         no_gravity=True)
            )

    def _generate_lightning_bolt(self):
        """Generate a jagged lightning bolt between left and right highway edges."""
        hw = int(SCREEN_WIDTH * HIGHWAY_WIDTH_RATIO)
        highway_bottom = SCREEN_HEIGHT - KEYBOARD_HEIGHT

        # Random vertical position
        y_start = random.uniform(highway_bottom * 0.2, highway_bottom * 0.7)
        segments = []
        x = 3  # left edge
        y = y_start
        target_x = hw - 3
        steps = random.randint(5, 10)
        dx_step = (target_x - x) / steps

        for i in range(steps):
            next_x = x + dx_step + random.uniform(-10, 10)
            next_y = y + random.uniform(-20, 20)
            segments.append(((int(x), int(y)), (int(next_x), int(next_y))))
            x, y = next_x, next_y

        lifetime = random.uniform(0.08, 0.18)
        self._lightning_bolts.append((segments, 0.0, lifetime))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt):
        """Advance all effect animations by *dt* seconds."""
        # Particles
        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles:
            p.update(dt)

        # Crack shards
        self.shards = [s for s in self.shards if s.alive]
        for s in self.shards:
            s.update(dt)

        # Flash fade
        if self._flash_alpha > 0:
            self._flash_alpha = max(0.0, self._flash_alpha - 300 * dt)

        # Screen shake decay
        if self._screen_shake > 0:
            self._screen_shake = max(0.0, self._screen_shake - 12 * dt)

        # Combo fire: ambient flame particles along highway edges
        if self._streak_fire:
            self._fire_timer += dt
            emit_rate = 0.04
            if self._current_streak >= 25:
                emit_rate = 0.025
            if self._current_streak >= 50:
                emit_rate = 0.018
            if self._fire_timer > emit_rate:
                self._fire_timer = 0.0
                self._emit_fire_particle()

        # Star power edge flames
        if self._star_power_active:
            self._sp_edge_timer += dt
            if self._sp_edge_timer > 0.05:
                self._sp_edge_timer = 0.0
                self._emit_star_power_edge_flames()

        # Lightning bolts at streak >= 50
        if self._streak_fire and self._current_streak >= 50:
            self._lightning_timer += dt
            if self._lightning_timer > 0.3:
                self._lightning_timer = 0.0
                self._generate_lightning_bolt()

        # Age lightning bolts
        updated_bolts = []
        for segments, age, lifetime in self._lightning_bolts:
            new_age = age + dt
            if new_age < lifetime:
                updated_bolts.append((segments, new_age, lifetime))
        self._lightning_bolts = updated_bolts

        # Beat time advances (if driven externally this is a no-op; if not,
        # we auto-advance so effects still animate)
        self._beat_time += dt

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw_background(self, surface, highway_width, highway_height):
        """Draw the reactive background. Call before drawing the highway."""
        self.background.draw_background(
            surface, highway_width, highway_height,
            self._performance_pct, self._beat_time, self._star_power_active,
        )

    def draw(self, surface):
        """Draw all active effects onto *surface*."""
        # Lightning bolts (draw behind particles)
        for segments, age, lifetime in self._lightning_bolts:
            bolt_alpha = max(0.0, 1.0 - age / lifetime)
            alpha_val = int(bolt_alpha * 220)
            for (x1, y1), (x2, y2) in segments:
                min_x = min(x1, x2) - 4
                min_y = min(y1, y2) - 4
                w = abs(x2 - x1) + 10
                h = abs(y2 - y1) + 10
                if w > 0 and h > 0:
                    bolt_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                    # Glow layer (thicker, dimmer)
                    glow_color = (150, 180, 255, max(0, alpha_val // 2))
                    pygame.draw.line(
                        bolt_surf, glow_color,
                        (x1 - min_x, y1 - min_y),
                        (x2 - min_x, y2 - min_y),
                        max(1, int(4 * bolt_alpha)),
                    )
                    # Core layer (thin, bright)
                    core_color = (220, 230, 255, alpha_val)
                    pygame.draw.line(
                        bolt_surf, core_color,
                        (x1 - min_x, y1 - min_y),
                        (x2 - min_x, y2 - min_y),
                        max(1, int(2 * bolt_alpha)),
                    )
                    surface.blit(bolt_surf, (min_x, min_y))

        # Particles (includes fire, sparkles, and burst particles)
        for p in self.particles:
            alpha_val = int(p.alpha * 255)
            size = max(1, int(p.size * p.alpha))
            color = (*p.color[:3], alpha_val)
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (size, size), size)
            surface.blit(surf, (int(p.x) - size, int(p.y) - size))

        # Crack shards (short fading line segments)
        for shard in self.shards:
            alpha_val = int(shard.alpha * 255)
            ex = shard.x + math.cos(shard.angle) * shard.length * shard.alpha
            ey = shard.y + math.sin(shard.angle) * shard.length * shard.alpha
            color = (*shard.color[:3], alpha_val)
            min_x = int(min(shard.x, ex)) - 2
            min_y = int(min(shard.y, ey)) - 2
            w = int(abs(ex - shard.x)) + 6
            h = int(abs(ey - shard.y)) + 6
            if w > 0 and h > 0:
                line_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.line(
                    line_surf, color,
                    (int(shard.x) - min_x, int(shard.y) - min_y),
                    (int(ex) - min_x, int(ey) - min_y),
                    max(1, int(2 * shard.alpha)),
                )
                surface.blit(line_surf, (min_x, min_y))

        # Screen flash overlay
        if self._flash_alpha > 0:
            flash_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            flash_surf.fill((*self._flash_color[:3], int(self._flash_alpha)))
            surface.blit(flash_surf, (0, 0))

    # ------------------------------------------------------------------
    # Screen shake
    # ------------------------------------------------------------------

    def get_shake_offset(self):
        """Return (dx, dy) pixel offset for screen shake."""
        if self._screen_shake > 0.5:
            dx = random.uniform(-self._screen_shake, self._screen_shake)
            dy = random.uniform(-self._screen_shake, self._screen_shake)
            return int(dx), int(dy)
        return 0, 0
