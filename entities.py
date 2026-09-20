"""Entidades: corpos, buracos negros, nave, tiros, aliens, partículas e asteroides."""
import math
import random
from collections import deque

import numpy as np
import pygame

from config import *
from physics import *
from render import *


# ==================== CORPOS CELESTES ====================
class Body:
    is_moon = False

    def __init__(self, name, x, y, vx, vy, mass, radius, color, is_sun=False, ring=None):
        self.ring = ring          # (raio_interno, raio_externo) dos anéis, ou None
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

    def record_trail(self):
        if not self.is_sun:
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

        if self.ring:
            for rr, col in ((self.ring[0], (150, 135, 100)), ((self.ring[0] + self.ring[1]) / 2, (190, 170, 125)),
                            (self.ring[1], (130, 118, 90))):
                pygame.draw.circle(screen, col, (int(sx), int(sy)), max(2, int(rr * zoom)), 1)

        # Corpo
        if self.is_sun:
            for i in range(4, 0, -1):
                glow_r = r + i * 8
                glow_col = (min(255, self.color[0] + 20*i),
                            min(255, self.color[1] + 10*i),
                            max(0, self.color[2] - 20*i))
                blit_glow_circle(screen, glow_col, 28, glow_r, sx, sy)
        pygame.draw.circle(screen, self.color, (int(sx), int(sy)), int(r))

        if zoom > 0.35 and not self.is_sun and not (self.is_moon and zoom < 0.9):
            font = get_font(12)
            text = font.render(self.name, True, (200, 200, 220))
            screen.blit(text, (sx + r + 4, sy - 6))


# ==================== LUAS (em trilhos) ====================
class Moon(Body):
    """
    Lua em órbita circular "em trilhos" ao redor de um planeta (estável mesmo com o softening da gravidade).
    Age como corpo sólido e fonte gravitacional fraca, mas não é integrada pelo Verlet.
    """
    is_moon = True

    def __init__(self, name, parent, orbit_r, radius, color, mass, omega, phase):
        super().__init__(name, parent.x, parent.y, parent.vx, parent.vy, mass, radius, color)
        self.parent = parent
        self.orbit_r = orbit_r
        self.omega = omega
        self.phase = phase
        self.trail = deque(maxlen=0)
        self._sync()

    def _sync(self):
        c, s = math.cos(self.phase), math.sin(self.phase)
        self.x = self.parent.x + self.orbit_r * c
        self.y = self.parent.y + self.orbit_r * s
        self.vx = self.parent.vx - self.orbit_r * self.omega * s
        self.vy = self.parent.vy + self.orbit_r * self.omega * c

    def compute_accel(self, bodies):
        self.ax = self.ay = 0.0

    def drift(self, dt):
        pass

    def kick(self, dt, bodies):
        self.phase += self.omega * dt
        self._sync()

    def record_trail(self):
        pass


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
    is_moon = False

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
        self.mass0 = mass
        self.horizon0 = horizon_radius
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

    def absorb(self, amount):
        """Ganha massa: horizonte e alcance gravitacional crescem com a raiz da massa (até BH_MAX_GROWTH×)."""
        self.mass = min(self.mass0 * BH_MAX_GROWTH, self.mass + amount)
        scale = math.sqrt(self.mass / self.mass0)
        self.horizon = self.horizon0 * scale
        self.radius = self.horizon
        self.gravity_range = BH_GRAVITY_RANGE * scale

    def drift(self, dt):
        pass   # buracos negros são fixos

    def record_trail(self):
        pass

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
        self.invincible = 0.0     # "frames" de invencibilidade pós-dano (escala com dt)
        self.shield = 0.0         # segundos de escudo (power-up)
        self.triple = 0.0         # segundos de tiro triplo (power-up)
        self.upgrades = {k: 0 for k in UPGRADE_MAX}
        self.ore = 0.0
        self.fuel = FUEL_MAX
        self.thrusting = False
        self.flame = False        # chama visível no draw (thrusting é zerado no fim do frame)
        self.thrust_ax = 0.0
        self.thrust_ay = 0.0
        self.trail = deque(maxlen=30)

    @property
    def fuel_max(self):
        return FUEL_MAX + 25.0 * self.upgrades["tank"]

    @property
    def shield_time(self):
        return SHIELD_TIME * (1.0 + 0.25 * self.upgrades["shield"])

    @property
    def fire_cooldown(self):
        return 12.0 * 0.85 ** self.upgrades["gun"]

    @property
    def protected(self):
        return self.invincible > 0 or self.shield > 0

    def rotate(self, direction, dt):
        self.angle += direction * ROT_SPEED * dt * 60

    def apply_thrust(self, dt):
        """Calcula aceleração de empuxo (entra no Verlet) e gasta combustível."""
        if self.fuel <= 0:
            return
        rad = math.radians(self.angle)
        power = THRUST * (1.0 + 0.12 * self.upgrades["thrust"]) * 60   # *60: THRUST está em px/frame²
        self.thrust_ax = math.cos(rad) * power
        self.thrust_ay = math.sin(rad) * power
        self.thrusting = True
        self.fuel = max(0.0, self.fuel - FUEL_USE * dt)

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

        speed = math.sqrt(self.vx*self.vx + self.vy*self.vy)
        if speed > MAX_SPEED:
            self.vx = self.vx / speed * MAX_SPEED
            self.vy = self.vy / speed * MAX_SPEED

    def end_frame(self, dt):
        """Estado de fim de frame (independe do número de subpassos físicos)."""
        self.trail.append((self.x, self.y))
        self.invincible = max(0.0, self.invincible - dt * 60)
        self.shield = max(0.0, self.shield - dt)
        self.triple = max(0.0, self.triple - dt)
        self.thrust_ax = 0.0
        self.thrust_ay = 0.0
        self.flame = self.thrusting
        self.thrusting = False

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2

        if len(self.trail) > 2 and self.flame:
            for i, (tx, ty) in enumerate(list(self.trail)[-10:]):
                px = (tx - cam_x) * zoom + WIDTH // 2
                py = (ty - cam_y) * zoom + HEIGHT // 2
                pygame.draw.circle(screen, (255, 160 + i*8, 40), (int(px), int(py)), 3)

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

        if self.shield > 0:
            blink = self.shield > 2 or int(self.shield * 6) % 2 == 0
            if blink:
                blit_glow_circle(screen, CYAN, 60, size * 1.5, sx, sy)
                pygame.draw.circle(screen, CYAN, (int(sx), int(sy)), int(size * 1.5), 1)

        if self.flame:
            flame = [
                (sx - math.cos(rad) * size * 0.3, sy - math.sin(rad) * size * 0.3),
                (sx + math.cos(rad + 2.8) * size * 0.5, sy + math.sin(rad + 2.8) * size * 0.5),
                (sx + math.cos(rad - 2.8) * size * 0.5, sy + math.sin(rad - 2.8) * size * 0.5),
            ]
            pygame.draw.polygon(screen, ORANGE, flame)


# ==================== TIRO ====================
class Bullet:
    """Tiro afetado pela gravidade (curva perto de planetas / buracos negros → estilingue)."""
    def __init__(self, x, y, angle, owner="player", vx0=0.0, vy0=0.0, speed=BULLET_SPEED):
        self.x = x
        self.y = y
        rad = math.radians(angle)
        self.vx = math.cos(rad) * speed + vx0
        self.vy = math.sin(rad) * speed + vy0
        self.life = BULLET_LIFE
        self.owner = owner
        self.radius = 3
        self.tracer = deque(maxlen=7)

    def update(self, dt, bodies):
        ax, ay = compute_gravity_accel(self.x, self.y, bodies)
        self.vx += ax * dt
        self.vy += ay * dt
        self.tracer.append((self.x, self.y))
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt * 60

    def draw(self, screen, cam_x, cam_y, zoom):
        color = CYAN if self.owner == "player" else RED
        pts = [((tx - cam_x) * zoom + WIDTH // 2, (ty - cam_y) * zoom + HEIGHT // 2)
               for tx, ty in self.tracer]
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        pts.append((sx, sy))
        if len(pts) > 1:
            dim = tuple(c // 2 for c in color)
            pygame.draw.lines(screen, dim, False, pts, 1)
        pygame.draw.circle(screen, color, (int(sx), int(sy)), max(2, int(self.radius * zoom)))


# ==================== ALIENS ====================
ALIEN_TYPES = {
    "normal":  dict(hp=2, radius=14, max_speed=160.0, thrust=15.0, color=PURPLE,        cd=(50, 110), range=450, mass=0.5, score=1.0),
    "fast":    dict(hp=1, radius=11, max_speed=260.0, thrust=26.0, color=ORANGE,        cd=(90, 160), range=350, mass=0.4, score=1.3),
    "shooter": dict(hp=2, radius=14, max_speed=120.0, thrust=9.0,  color=GREEN,         cd=(28, 55),  range=700, mass=0.5, score=1.6),
    "tank":    dict(hp=6, radius=22, max_speed=90.0,  thrust=8.0,  color=(200, 60, 90), cd=(60, 100), range=500, mass=1.5, score=3.0),
}


def alien_kinds_for_wave(wave):
    """Tipos disponíveis por onda (progressão de dificuldade)."""
    kinds = ["normal"]
    if wave >= 2:
        kinds.append("fast")
    if wave >= 3:
        kinds.append("shooter")
    if wave >= 4:
        kinds.append("tank")
    return kinds


class Alien:
    def __init__(self, x, y, target=None, kind="normal"):
        spec = ALIEN_TYPES[kind]
        self.kind = kind
        self.spec = spec
        self.x = x
        self.y = y
        angle = random.uniform(0, 360)
        speed = random.uniform(40.0, 90.0)
        self.vx = math.cos(math.radians(angle)) * speed
        self.vy = math.sin(math.radians(angle)) * speed
        self.ax = 0.0
        self.ay = 0.0
        self.radius = spec["radius"]
        self.mass = spec["mass"]
        self.hp = spec["hp"]
        self.shoot_cooldown = float(random.randint(*spec["cd"]))
        self.angle = 0
        self.target = target
        self.ai_ax = 0.0
        self.ai_ay = 0.0

    def compute_accel(self, bodies, player):
        gx, gy = compute_gravity_accel(self.x, self.y, bodies, mass_scale=0.75)

        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            dist = math.sqrt(dx*dx + dy*dy) + 1.0
            # Atiradores mantêm distância; os demais perseguem
            sign = -1.0 if (self.kind == "shooter" and dist < 380) else 1.0
            thrust = self.spec["thrust"]
            self.ai_ax = sign * (dx / dist) * thrust
            self.ai_ay = sign * (dy / dist) * thrust
            self.angle = math.degrees(math.atan2(dy, dx))
        else:
            self.ai_ax = self.ai_ay = 0.0

        self.ax = gx + self.ai_ax
        self.ay = gy + self.ai_ay

    def drift(self, dt):
        self._ax0, self._ay0 = self.ax, self.ay
        self.x += self.vx * dt + 0.5 * self.ax * dt * dt
        self.y += self.vy * dt + 0.5 * self.ay * dt * dt

    def kick(self, dt, bodies, player):
        self.compute_accel(bodies, player)
        self.vx += 0.5 * (self._ax0 + self.ax) * dt
        self.vy += 0.5 * (self._ay0 + self.ay) * dt
        max_speed = self.spec["max_speed"]
        speed = math.sqrt(self.vx*self.vx + self.vy*self.vy)
        if speed > max_speed:
            self.vx = self.vx / speed * max_speed
            self.vy = self.vy / speed * max_speed

    def think(self, dt, player, bullets):
        """IA de tiro (uma vez por frame). Retorna True se atirou."""
        self.shoot_cooldown -= dt * 60
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            if self.shoot_cooldown <= 0 and dx*dx + dy*dy < self.spec["range"] ** 2:
                bullets.append(Bullet(self.x, self.y, self.angle, owner="alien", speed=ALIEN_BULLET_SPEED))
                self.shoot_cooldown = float(random.randint(*self.spec["cd"]))
                return True
        return False

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(4, self.radius * zoom)
        base = self.spec["color"]
        light = tuple(min(255, c + 90) for c in base)

        pygame.draw.circle(screen, base, (int(sx), int(sy)), int(r))
        pygame.draw.circle(screen, light, (int(sx), int(sy)), int(r * 0.6))
        pygame.draw.circle(screen, RED, (int(sx - r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))
        pygame.draw.circle(screen, RED, (int(sx + r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))
        if self.kind == "tank":
            frac = self.hp / self.spec["hp"]
            pygame.draw.rect(screen, (60, 20, 30), (sx - r, sy - r - 8, r * 2, 4))
            pygame.draw.rect(screen, RED, (sx - r, sy - r - 8, r * 2 * frac, 4))


# ==================== PARTÍCULAS DE EXPLOSÃO ====================
class Particle:
    def __init__(self, x, y, vx, vy, life, color, size):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color = color
        self.size = size

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        drag = 0.985 ** (dt * 60)
        self.vx *= drag
        self.vy *= drag
        self.life -= dt

    def draw(self, screen, cam_x, cam_y, zoom):
        f = max(0.0, self.life / self.max_life)
        col = tuple(int(c * (0.25 + 0.75 * f)) for c in self.color)
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        pygame.draw.circle(screen, col, (int(sx), int(sy)), max(1, int(self.size * zoom * (0.4 + 0.6 * f))))


def spawn_explosion(particles, x, y, color, n=18, speed=150.0, size=3.0, vx=0.0, vy=0.0):
    for _ in range(n):
        a = random.uniform(0, 2 * math.pi)
        s = random.uniform(0.2, 1.0) * speed
        c = random.choice([color, WHITE, tuple(min(255, k + 60) for k in color)])
        particles.append(Particle(x, y, vx + math.cos(a) * s, vy + math.sin(a) * s,
                                  random.uniform(0.4, 0.9), c, random.uniform(size * 0.6, size * 1.4)))


# ==================== POWER-UPS ====================
POWERUP_KINDS = {
    "shield": (CYAN,   "E"),
    "triple": (YELLOW, "3"),
    "fuel":   (GREEN,  "F"),
    "life":   (RED,    "+"),
}


class PowerUp:
    def __init__(self, x, y, kind, vx=0.0, vy=0.0):
        self.x, self.y = x, y
        self.vx, self.vy = vx * 0.3, vy * 0.3
        self.kind = kind
        self.life = POWERUP_LIFE
        self.radius = 11
        self.t = random.uniform(0, 6.28)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        self.t += dt * 4

    def draw(self, screen, cam_x, cam_y, zoom):
        if self.life < 4 and int(self.life * 5) % 2 == 0:
            return   # pisca antes de sumir
        color, letter = POWERUP_KINDS[self.kind]
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(6, self.radius * zoom * (1.0 + 0.12 * math.sin(self.t)))
        blit_glow_circle(screen, color, 70, r * 1.9, sx, sy)
        pygame.draw.circle(screen, (10, 12, 28), (int(sx), int(sy)), int(r))
        pygame.draw.circle(screen, color, (int(sx), int(sy)), int(r), 2)
        txt = get_font(13, bold=True).render(letter, True, color)
        screen.blit(txt, (sx - txt.get_width() / 2, sy - txt.get_height() / 2))


# ==================== CINTURÃO DE ASTEROIDES (NumPy) ====================
class AsteroidBelt:
    """Partículas de teste (sem interação mútua) vetorizadas em NumPy, entre Marte e Júpiter."""
    def __init__(self, sun_mass, n=BELT_COUNT):
        rng = np.random.default_rng()
        r = rng.uniform(BELT_R_MIN, BELT_R_MAX, n)
        th = rng.uniform(0, 2 * np.pi, n)
        v = np.sqrt(G * sun_mass / r) * rng.uniform(0.97, 1.03, n)
        self.x = r * np.cos(th)
        self.y = r * np.sin(th)
        self.vx = -v * np.sin(th)
        self.vy = v * np.cos(th)
        self.size = rng.uniform(2.0, 5.5, n)
        self.shade = rng.integers(110, 190, n)
        self.ax = np.zeros(n)
        self.ay = np.zeros(n)
        self._ax0 = self.ax.copy()
        self._ay0 = self.ay.copy()

    def __len__(self):
        return len(self.x)

    def init_accel(self, src):
        self.ax, self.ay = accel_points(self.x, self.y, src)

    def drift(self, dt):
        self._ax0, self._ay0 = self.ax, self.ay
        self.x = self.x + self.vx * dt + 0.5 * self.ax * dt * dt
        self.y = self.y + self.vy * dt + 0.5 * self.ay * dt * dt

    def kick(self, dt, src):
        self.ax, self.ay = accel_points(self.x, self.y, src)
        self.vx = self.vx + 0.5 * (self._ax0 + self.ax) * dt
        self.vy = self.vy + 0.5 * (self._ay0 + self.ay) * dt

    def remove(self, dead_mask):
        keep = ~dead_mask
        for name in ("x", "y", "vx", "vy", "size", "shade", "ax", "ay", "_ax0", "_ay0"):
            setattr(self, name, getattr(self, name)[keep])

    def swallowed_mask(self, bodies):
        """Asteroides dentro do Sol ou de um horizonte de eventos."""
        mask = np.zeros(len(self.x), dtype=bool)
        for b in bodies:
            if b.is_sun or getattr(b, "is_black_hole", False):
                rad = b.radius + self.size
                mask |= (self.x - b.x) ** 2 + (self.y - b.y) ** 2 < rad ** 2
        return mask

    def hit_mask(self, x, y, radius):
        return (self.x - x) ** 2 + (self.y - y) ** 2 < (self.size + radius) ** 2

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        vis = np.nonzero((sx > -10) & (sx < WIDTH + 10) & (sy > -10) & (sy < HEIGHT + 10))[0]
        for i in vis:
            g = int(self.shade[i])
            pygame.draw.circle(screen, (g, g - 15, g - 30), (int(sx[i]), int(sy[i])),
                               max(1, int(self.size[i] * zoom)))
