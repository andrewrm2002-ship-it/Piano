"""Main rendering coordinator and utility functions."""

import pygame
from piano_hero.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, BG_GRADIENT_TOP, BG_GRADIENT_BOTTOM,
)


def init_display(fullscreen=False):
    """Initialize pygame and create the game window."""
    pygame.init()
    flags = 0
    if fullscreen:
        flags |= pygame.FULLSCREEN
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
    pygame.display.set_caption("Piano Hero")
    return screen


def draw_gradient_bg(surface):
    """Draw a vertical gradient background."""
    w, h = surface.get_size()
    for y in range(h):
        t = y / h
        r = int(BG_GRADIENT_TOP[0] * (1 - t) + BG_GRADIENT_BOTTOM[0] * t)
        g = int(BG_GRADIENT_TOP[1] * (1 - t) + BG_GRADIENT_BOTTOM[1] * t)
        b = int(BG_GRADIENT_TOP[2] * (1 - t) + BG_GRADIENT_BOTTOM[2] * t)
        pygame.draw.line(surface, (r, g, b), (0, y), (w, y))


# Cache the gradient so we only draw it once
_gradient_cache = None


def get_gradient_bg(width, height):
    """Get a cached gradient background surface."""
    global _gradient_cache
    if _gradient_cache is None or _gradient_cache.get_size() != (width, height):
        _gradient_cache = pygame.Surface((width, height))
        draw_gradient_bg(_gradient_cache)
    return _gradient_cache


def _ensure_font_init():
    """Ensure pygame font system is initialized."""
    if not pygame.font.get_init():
        pygame.font.init()


def get_font(size, bold=False):
    """Get a pygame font. Uses system fonts with fallback."""
    _ensure_font_init()
    try:
        font = pygame.font.SysFont("segoeui,arial,helvetica", size, bold=bold)
    except Exception:
        font = pygame.font.Font(None, size)
    return font


def get_title_font(size):
    """Get a bold display font for titles."""
    _ensure_font_init()
    try:
        font = pygame.font.SysFont("impact,arial black,arial", size, bold=True)
    except Exception:
        font = pygame.font.Font(None, size)
    return font


def draw_text(surface, text, pos, font, color=(255, 255, 255),
              center=False, shadow=False):
    """Draw text with optional shadow and centering."""
    if shadow:
        shadow_surf = font.render(text, True, (0, 0, 0))
        if center:
            shadow_rect = shadow_surf.get_rect(center=(pos[0] + 2, pos[1] + 2))
        else:
            shadow_rect = shadow_surf.get_rect(topleft=(pos[0] + 2, pos[1] + 2))
        surface.blit(shadow_surf, shadow_rect)

    text_surf = font.render(text, True, color)
    if center:
        text_rect = text_surf.get_rect(center=pos)
    else:
        text_rect = text_surf.get_rect(topleft=pos)
    surface.blit(text_surf, text_rect)
    return text_rect


def lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB or RGBA colors.

    Args:
        c1: Starting color tuple (R, G, B) or (R, G, B, A).
        c2: Ending color tuple (same length as c1).
        t: Interpolation factor clamped to [0, 1].

    Returns:
        Interpolated color tuple with the same number of channels.
    """
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def draw_rounded_rect_glow(surface, color, rect, radius, glow_size):
    """Draw a rounded rectangle with a soft glow around it.

    Args:
        surface: Target pygame Surface.
        color: Base RGB color for the rectangle and glow.
        rect: pygame.Rect defining the rectangle.
        radius: Corner radius for the rounded rectangle.
        glow_size: How many pixels outward the glow extends.
    """
    # Draw concentric glow layers from outside in with increasing alpha
    for i in range(glow_size, 0, -1):
        alpha = int(40 * (1.0 - i / glow_size))
        glow_rect = rect.inflate(i * 2, i * 2)
        glow_surf = pygame.Surface(
            (glow_rect.width, glow_rect.height), pygame.SRCALPHA
        )
        glow_color = (*color[:3], alpha)
        pygame.draw.rect(
            glow_surf, glow_color,
            pygame.Rect(0, 0, glow_rect.width, glow_rect.height),
            border_radius=radius + i,
        )
        surface.blit(glow_surf, glow_rect.topleft)

    # Draw the solid rectangle on top
    pygame.draw.rect(surface, color, rect, border_radius=radius)
