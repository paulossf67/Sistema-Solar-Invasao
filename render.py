"""Utilitários de render com cache (fontes e superfícies translúcidas)."""
import pygame


_font_cache = {}
_surf_cache = {}


def get_font(size, bold=False):
    key = (size, bold)
    f = _font_cache.get(key)
    if f is None:
        f = _font_cache[key] = pygame.font.SysFont("consolas", size, bold=bold)
    return f


def _cached_surface(key, builder):
    surf = _surf_cache.get(key)
    if surf is None:
        if len(_surf_cache) > 600:
            _surf_cache.clear()
        surf = _surf_cache[key] = builder()
    return surf


def blit_glow_circle(screen, color, alpha, radius, cx, cy):
    """Círculo translúcido preenchido, com superfície reutilizada entre frames."""
    r = max(1, int(radius))
    a = max(0, min(255, (int(alpha) // 4) * 4))
    def build():
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, a), (r, r), r)
        return s
    screen.blit(_cached_surface(("c", r, tuple(color), a), build), (cx - r, cy - r))


def blit_glow_ellipse(screen, color, alpha, w, h, width, x, y):
    """Elipse (anel) translúcida com superfície reutilizada entre frames."""
    w, h = max(2, int(w)), max(2, int(h))
    a = max(0, min(255, (int(alpha) // 8) * 8))
    def build():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (*color, a), s.get_rect(), width)
        return s
    screen.blit(_cached_surface(("e", w, h, tuple(color), a, width), build), (x, y))

