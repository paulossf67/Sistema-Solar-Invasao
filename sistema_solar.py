#!/usr/bin/env python3
"""
Sistema Solar - Invasão Alienígena
Física orbital realista com Integração de Velocity Verlet
"""

import pygame
import math
import random
import sys
from collections import deque

# ==================== CONFIGURAÇÕES ====================
WIDTH, HEIGHT = 1280, 720
FPS = 60
G = 1200.0          # Constante gravitacional (ajustada para escala do jogo)
SOFTENING = 25.0    # Evita singularidade quando r → 0
MAX_SPEED = 18.0    # Velocidade máxima da nave
THRUST = 0.18       # Aceleração do empuxo
ROT_SPEED = 4.5     # Velocidade de rotação (graus/frame)
BULLET_SPEED = 12.0
BULLET_LIFE = 90    # frames
PLAYER_RADIUS = 12
ALIEN_RADIUS = 14

# Cores
BLACK = (5, 5, 15)
WHITE = (240, 240, 255)
YELLOW = (255, 230, 80)
ORANGE = (255, 160, 40)
RED = (255, 60, 60)
GREEN = (80, 255, 120)
CYAN = (80, 220, 255)
PURPLE = (180, 100, 255)
GRAY = (120, 120, 140)
DARK_PANEL = (10, 12, 28)
BH_DISK = (255, 120, 40)
BH_PHOTON = (255, 220, 150)

BH_GRAVITY_RANGE = 900.0   # alcance efetivo da gravidade dos buracos negros (escala do jogo)
DT_REF = 1.0 / 60.0        # passo de referência: contadores em "frames" são escalados por dt*60


# ==================== CACHES DE RENDER ====================
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


# ==================== FUNÇÃO DE ACELERAÇÃO GRAVITACIONAL ====================
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


# ==================== CORPOS CELESTES ====================
class Body:
    def __init__(self, name, x, y, vx, vy, mass, radius, color, is_sun=False):
        self.name = name
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.mass = mass
        self.radius = radius
        self.color = color
        self.is_sun = is_sun
        self.trail = deque(maxlen=90 if not is_sun else 0)
        # Aceleração atual (para Verlet)
        self.ax = 0.0
        self.ay = 0.0

    def compute_accel(self, bodies):
        """Calcula e armazena a aceleração atual."""
        if self.is_sun:
            self.ax = self.ay = 0.0
            return
        self.ax, self.ay = compute_gravity_accel(self.x, self.y, bodies, exclude=self)

    def drift(self, dt):
        """
        Velocity Verlet, fase 1: x(t+dt) = x(t) + v(t)*dt + 0.5*a(t)*dt²
        (todos os corpos avançam antes de qualquer aceleração ser recalculada).
        """
        if self.is_sun:
            return
        self._ax0, self._ay0 = self.ax, self.ay
        self.x += self.vx * dt + 0.5 * self.ax * dt * dt
        self.y += self.vy * dt + 0.5 * self.ay * dt * dt

    def kick(self, dt, bodies):
        """Fases 2 e 3: a(t+dt) com as novas posições; v += 0.5*(a_old + a_new)*dt."""
        if self.is_sun:
            return
        self.compute_accel(bodies)
        self.vx += 0.5 * (self._ax0 + self.ax) * dt
        self.vy += 0.5 * (self._ay0 + self.ay) * dt
        self.trail.append((self.x, self.y))

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(2, self.radius * zoom)

        # Trilha
        if len(self.trail) > 2:
            points = []
            for tx, ty in self.trail:
                px = (tx - cam_x) * zoom + WIDTH // 2
                py = (ty - cam_y) * zoom + HEIGHT // 2
                if -50 <= px < WIDTH + 50 and -50 <= py < HEIGHT + 50:
                    points.append((px, py))
            if len(points) > 1:
                pygame.draw.lines(screen, self.color, False, points, 1)

        # Corpo
        if self.is_sun:
            for i in range(4, 0, -1):
                glow_r = r + i * 8
                glow_col = (min(255, self.color[0] + 20*i),
                            min(255, self.color[1] + 10*i),
                            max(0, self.color[2] - 20*i))
                blit_glow_circle(screen, glow_col, 28, glow_r, sx, sy)
        pygame.draw.circle(screen, self.color, (int(sx), int(sy)), int(r))

        if zoom > 0.35 and not self.is_sun:
            font = get_font(12)
            text = font.render(self.name, True, (200, 200, 220))
            screen.blit(text, (sx + r + 4, sy - 6))


# ==================== BURACO NEGRO / QUASAR ====================
class BlackHole:
    """
    Buraco negro supermassivo.
    Quando active_quasar=True vira um quasar:
      - Disco de acreção muito mais brilhante
      - Dois jatos relativísticos bipolares
      - Zona de dano / aceleração dentro dos cones dos jatos
      - Radiação intensa
    """
    def __init__(self, name, x, y, mass, horizon_radius=28, active_quasar=False, jet_angle=0.0):
        self.name = name
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.mass = mass
        self.horizon = horizon_radius
        self.radius = horizon_radius
        self.is_sun = False
        self.is_black_hole = True
        self.gravity_range = BH_GRAVITY_RANGE
        self.color = (5, 5, 8)
        self.trail = deque(maxlen=0)
        self.disk_angle = 0.0
        self.swallowed = 0
        self.active_quasar = active_quasar
        self.jet_angle = jet_angle          # orientação dos jatos (graus)
        self.jet_length = 2200              # comprimento visual dos jatos
        self.jet_half_angle = 14.0          # semi-abertura do cone (graus)
        self.jet_particles = []             # partículas dos jatos
        self.luminosity = 0.0
        self.pulse = 0.0
        self.accretion_rate = 1.0           # taxa de acreção relativa (afeta brilho)
        self.disk_particles = []            # partículas do disco de acreção

        self._init_disk_particles()
        if self.active_quasar:
            self._init_jet_particles()

    def _init_disk_particles(self):
        """
        Disco de acreção com partículas em órbitas keplerianas.
        Temperatura (cor) segue perfil aproximado T ∝ r^(-3/4) (disco de Shakura-Sunyaev).
        Rotação diferencial: ω ∝ r^(-3/2).
        """
        self.disk_particles = []
        n_particles = 90 if self.active_quasar else 55
        r_in = self.horizon * 1.6
        r_out = self.horizon * (6.5 if self.active_quasar else 5.0)

        for i in range(n_particles):
            # Distribuição radial (mais partículas no centro)
            t = i / n_particles
            r = r_in + (r_out - r_in) * (t ** 0.7)
            angle = random.uniform(0, 360)
            # Velocidade angular kepleriana aproximada (escala visual)
            omega = 180.0 * (r_in / r) ** 1.5   # graus por segundo (visual)
            # Temperatura relativa → cor
            temp = (r_in / r) ** 0.75           # perfil T ∝ r^{-3/4}
            self.disk_particles.append({
                "r": r,
                "angle": angle,
                "omega": omega,
                "temp": temp,
                "size": random.uniform(1.2, 2.8),
                "phase": random.uniform(0, 2 * math.pi),
            })

    def _init_jet_particles(self):
        """
        Jatos relativísticos com:
        - Núcleo colimado + envelope mais largo
        - Filamentos helicoidais
        - Nós de choque (bright knots)
        - Assimetría de brilho (efeito Doppler visual)
        """
        self.jet_particles = []
        self.jet_knots = []          # nós de choque brilhantes
        self.jet_length = 2600

        for direction in (1, -1):    # jato + contra-jato
            # Núcleo do jato (partículas rápidas e colimadas)
            for _ in range(55):
                self.jet_particles.append({
                    "dist": random.uniform(self.horizon * 1.8, self.jet_length),
                    "side": direction,
                    "spread": random.uniform(-0.35, 0.35),   # bem colimado
                    "speed": random.uniform(14.0, 26.0),
                    "size": random.uniform(1.8, 3.5),
                    "brightness": random.uniform(0.7, 1.0),
                    "layer": "core",
                    "helix": random.uniform(0, 2 * math.pi),
                })
            # Envelope / sheath (mais largo e lento)
            for _ in range(35):
                self.jet_particles.append({
                    "dist": random.uniform(self.horizon * 2.5, self.jet_length * 0.9),
                    "side": direction,
                    "spread": random.uniform(-1.1, 1.1),
                    "speed": random.uniform(7.0, 13.0),
                    "size": random.uniform(2.5, 5.5),
                    "brightness": random.uniform(0.35, 0.65),
                    "layer": "sheath",
                    "helix": random.uniform(0, 2 * math.pi),
                })

            # Nós de choque (bright knots) — características reais de jatos de AGN
            for k in range(4):
                self.jet_knots.append({
                    "dist": 400 + k * 550 + random.uniform(-80, 80),
                    "side": direction,
                    "size": random.uniform(14, 22),
                    "phase": random.uniform(0, 2 * math.pi),
                    "brightness": random.uniform(0.75, 1.0),
                })

    def _temp_to_color(self, temp, luminosity=1.0):
        """Converte temperatura relativa (0–1+) em cor de corpo negro aproximada."""
        t = max(0.05, min(1.4, temp * luminosity))
        if t > 0.85:          # muito quente → branco-azulado
            r = 255
            g = 255
            b = int(200 + 55 * (t - 0.85) / 0.55)
        elif t > 0.55:        # quente → amarelo-branco
            r = 255
            g = int(200 + 55 * (t - 0.55) / 0.3)
            b = int(80 + 120 * (t - 0.55) / 0.3)
        elif t > 0.3:         # médio → laranja
            r = 255
            g = int(100 + 100 * (t - 0.3) / 0.25)
            b = 30
        else:                 # frio → vermelho-escuro
            r = int(180 + 75 * t / 0.3)
            g = int(40 + 60 * t / 0.3)
            b = 15
        return (r, g, b)

    def compute_accel(self, bodies):
        self.ax = self.ay = 0.0

    def drift(self, dt):
        pass   # buracos negros são fixos

    def kick(self, dt, bodies):
        self.animate(dt)

    def animate(self, dt):
        self.disk_angle = (self.disk_angle + (2.5 if self.active_quasar else 1.2) * dt * 60) % 360
        self.pulse = (self.pulse + dt * 3.0) % (2 * math.pi)

        # Rotação diferencial do disco (Kepleriana)
        for p in self.disk_particles:
            p["angle"] = (p["angle"] + p["omega"] * dt) % 360
            # Pequena variação de brilho (turbulência visual)
            p["phase"] += dt * 4.0

        if self.active_quasar:
            self.luminosity = 0.65 + 0.35 * math.sin(self.pulse)
            self.accretion_rate = 0.8 + 0.4 * math.sin(self.pulse * 0.7)

            for p in self.jet_particles:
                p["dist"] += p["speed"] * dt * 60
                p["helix"] += dt * (3.5 if p["layer"] == "core" else 1.8)
                if p["dist"] > self.jet_length:
                    p["dist"] = self.horizon * 1.8
                    if p["layer"] == "core":
                        p["spread"] = random.uniform(-0.35, 0.35)
                    else:
                        p["spread"] = random.uniform(-1.1, 1.1)
                    p["brightness"] = random.uniform(0.5, 1.0)

            # Nós de choque oscilam levemente e avançam devagar
            for knot in self.jet_knots:
                knot["phase"] += dt * 2.2
                knot["dist"] += 1.8 * dt * 60
                if knot["dist"] > self.jet_length * 0.95:
                    knot["dist"] = self.horizon * 3.5
                    knot["brightness"] = random.uniform(0.75, 1.0)
        else:
            self.luminosity = 0.4 + 0.15 * math.sin(self.pulse * 0.5)
            self.accretion_rate = 0.5

    def swallows(self, obj_x, obj_y, obj_radius=0):
        dx = obj_x - self.x
        dy = obj_y - self.y
        return (dx*dx + dy*dy) < (self.horizon + obj_radius)**2

    def in_jet_cone(self, obj_x, obj_y):
        """Verifica se o ponto está dentro de um dos cones de jato."""
        if not self.active_quasar:
            return False, 0.0

        dx = obj_x - self.x
        dy = obj_y - self.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < self.horizon * 1.5 or dist > self.jet_length:
            return False, 0.0

        # Ângulo do objeto em relação ao eixo do jato
        obj_angle = math.degrees(math.atan2(dy, dx))
        for sign in (0, 180):               # dois jatos opostos
            jet_dir = (self.jet_angle + sign) % 360
            diff = abs((obj_angle - jet_dir + 180) % 360 - 180)
            if diff < self.jet_half_angle:
                # Intensidade cai com a distância e com o desvio angular
                intensity = (1.0 - dist / self.jet_length) * (1.0 - diff / self.jet_half_angle)
                return True, max(0.0, intensity)
        return False, 0.0

    def apply_jet_force(self, obj, dt):
        """Aplica aceleração e dano se o objeto estiver no jato."""
        inside, intensity = self.in_jet_cone(obj.x, obj.y)
        if not inside:
            return 0.0

        # Direção radial para fora (jato empurra)
        dx = obj.x - self.x
        dy = obj.y - self.y
        dist = math.sqrt(dx*dx + dy*dy) + 1e-6
        force = 2.8 * intensity
        obj.vx += (dx / dist) * force * dt * 60
        obj.vy += (dy / dist) * force * dt * 60
        return intensity   # retorna intensidade para aplicar dano

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        h = max(4, self.horizon * zoom)

        # ========== JATOS RELATIVÍSTICOS ==========
        if self.active_quasar:
            # 1) Feixe difuso de fundo (glow do jato)
            for sign in (0, 180):
                ang = math.radians(self.jet_angle + sign)
                # Doppler visual: jato "aproximando" (sign==0) mais brilhante
                doppler = 1.25 if sign == 0 else 0.55
                for step in range(12):
                    t = step / 11.0
                    dist = self.horizon * 2 + t * self.jet_length * 0.92
                    width = h * (0.8 + t * 2.8)
                    px = self.x + math.cos(ang) * dist
                    py = self.y + math.sin(ang) * dist
                    psx = (px - cam_x) * zoom + WIDTH // 2
                    psy = (py - cam_y) * zoom + HEIGHT // 2
                    alpha = int(18 * (1.0 - t) * doppler * self.luminosity)
                    if alpha > 4 and -40 < psx < WIDTH + 40:
                        col = (120, 60, 220) if sign == 0 else (80, 40, 140)
                        blit_glow_circle(screen, col, alpha, width, psx, psy)

            # 2) Partículas (núcleo colimado + envelope)
            for p in self.jet_particles:
                ang = math.radians(self.jet_angle + (0 if p["side"] > 0 else 180))
                perp = ang + math.pi / 2

                # Espalhamento + componente helicoidal (filamentos)
                helix_amp = h * 0.45 if p["layer"] == "core" else h * 0.9
                helix_off = math.sin(p["helix"]) * helix_amp * (p["dist"] / self.jet_length) ** 0.6
                spread_px = p["spread"] * h * 1.1 * (0.3 + 0.7 * p["dist"] / self.jet_length)

                px = self.x + math.cos(ang) * p["dist"] + math.cos(perp) * (spread_px + helix_off)
                py = self.y + math.sin(ang) * p["dist"] + math.sin(perp) * (spread_px + helix_off)

                psx = (px - cam_x) * zoom + WIDTH // 2
                psy = (py - cam_y) * zoom + HEIGHT // 2

                if -40 < psx < WIDTH + 40 and -40 < psy < HEIGHT + 40:
                    # Doppler: jato principal mais brilhante
                    doppler = 1.3 if p["side"] > 0 else 0.6
                    b = p["brightness"] * self.luminosity * doppler

                    if p["layer"] == "core":
                        # Núcleo: branco-azulado / magenta
                        r = int(min(255, 160 + 95 * b))
                        g = int(min(255, 100 + 80 * b))
                        bl = int(min(255, 220 + 35 * b))
                        color = (r, g, bl)
                    else:
                        # Envelope: roxo mais suave
                        r = int(min(255, 90 + 70 * b))
                        g = int(min(255, 40 + 40 * b))
                        bl = int(min(255, 180 + 50 * b))
                        color = (r, g, bl)

                    size = max(1, p["size"] * zoom * (0.55 + 0.45 * b))
                    pygame.draw.circle(screen, color, (int(psx), int(psy)), int(size))

            # 3) Nós de choque (bright knots) — estrutura real de jatos de AGN
            for knot in self.jet_knots:
                ang = math.radians(self.jet_angle + (0 if knot["side"] > 0 else 180))
                px = self.x + math.cos(ang) * knot["dist"]
                py = self.y + math.sin(ang) * knot["dist"]
                psx = (px - cam_x) * zoom + WIDTH // 2
                psy = (py - cam_y) * zoom + HEIGHT // 2

                if -50 < psx < WIDTH + 50 and -50 < psy < HEIGHT + 50:
                    doppler = 1.35 if knot["side"] > 0 else 0.5
                    pulse = 0.75 + 0.25 * math.sin(knot["phase"])
                    b = knot["brightness"] * self.luminosity * doppler * pulse
                    radius = max(3, knot["size"] * zoom * (0.6 + 0.4 * b))

                    # Halo do nó
                    blit_glow_circle(screen, (180, 100, 255), 50 * b, radius * 2, psx, psy)
                    # Núcleo brilhante
                    pygame.draw.circle(screen, (255, 220, 255), (int(psx), int(psy)), int(radius * 0.55))
                    pygame.draw.circle(screen, (220, 160, 255), (int(psx), int(psy)), int(radius))

            # 4) Eixo central fino (guia)
            for sign in (0, 180):
                ang = math.radians(self.jet_angle + sign)
                ex = self.x + math.cos(ang) * self.jet_length * 0.98
                ey = self.y + math.sin(ang) * self.jet_length * 0.98
                esx = (ex - cam_x) * zoom + WIDTH // 2
                esy = (ey - cam_y) * zoom + HEIGHT // 2
                col = (160, 100, 255) if sign == 0 else (90, 50, 140)
                pygame.draw.line(screen, col, (sx, sy), (esx, esy), 1)

        # ========== DISCO DE ACREÇÃO (partículas + camadas) ==========
        # 1) Camadas de fundo (nebulosidade do disco)
        disk_w = h * (5.0 if self.active_quasar else 4.2)
        disk_h = h * (1.35 if self.active_quasar else 1.15)
        layers = 6 if self.active_quasar else 4
        for i in range(layers, 0, -1):
            alpha = int((20 + i * 14) * (0.6 + 0.4 * self.luminosity))
            scale = 1.0 + i * 0.13
            base_temp = 0.9 - i * 0.12
            color = self._temp_to_color(base_temp, self.luminosity)
            # Inclinação visual leve
            offset_x = math.sin(math.radians(self.disk_angle * 0.3 + i * 20)) * h * 0.12
            blit_glow_ellipse(screen, color, alpha, disk_w * 2 * scale, disk_h * 2 * scale,
                              max(1, int(2.5 * zoom)), sx - disk_w * scale + offset_x, sy - disk_h * scale)

        # 2) Partículas do disco (rotação diferencial + gradiente de temperatura)
        for p in self.disk_particles:
            ang = math.radians(p["angle"])
            # Órbita elíptica projetada (disco inclinado)
            px = self.x + math.cos(ang) * p["r"]
            py = self.y + math.sin(ang) * p["r"] * 0.38   # achatamento visual
            psx = (px - cam_x) * zoom + WIDTH // 2
            psy = (py - cam_y) * zoom + HEIGHT // 2

            if -20 < psx < WIDTH + 20 and -20 < psy < HEIGHT + 20:
                # Turbulência de brilho
                flicker = 0.85 + 0.15 * math.sin(p["phase"])
                col = self._temp_to_color(p["temp"] * flicker, self.luminosity * self.accretion_rate)
                size = max(1, p["size"] * zoom * (0.7 + 0.3 * p["temp"]))
                pygame.draw.circle(screen, col, (int(psx), int(psy)), int(size))

        # 3) Anel de fótons (mais brilhante no quasar)
        photon_col = (255, 240, 180) if self.active_quasar else BH_PHOTON
        pygame.draw.circle(screen, photon_col, (int(sx), int(sy)), int(h * 1.65), max(1, int(2.5 * zoom)))
        pygame.draw.circle(screen, (255, 210, 120), (int(sx), int(sy)), int(h * 1.4), 1)

        # 4) Horizonte de eventos
        pygame.draw.circle(screen, (0, 0, 0), (int(sx), int(sy)), int(h))
        rim = (40, 15, 50) if self.active_quasar else (20, 10, 30)
        pygame.draw.circle(screen, rim, (int(sx), int(sy)), int(h), max(1, int(2 * zoom)))

        # Rótulo
        if zoom > 0.20:
            font = get_font(13)
            label_color = (255, 190, 90) if self.active_quasar else (220, 160, 100)
            screen.blit(font.render(self.name, True, label_color), (sx + h + 6, sy - 14))
            if self.active_quasar:
                info = f"QUASAR  Ṁ≈{self.accretion_rate:.2f}"
                info_col = (255, 120, 255)
            else:
                info = f"M ≈ {self.mass/1000:.0f}k"
                info_col = (160, 120, 80)
            screen.blit(font.render(info, True, info_col), (sx + h + 6, sy + 2))
            # Indicador de temperatura do disco
            temp_label = font.render("Disco: T∝r⁻¾", True, (140, 140, 160))
            screen.blit(temp_label, (sx + h + 6, sy + 18))


# ==================== NAVE DO JOGADOR ====================
class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.angle = -90.0
        self.radius = PLAYER_RADIUS
        self.mass = 1.0
        self.lives = 3
        self.score = 0
        self.invincible = 0
        self.thrusting = False
        self.thrust_ax = 0.0
        self.thrust_ay = 0.0
        self.trail = deque(maxlen=30)

    def rotate(self, direction, dt):
        self.angle += direction * ROT_SPEED * dt * 60

    def apply_thrust(self, dt):
        """Calcula aceleração de empuxo (não aplica ainda — entra no Verlet)."""
        rad = math.radians(self.angle)
        self.thrust_ax = math.cos(rad) * THRUST * 60   # *60 para compensar dt≈1/60
        self.thrust_ay = math.sin(rad) * THRUST * 60
        self.thrusting = True

    def compute_accel(self, bodies):
        """Aceleração total = gravidade + empuxo."""
        gx, gy = compute_gravity_accel(self.x, self.y, bodies)
        self.ax = gx + self.thrust_ax
        self.ay = gy + self.thrust_ay

    def drift(self, dt):
        self._ax0, self._ay0 = self.ax, self.ay
        self.x += self.vx * dt + 0.5 * self.ax * dt * dt
        self.y += self.vy * dt + 0.5 * self.ay * dt * dt

    def kick(self, dt, bodies):
        """Velocity Verlet (fases 2 e 3) com empuxo incluído na aceleração."""
        self.compute_accel(bodies)
        self.vx += 0.5 * (self._ax0 + self.ax) * dt
        self.vy += 0.5 * (self._ay0 + self.ay) * dt

        # Limita velocidade máxima (opcional, para jogabilidade)
        speed = math.sqrt(self.vx*self.vx + self.vy*self.vy)
        if speed > MAX_SPEED:
            self.vx = self.vx / speed * MAX_SPEED
            self.vy = self.vy / speed * MAX_SPEED

        self.trail.append((self.x, self.y))
        if self.invincible > 0:
            self.invincible = max(0.0, self.invincible - dt * 60)

        # Reseta empuxo (só vale enquanto a tecla está pressionada)
        self.thrust_ax = 0.0
        self.thrust_ay = 0.0
        self.thrusting = False

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2

        # Trilha de foguete
        if len(self.trail) > 2 and self.thrusting:
            for i, (tx, ty) in enumerate(list(self.trail)[-10:]):
                px = (tx - cam_x) * zoom + WIDTH // 2
                py = (ty - cam_y) * zoom + HEIGHT // 2
                pygame.draw.circle(screen, (255, 160 + i*8, 40), (int(px), int(py)), 3)

        # Nave (triângulo)
        rad = math.radians(self.angle)
        size = self.radius * zoom * 1.8
        points = [
            (sx + math.cos(rad) * size, sy + math.sin(rad) * size),
            (sx + math.cos(rad + 2.4) * size * 0.7, sy + math.sin(rad + 2.4) * size * 0.7),
            (sx + math.cos(rad - 2.4) * size * 0.7, sy + math.sin(rad - 2.4) * size * 0.7),
        ]

        color = CYAN if self.invincible <= 0 or self.invincible % 10 < 5 else (100, 100, 120)
        pygame.draw.polygon(screen, color, points)
        pygame.draw.polygon(screen, WHITE, points, 1)

        # Chama do motor
        if self.thrusting:
            flame = [
                (sx - math.cos(rad) * size * 0.3, sy - math.sin(rad) * size * 0.3),
                (sx + math.cos(rad + 2.8) * size * 0.5, sy + math.sin(rad + 2.8) * size * 0.5),
                (sx + math.cos(rad - 2.8) * size * 0.5, sy + math.sin(rad - 2.8) * size * 0.5),
            ]
            pygame.draw.polygon(screen, ORANGE, flame)


# ==================== TIRO ====================
class Bullet:
    def __init__(self, x, y, angle, owner="player"):
        self.x = x
        self.y = y
        rad = math.radians(angle)
        self.vx = math.cos(rad) * BULLET_SPEED
        self.vy = math.sin(rad) * BULLET_SPEED
        self.life = BULLET_LIFE
        self.owner = owner
        self.radius = 3

    def update(self, dt):
        # Tiros usam Euler simples (rápidos e de vida curta)
        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60
        self.life -= dt * 60

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        color = CYAN if self.owner == "player" else RED
        pygame.draw.circle(screen, color, (int(sx), int(sy)), max(2, int(self.radius * zoom)))


# ==================== ALIEN ====================
class Alien:
    def __init__(self, x, y, target=None):
        self.x = x
        self.y = y
        angle = random.uniform(0, 360)
        speed = random.uniform(1.5, 3.5)
        self.vx = math.cos(math.radians(angle)) * speed
        self.vy = math.sin(math.radians(angle)) * speed
        self.ax = 0.0
        self.ay = 0.0
        self.radius = ALIEN_RADIUS
        self.mass = 0.5
        self.hp = 2
        self.shoot_cooldown = random.randint(40, 100)
        self.angle = 0
        self.target = target
        self.ai_ax = 0.0
        self.ai_ay = 0.0

    def compute_accel(self, bodies, player):
        gx, gy = compute_gravity_accel(self.x, self.y, bodies, mass_scale=0.75)

        # IA: pequeno empuxo em direção ao jogador
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            dist = math.sqrt(dx*dx + dy*dy) + 1.0
            self.ai_ax = (dx / dist) * 0.035 * 60
            self.ai_ay = (dy / dist) * 0.035 * 60
            self.angle = math.degrees(math.atan2(dy, dx))
        else:
            self.ai_ax = self.ai_ay = 0.0

        self.ax = gx + self.ai_ax
        self.ay = gy + self.ai_ay

    def drift(self, dt):
        self._ax0, self._ay0 = self.ax, self.ay
        self.x += self.vx * dt + 0.5 * self.ax * dt * dt
        self.y += self.vy * dt + 0.5 * self.ay * dt * dt

    def kick(self, dt, bodies, player, bullets):
        self.compute_accel(bodies, player)
        self.vx += 0.5 * (self._ax0 + self.ax) * dt
        self.vy += 0.5 * (self._ay0 + self.ay) * dt

        # Limita velocidade
        speed = math.sqrt(self.vx*self.vx + self.vy*self.vy)
        if speed > 8.0:
            self.vx = self.vx / speed * 8.0
            self.vy = self.vy / speed * 8.0

        # Tiro
        self.shoot_cooldown -= dt * 60
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            dist = math.sqrt(dx*dx + dy*dy)
            if self.shoot_cooldown <= 0 and dist < 450:
                bullets.append(Bullet(self.x, self.y, self.angle, owner="alien"))
                self.shoot_cooldown = random.randint(50, 110)

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(4, self.radius * zoom)

        pygame.draw.circle(screen, PURPLE, (int(sx), int(sy)), int(r))
        pygame.draw.circle(screen, (220, 150, 255), (int(sx), int(sy)), int(r * 0.6))
        pygame.draw.circle(screen, RED, (int(sx - r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))
        pygame.draw.circle(screen, RED, (int(sx + r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))


# ==================== JOGO PRINCIPAL ====================
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sistema Solar — Invasão Alienígena | Verlet + Quasar Ativo")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = get_font(18)
        self.big_font = get_font(36, bold=True)
        self.small_font = get_font(14)
        rng = random.Random(42)   # estrelas fixas de fundo (geradas uma única vez)
        self.stars = [(rng.randint(-3000, 3000), rng.randint(-3000, 3000), rng.randint(90, 255))
                      for _ in range(130)]
        self.reset()

    def reset(self):
        self.bodies = [
            Body("Sol", 0, 0, 0, 0, 8000, 45, YELLOW, is_sun=True)
        ]

        planets_data = [
            ("Mercúrio", 180,  8,  6,  (180, 160, 140)),
            ("Vênus",    260, 18,  9,  (230, 190, 100)),
            ("Terra",    360, 22, 10,  (70, 140, 255)),
            ("Marte",    480, 12,  7,  (220, 100, 60)),
            ("Júpiter",  720, 90, 22,  (220, 180, 120)),
            ("Saturno",  920, 55, 18,  (230, 210, 150)),
            ("Urano",   1120, 30, 14,  (120, 220, 230)),
            ("Netuno",  1320, 28, 13,  (60, 100, 255)),
        ]

        for name, r, mass, rad, color in planets_data:
            theta = random.uniform(0, 2 * math.pi)
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            v = math.sqrt(G * 8000 / r) * 0.995
            vx = -v * math.sin(theta)
            vy =  v * math.cos(theta)
            body = Body(name, x, y, vx, vy, mass, rad, color)
            body.compute_accel(self.bodies)  # aceleração inicial
            self.bodies.append(body)

        # === Buracos negros supermassivos / Quasar ===
        # Sagitarius A* — relativamente quieto
        bh1 = BlackHole("Sagitarius A*", 2800, -900, mass=45000, horizon_radius=32,
                        active_quasar=False)
        # M87* — quasar ativo com jatos relativísticos (inspirado no jato real de M87)
        bh2 = BlackHole("M87* (Quasar)", -3400, 1800, mass=95000, horizon_radius=52,
                        active_quasar=True, jet_angle=35.0)
        self.bodies.append(bh1)
        self.bodies.append(bh2)

        # Recomputa acelerações com todos os corpos (incluindo BHs)
        for body in self.bodies:
            if hasattr(body, "compute_accel"):
                body.compute_accel(self.bodies)

        # Jogador perto da Terra
        terra = next(b for b in self.bodies if b.name == "Terra")
        self.player = Player(terra.x + 55, terra.y)
        self.player.vx = terra.vx
        self.player.vy = terra.vy - 1.2
        self.player.compute_accel(self.bodies)

        self.bullets = []
        self.aliens = []
        self.wave = 1
        self.wave_timer = 180.0
        self.shoot_cd = 0.0
        self.game_over = False
        self.paused = False
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.zoom = 0.55

        # Histórico para gráficos de conservação
        self.energy_history = deque(maxlen=300)   # ~5 segundos a 60 fps
        self.L_history = deque(maxlen=300)
        self.initial_energy = None
        self.initial_L = None
        self.n_solar_bodies = None   # muda quando um planeta é engolido → rebaseia E e L
        self.show_physics_panel = True

        self.spawn_wave()

    def spawn_wave(self):
        n = 3 + self.wave * 2
        for _ in range(n):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(1600, 2200)
            x = dist * math.cos(angle)
            y = dist * math.sin(angle)
            alien = Alien(x, y, self.player)
            alien.compute_accel(self.bodies, self.player)
            self.aliens.append(alien)

    def handle_input(self, dt):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player.rotate(-1, dt)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player.rotate(1, dt)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.player.apply_thrust(dt)

        if keys[pygame.K_SPACE]:
            if self.shoot_cd <= 0:
                self.bullets.append(Bullet(self.player.x, self.player.y, self.player.angle))
                self.shoot_cd = 12.0
        if self.shoot_cd > 0:
            self.shoot_cd -= dt * 60

        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS]:
            self.zoom = min(1.8, self.zoom + 0.012 * dt * 60)
        if keys[pygame.K_MINUS]:
            self.zoom = max(0.12, self.zoom - 0.012 * dt * 60)

    def update(self, dt):
        if self.game_over or self.paused:
            return

        # === Velocity Verlet em duas fases para todos os corpos ===
        # 1) todos avançam a posição com a aceleração antiga;
        # 2) as acelerações são recalculadas com o estado novo e as velocidades atualizadas.
        movers = self.bodies + [self.player] + self.aliens
        for m in movers:
            m.drift(dt)
        for body in self.bodies:
            body.kick(dt, self.bodies)
        self.player.kick(dt, self.bodies)

        # Câmera suave (independente do FPS)
        k = 1.0 - (1.0 - 0.09) ** (dt * 60)
        self.cam_x += (self.player.x - self.cam_x) * k
        self.cam_y += (self.player.y - self.cam_y) * k

        # --- Horizonte de eventos + jatos de quasar ---
        black_holes = [b for b in self.bodies if getattr(b, "is_black_hole", False)]
        for bh in black_holes:
            # Jogador engolido
            if bh.swallows(self.player.x, self.player.y, self.player.radius):
                self.player.lives = 0
                self.game_over = True
                bh.swallowed += 1

            # Jato do quasar afeta o jogador
            if bh.active_quasar and self.player.invincible <= 0:
                intensity = bh.apply_jet_force(self.player, dt)
                if intensity > 0.15:
                    # Dano por radiação / partículas relativísticas
                    self.player.lives -= 1
                    self.player.invincible = 75
                    if self.player.lives <= 0:
                        self.game_over = True

            # Aliens
            for alien in self.aliens[:]:
                if bh.swallows(alien.x, alien.y, alien.radius):
                    self.aliens.remove(alien)
                    bh.swallowed += 1
                    self.player.score += 50
                    continue
                # Jato também empurra / danifica aliens
                if bh.active_quasar:
                    intensity = bh.apply_jet_force(alien, dt)
                    if intensity > 0.25:
                        alien.hp -= 1
                        if alien.hp <= 0:
                            self.aliens.remove(alien)
                            self.player.score += 80  # bônus por destruir com o jato

            # Tiros engolidos
            for b in self.bullets[:]:
                if bh.swallows(b.x, b.y, b.radius):
                    self.bullets.remove(b)

            # Planetas engolidos
            for body in self.bodies[:]:
                if getattr(body, "is_black_hole", False) or body.is_sun:
                    continue
                if bh.swallows(body.x, body.y, body.radius):
                    self.bodies.remove(body)
                    bh.swallowed += 1

        # Aliens
        for alien in self.aliens[:]:
            alien.kick(dt, self.bodies, self.player, self.bullets)

            # Colisão alien × jogador
            if self.player.invincible <= 0:
                dx = alien.x - self.player.x
                dy = alien.y - self.player.y
                if dx*dx + dy*dy < (alien.radius + self.player.radius)**2:
                    self.player.lives -= 1
                    self.player.invincible = 90
                    alien.vx += dx * 0.08
                    alien.vy += dy * 0.08
                    if self.player.lives <= 0:
                        self.game_over = True

        # Tiros
        for b in self.bullets[:]:
            b.update(dt)
            if b.life <= 0:
                self.bullets.remove(b)
                continue

            if b.owner == "player":
                for alien in self.aliens[:]:
                    dx = alien.x - b.x
                    dy = alien.y - b.y
                    if dx*dx + dy*dy < (alien.radius + b.radius)**2:
                        alien.hp -= 1
                        if b in self.bullets:
                            self.bullets.remove(b)
                        if alien.hp <= 0:
                            self.aliens.remove(alien)
                            self.player.score += 100 * self.wave
                        break
            else:
                if self.player.invincible <= 0:
                    dx = self.player.x - b.x
                    dy = self.player.y - b.y
                    if dx*dx + dy*dy < (self.player.radius + b.radius)**2:
                        self.player.lives -= 1
                        self.player.invincible = 90
                        if b in self.bullets:
                            self.bullets.remove(b)
                        if self.player.lives <= 0:
                            self.game_over = True

        # Colisão com planetas / Sol
        for body in self.bodies:
            dx = body.x - self.player.x
            dy = body.y - self.player.y
            min_dist = body.radius + self.player.radius
            if dx*dx + dy*dy < min_dist*min_dist:
                if body.is_sun:
                    self.player.lives = 0
                    self.game_over = True
                else:
                    if self.player.invincible <= 0:
                        self.player.lives -= 1
                        self.player.invincible = 60
                        dist = math.sqrt(dx*dx + dy*dy) + 0.1
                        self.player.vx -= (dx / dist) * 5
                        self.player.vy -= (dy / dist) * 5
                        if self.player.lives <= 0:
                            self.game_over = True

        # Próxima onda
        if not self.aliens:
            self.wave_timer -= dt * 60
            if self.wave_timer <= 0:
                self.wave += 1
                self.spawn_wave()
                self.wave_timer = 120.0

        # === Monitoramento de conservação ===
        E, K, U = compute_system_energy(self.bodies, self.player)
        L = compute_angular_momentum(self.bodies, self.player)

        n_solar = sum(1 for b in self.bodies if not getattr(b, "is_black_hole", False))
        if self.initial_energy is None or n_solar != self.n_solar_bodies:
            # Novo baseline (início ou planeta engolido — o sistema mudou de fato)
            self.n_solar_bodies = n_solar
            self.initial_energy = E
            self.initial_L = L
            self.energy_history.clear()
            self.L_history.clear()

        self.energy_history.append(E)
        self.L_history.append(L)

    def draw_physics_panel(self):
        """Painel lateral com energia, momento angular e gráficos."""
        if not self.show_physics_panel:
            return

        panel_w, panel_h = 280, 210
        panel_x = WIDTH - panel_w - 12
        panel_y = 90

        # Fundo
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((8, 10, 25, 210))
        pygame.draw.rect(panel, (60, 80, 140), (0, 0, panel_w, panel_h), 1)
        self.screen.blit(panel, (panel_x, panel_y))

        # Valores atuais
        E = self.energy_history[-1] if self.energy_history else 0.0
        L = self.L_history[-1] if self.L_history else 0.0
        E0 = self.initial_energy if self.initial_energy is not None else E
        L0 = self.initial_L if self.initial_L is not None else L

        dE = E - E0
        dL = L - L0
        rel_E = (dE / abs(E0) * 100) if abs(E0) > 1e-6 else 0.0
        rel_L = (dL / abs(L0) * 100) if abs(L0) > 1e-6 else 0.0

        title = self.small_font.render("Sol+planetas+nave (Verlet)", True, CYAN)
        self.screen.blit(title, (panel_x + 10, panel_y + 8))

        # Energia
        e_col = GREEN if abs(rel_E) < 1.5 else (ORANGE if abs(rel_E) < 5 else RED)
        self.screen.blit(self.small_font.render(f"Energia E : {E:,.0f}", True, WHITE),
                         (panel_x + 10, panel_y + 30))
        self.screen.blit(self.small_font.render(f"ΔE        : {dE:+.1f}  ({rel_E:+.2f}%)", True, e_col),
                         (panel_x + 10, panel_y + 48))

        # Momento angular
        l_col = GREEN if abs(rel_L) < 1.5 else (ORANGE if abs(rel_L) < 5 else RED)
        self.screen.blit(self.small_font.render(f"Momento L : {L:,.0f}", True, WHITE),
                         (panel_x + 10, panel_y + 72))
        self.screen.blit(self.small_font.render(f"ΔL        : {dL:+.1f}  ({rel_L:+.2f}%)", True, l_col),
                         (panel_x + 10, panel_y + 90))

        # Gráfico de energia (últimos ~5 s)
        graph_x = panel_x + 10
        graph_y = panel_y + 118
        graph_w = panel_w - 20
        graph_h = 80

        pygame.draw.rect(self.screen, (15, 18, 35), (graph_x, graph_y, graph_w, graph_h))
        pygame.draw.rect(self.screen, (50, 60, 100), (graph_x, graph_y, graph_w, graph_h), 1)

        if len(self.energy_history) > 2:
            vals = list(self.energy_history)
            mn, mx = min(vals), max(vals)
            span = max(mx - mn, abs(E0) * 0.01, 1.0)  # evita divisão por zero

            points = []
            for i, val in enumerate(vals):
                px = graph_x + int(i / (len(vals) - 1) * (graph_w - 1))
                py = graph_y + graph_h - 4 - int((val - mn) / span * (graph_h - 8))
                points.append((px, py))

            if len(points) > 1:
                pygame.draw.lines(self.screen, CYAN, False, points, 1)

            # Linha de referência (energia inicial)
            ref_y = graph_y + graph_h - 4 - int((E0 - mn) / span * (graph_h - 8))
            pygame.draw.line(self.screen, (80, 80, 100), (graph_x, ref_y), (graph_x + graph_w, ref_y), 1)

        label = self.small_font.render("E(t) cinza=E₀ (empuxo/jato mudam E)", True, GRAY)
        self.screen.blit(label, (graph_x, graph_y + graph_h + 4))

    def draw_hud(self):
        hud = pygame.Surface((WIDTH, 72), pygame.SRCALPHA)
        hud.fill((0, 0, 20, 170))
        self.screen.blit(hud, (0, 0))

        self.screen.blit(self.font.render(f"Vidas: {self.player.lives}", True, GREEN), (20, 12))
        self.screen.blit(self.font.render(f"Pontos: {self.player.score}", True, CYAN), (20, 40))
        self.screen.blit(self.font.render(f"Onda: {self.wave}", True, ORANGE), (200, 12))

        speed = math.sqrt(self.player.vx**2 + self.player.vy**2)
        self.screen.blit(self.font.render(f"Vel: {speed:.1f}", True, WHITE), (200, 40))

        help1 = self.small_font.render(
            "A/D girar | W empuxo | Espaço atirar | +/- zoom | P pausar | F painel física | R reiniciar",
            True, GRAY)
        self.screen.blit(help1, (360, 16))

        phys = self.small_font.render(
            "Velocity Verlet  •  Newton  •  Quasar ativo (M87*) + jatos relativísticos",
            True, (90, 210, 120))
        self.screen.blit(phys, (360, 42))

        if self.paused:
            txt = self.big_font.render("PAUSADO", True, YELLOW)
            self.screen.blit(txt, (WIDTH//2 - 90, HEIGHT//2 - 20))

        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 190))
            self.screen.blit(overlay, (0, 0))
            self.screen.blit(self.big_font.render("GAME OVER", True, RED), (WIDTH//2 - 110, HEIGHT//2 - 60))
            self.screen.blit(self.font.render(f"Pontuação final: {self.player.score}", True, WHITE),
                             (WIDTH//2 - 110, HEIGHT//2))
            self.screen.blit(self.font.render("Pressione R para reiniciar", True, CYAN),
                             (WIDTH//2 - 130, HEIGHT//2 + 40))

    def draw(self):
        self.screen.fill(BLACK)

        # Estrelas de fundo
        for x, y, b in self.stars:
            sx = (x - self.cam_x * 0.08) % WIDTH
            sy = (y - self.cam_y * 0.08) % HEIGHT
            pygame.draw.circle(self.screen, (b, b, b), (int(sx), int(sy)), 1)

        for body in self.bodies:
            body.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        for b in self.bullets:
            b.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        for alien in self.aliens:
            alien.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        self.player.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        self.draw_hud()
        self.draw_physics_panel()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.033)  # limita dt para estabilidade do Verlet

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_p:
                        self.paused = not self.paused
                    if event.key == pygame.K_r:
                        self.reset()
                    if event.key == pygame.K_f:
                        self.show_physics_panel = not self.show_physics_panel
                    if event.key == pygame.K_ESCAPE:
                        running = False

            if not self.paused and not self.game_over:
                self.handle_input(dt)
                self.update(dt)

            self.draw()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    game = Game()
    game.run()
