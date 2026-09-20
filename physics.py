"""Gravidade, energia, momento angular, colisões e previsão de trajetória."""
import math

import numpy as np

from config import *


def compute_gravity_accel(x, y, bodies, mass_scale=1.0, exclude=None):
    """Calcula aceleração gravitacional em (x,y) causada por todos os bodies."""
    ax, ay = 0.0, 0.0
    for body in bodies:
        if body is exclude:
            continue
        dx = body.x - x
        dy = body.y - y
        dist_sq = dx*dx + dy*dy + SOFTENING*SOFTENING
        dist = math.sqrt(dist_sq)
        force = G * body.mass * mass_scale / dist_sq
        rng = getattr(body, "gravity_range", None)
        if rng:
            # Alcance suave: buracos negros dominam perto, mas não desestabilizam o sistema solar
            force /= 1.0 + (dist / rng) ** 4
        ax += force * dx / dist
        ay += force * dy / dist
    return ax, ay


def compute_system_energy(bodies, player=None):
    """
    Energia mecânica do sistema Sol + planetas + nave (buracos negros e aliens
    ficam de fora, pois têm gravidade de alcance limitado / massa desprezível).
    E = Σ ½ m v²  -  Σ_{i<j} G m_i m_j / r_ij
    Empuxo e jatos realizam trabalho externo, então E varia por causa deles.
    """
    kinetic = 0.0
    potential = 0.0
    solar = [b for b in bodies if not getattr(b, "is_black_hole", False)]

    n = len(solar)
    for i, b in enumerate(solar):
        if not b.is_sun:
            kinetic += 0.5 * b.mass * (b.vx*b.vx + b.vy*b.vy)
        for j in range(i + 1, n):
            other = solar[j]
            dx = other.x - b.x
            dy = other.y - b.y
            r = math.sqrt(dx*dx + dy*dy + SOFTENING*SOFTENING)
            potential -= G * b.mass * other.mass / r

    if player is not None:
        kinetic += 0.5 * (player.vx*player.vx + player.vy*player.vy)
        for b in solar:
            dx = b.x - player.x
            dy = b.y - player.y
            r = math.sqrt(dx*dx + dy*dy + SOFTENING*SOFTENING)
            potential -= G * 1.0 * b.mass / r

    return kinetic + potential, kinetic, potential


def compute_angular_momentum(bodies, player=None, origin=(0.0, 0.0)):
    """
    Momento angular total em torno da origem (Sol).
    L = Σ m (x vy - y vx)
    """
    L = 0.0
    ox, oy = origin

    for b in bodies:
        if b.is_sun or getattr(b, "is_black_hole", False):
            continue
        rx = b.x - ox
        ry = b.y - oy
        L += b.mass * (rx * b.vy - ry * b.vx)

    if player is not None:
        rx = player.x - ox
        ry = player.y - oy
        L += 1.0 * (rx * player.vy - ry * player.vx)

    return L



# ==================== GRAVIDADE VETORIZADA (NumPy) ====================
def source_arrays(bodies):
    """Arrays (x, y, massa, alcance) das fontes gravitacionais. Alcance 1e30 = ilimitado."""
    sx = np.array([b.x for b in bodies], dtype=float)
    sy = np.array([b.y for b in bodies], dtype=float)
    sm = np.array([b.mass for b in bodies], dtype=float)
    sr = np.array([getattr(b, "gravity_range", None) or 1e30 for b in bodies], dtype=float)
    return sx, sy, sm, sr


def accel_points(px, py, src, self_index=None):
    """
    Aceleração gravitacional em N pontos (partículas de teste) causada por M fontes.
    self_index[i] = índice da fonte que é o próprio ponto i (ou -1) para excluir auto-força.
    Mesma lei de compute_gravity_accel (softening + alcance suave), sem loops Python.
    """
    sx, sy, sm, sr = src
    dx = sx[None, :] - px[:, None]
    dy = sy[None, :] - py[:, None]
    d2 = dx * dx + dy * dy + SOFTENING * SOFTENING
    d = np.sqrt(d2)
    f = G * sm[None, :] / d2 / (1.0 + (d / sr[None, :]) ** 4)
    if self_index is not None:
        rows = np.nonzero(self_index >= 0)[0]
        f[rows, self_index[rows]] = 0.0
    return (f * dx / d).sum(axis=1), (f * dy / d).sum(axis=1)


# ==================== COLISÕES ====================
def collide_elastic(a, b, ma, mb, radius_sum, restitution=0.6):
    """
    Colisão entre círculos com conservação de momento e coeficiente de restituição.
    Separa os corpos sobrepostos e devolve a velocidade normal de impacto (0 se não houve colisão).
    """
    dx = b.x - a.x
    dy = b.y - a.y
    d2 = dx * dx + dy * dy
    if d2 >= radius_sum * radius_sum:
        return 0.0
    d = math.sqrt(d2) or 1e-6
    nx, ny = (dx / d, dy / d) if d2 > 0 else (1.0, 0.0)
    total = ma + mb
    overlap = radius_sum - d
    a.x -= nx * overlap * mb / total
    a.y -= ny * overlap * mb / total
    b.x += nx * overlap * ma / total
    b.y += ny * overlap * ma / total
    vn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
    if vn >= 0:
        return 0.0
    j = -(1.0 + restitution) * vn / (1.0 / ma + 1.0 / mb)
    a.vx -= j * nx / ma
    a.vy -= j * ny / ma
    b.vx += j * nx / mb
    b.vy += j * ny / mb
    return -vn


# ==================== PREVISÃO DE TRAJETÓRIA ====================
def predict_trajectory(player, bodies, seconds=PREDICT_SECONDS, step=PREDICT_STEP):
    """
    Simula a nave "à deriva" (sem empuxo) com Velocity Verlet, movendo também os planetas.
    Retorna (caminho, corpo_atingido_ou_None).
    """
    n = len(bodies)
    fixed = np.array([b.is_sun or getattr(b, "is_black_hole", False) for b in bodies] + [False])
    movable = (~fixed).astype(float)
    x = np.array([b.x for b in bodies] + [player.x], dtype=float)
    y = np.array([b.y for b in bodies] + [player.y], dtype=float)
    vx = np.array([b.vx for b in bodies] + [player.vx], dtype=float) * movable
    vy = np.array([b.vy for b in bodies] + [player.vy], dtype=float) * movable
    sm = np.array([b.mass for b in bodies], dtype=float)
    sr = np.array([getattr(b, "gravity_range", None) or 1e30 for b in bodies], dtype=float)
    rad = np.array([b.radius for b in bodies], dtype=float) + PLAYER_RADIUS
    self_index = np.append(np.arange(n), -1)

    def accel():
        ax, ay = accel_points(x, y, (x[:n], y[:n], sm, sr), self_index)
        return ax * movable, ay * movable

    ax, ay = accel()
    path = [(x[n], y[n])]
    hit = None
    for _ in range(int(seconds / step)):
        x += vx * step + 0.5 * ax * step * step
        y += vy * step + 0.5 * ay * step * step
        nax, nay = accel()
        vx += 0.5 * (ax + nax) * step
        vy += 0.5 * (ay + nay) * step
        ax, ay = nax, nay
        path.append((x[n], y[n]))
        d2 = (x[:n] - x[n]) ** 2 + (y[:n] - y[n]) ** 2
        idx = np.nonzero(d2 < rad ** 2)[0]
        if len(idx):
            hit = bodies[int(idx[0])]
            break
    return path, hit
