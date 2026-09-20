"""Laço principal do jogo."""
import json
import math
import os
import random
import sys
from collections import deque

import pygame

from config import *
from physics import *
from render import *
from render import _cached_surface
from entities import *
from audio import Sfx

MAP_SIZE = 190
MAP_RANGE = 4200.0
PLANETS_DATA = [
    ("Mercúrio", 180,  8,  6,  (180, 160, 140)),
    ("Vênus",    260, 18,  9,  (230, 190, 100)),
    ("Terra",    360, 22, 10,  (70, 140, 255)),
    ("Marte",    480, 12,  7,  (220, 100, 60)),
    ("Júpiter",  720, 90, 22,  (220, 180, 120)),
    ("Saturno",  920, 55, 18,  (230, 210, 150)),
    ("Urano",   1120, 30, 14,  (120, 220, 230)),
    ("Netuno",  1320, 28, 13,  (60, 100, 255)),
]
PAUSE_OPTIONS = ["Continuar", "Reiniciar", "Voltar ao menu", "Sair"]
# (planeta, nome, raio orbital, raio do corpo, cor, massa, ω rad/s)
MOONS_DATA = [
    ("Terra",   "Lua",       46, 5, (200, 200, 205), 0.3, 1.05),
    ("Júpiter", "Io",        60, 4, (230, 210, 110), 0.3, 1.70),
    ("Júpiter", "Europa",    80, 4, (210, 200, 180), 0.3, 1.05),
    ("Júpiter", "Ganimedes", 104, 6, (170, 160, 150), 0.4, 0.68),
]
RING_DATA = {"Saturno": (28, 46)}
# (chave, nome, custo(nível), descrição)
SHOP_ITEMS = [
    ("thrust", "Motor",              lambda lv: 20 * (lv + 1), "+12% de empuxo"),
    ("tank",   "Tanque",             lambda lv: 15 * (lv + 1), "+25 de combustível máximo"),
    ("shield", "Gerador de escudo",  lambda lv: 25 * (lv + 1), "+25% de duração do escudo"),
    ("gun",    "Canhão",             lambda lv: 20 * (lv + 1), "cadência de tiro +18%"),
    ("repair", "Reparo",             lambda lv: 35,            "+1 vida (máx. 6)"),
    ("refuel", "Reabastecer",        lambda lv: 8,             "tanque cheio"),
]


def highscore_path():
    """Recorde em pasta gravável do usuário (funciona instalado em Program Files e no .exe do PyInstaller)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "SistemaSolarInvasao", HIGHSCORE_FILE)


def load_highscore():
    try:
        with open(highscore_path(), encoding="utf-8") as f:
            return int(json.load(f).get("highscore", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_highscore(value):
    path = highscore_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"highscore": int(value)}, f)
    except OSError:
        pass


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sistema Solar — Invasão Alienígena | Verlet + Quasar Ativo")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = get_font(18)
        self.big_font = get_font(36, bold=True)
        self.huge_font = get_font(56, bold=True)
        self.small_font = get_font(14)
        self.sfx = Sfx()
        rng = random.Random(42)   # estrelas fixas de fundo (geradas uma única vez)
        self.stars = [(rng.randint(-3000, 3000), rng.randint(-3000, 3000), rng.randint(90, 255))
                      for _ in range(130)]
        self.highscore = load_highscore()
        self.show_physics_panel = True
        self.show_prediction = True
        self.state = "menu"          # menu | playing | paused | over
        self.pause_sel = 0
        self.reset()

    @property
    def game_over(self):
        return self.state == "over"

    @property
    def paused(self):
        return self.state == "paused"

    # ------------------------------------------------------------------ setup
    def reset(self):
        self.bodies = [Body("Sol", 0, 0, 0, 0, 8000, 45, YELLOW, is_sun=True)]

        for name, r, mass, rad, color in PLANETS_DATA:
            theta = random.uniform(0, 2 * math.pi)
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            v = math.sqrt(G * 8000 / r) * 0.995
            vx = -v * math.sin(theta)
            vy = v * math.cos(theta)
            body = Body(name, x, y, vx, vy, mass * PLANET_MASS_SCALE, rad, color, ring=RING_DATA.get(name))
            body.compute_accel(self.bodies)
            self.bodies.append(body)

        for parent_name, name, orbit_r, rad, color, mass, omega in MOONS_DATA:
            parent = next(b for b in self.bodies if b.name == parent_name)
            self.bodies.append(Moon(name, parent, orbit_r, rad, color, mass, omega, random.uniform(0, 2 * math.pi)))

        # Sagitarius A* — relativamente quieto; M87* — quasar ativo com jatos relativísticos
        self.bodies.append(BlackHole("Sagitarius A*", 2800, -900, mass=45000, horizon_radius=32,
                                     active_quasar=False))
        self.bodies.append(BlackHole("M87* (Quasar)", -3400, 1800, mass=95000, horizon_radius=52,
                                     active_quasar=True, jet_angle=35.0))

        for body in self.bodies:
            body.compute_accel(self.bodies)

        terra = next(b for b in self.bodies if b.name == "Terra")
        self.player = Player(terra.x + 90, terra.y)
        self.player.vx = terra.vx
        self.player.vy = terra.vy - 1.2
        self.player.compute_accel(self.bodies)

        self.belt = AsteroidBelt(8000)
        self.belt.init_accel(source_arrays(self.bodies))

        self.bullets = []
        self.aliens = []
        self.particles = []
        self.powerups = []
        self.wave = 1
        self.wave_timer = 180.0
        self.wave_cleared = False
        self.wave_bonus = 0
        self.shop_sel = 0
        self.shop_msg = ""
        self.shoot_cd = 0.0
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.zoom = 0.55
        self.warning = ""
        self.refueling = False
        self.frame = 0
        self.pred_path, self.pred_hit = [], None
        self.substeps = 1

        self.energy_history = deque(maxlen=300)   # ~5 segundos a 60 fps
        self.L_history = deque(maxlen=300)
        self.initial_energy = None
        self.initial_L = None
        self.n_solar_bodies = None   # muda quando um planeta é engolido → rebaseia E e L

        self.spawn_wave()

    def spawn_wave(self):
        kinds = alien_kinds_for_wave(self.wave)
        weights = {"normal": 4, "fast": 2, "shooter": 2, "tank": 1}
        n = min(3 + self.wave * 2, 20)
        for _ in range(n):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(1600, 2200)
            kind = random.choices(kinds, weights=[weights[k] for k in kinds])[0]
            alien = Alien(dist * math.cos(angle), dist * math.sin(angle), self.player, kind)
            alien.compute_accel(self.bodies, self.player)
            self.aliens.append(alien)

    # ------------------------------------------------------------------ eventos do jogo
    def end_game(self):
        if self.state == "over":
            return
        self.state = "over"
        self.player.lives = max(0, self.player.lives)
        spawn_explosion(self.particles, self.player.x, self.player.y, CYAN, n=40, speed=220, size=4)
        self.sfx.play("explode")
        if self.player.score > self.highscore:
            self.highscore = self.player.score
            save_highscore(self.highscore)

    def hurt_player(self, invincible_frames=90):
        p = self.player
        if p.protected or self.state != "playing":
            return False
        p.lives -= 1
        p.invincible = invincible_frames
        self.sfx.play("hit")
        spawn_explosion(self.particles, p.x, p.y, RED, n=14, speed=120, vx=p.vx * 0.3, vy=p.vy * 0.3)
        if p.lives <= 0:
            self.end_game()
        return True

    def kill_alien(self, alien, points, drop=True):
        if alien in self.aliens:
            self.aliens.remove(alien)
        self.player.score += int(points * alien.spec["score"])
        self.player.ore += ORE_ALIEN * alien.spec["score"]
        spawn_explosion(self.particles, alien.x, alien.y, alien.spec["color"],
                        n=22 if alien.kind == "tank" else 14, vx=alien.vx * 0.3, vy=alien.vy * 0.3)
        self.sfx.play("explode")
        if drop and random.random() < POWERUP_DROP_CHANCE:
            kinds = ["shield", "triple", "fuel"] * 2 + (["life"] if self.player.lives < MAX_LIVES else [])
            self.powerups.append(PowerUp(alien.x, alien.y, random.choice(kinds), alien.vx, alien.vy))

    def apply_powerup(self, kind):
        p = self.player
        if kind == "shield":
            p.shield = p.shield_time
        elif kind == "triple":
            p.triple = TRIPLE_TIME
        elif kind == "fuel":
            p.fuel = min(p.fuel_max, p.fuel + p.fuel_max * 0.5)
        elif kind == "life":
            p.lives = min(MAX_LIVES, p.lives + 1)
        self.sfx.play("pickup")

    # ------------------------------------------------------------------ entrada
    def handle_input(self, dt):
        keys = pygame.key.get_pressed()
        p = self.player
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            p.rotate(-1, dt)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            p.rotate(1, dt)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            p.apply_thrust(dt)
            if p.thrusting:
                self.sfx.thrust()

        if keys[pygame.K_SPACE] and self.shoot_cd <= 0:
            angles = (-9, 0, 9) if p.triple > 0 else (0,)
            for da in angles:
                self.bullets.append(Bullet(p.x, p.y, p.angle + da, vx0=p.vx, vy0=p.vy))
            self.shoot_cd = p.fire_cooldown
            self.sfx.play("shoot")
        if self.shoot_cd > 0:
            self.shoot_cd -= dt * 60

        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS] or keys[pygame.K_KP_PLUS]:
            self.zoom = min(1.8, self.zoom + 0.012 * dt * 60)
        if keys[pygame.K_MINUS] or keys[pygame.K_KP_MINUS]:
            self.zoom = max(0.12, self.zoom - 0.012 * dt * 60)

    # ------------------------------------------------------------------ física
    def _substeps(self, dt):
        """Subpassos adaptativos: mais passos quando algo rápido passa perto de um corpo."""
        n = 1
        for m in [self.player] + self.aliens:
            step = math.hypot(m.vx, m.vy) * dt
            if step < 1.0:
                continue
            dmin = min(math.hypot(b.x - m.x, b.y - m.y) - b.radius for b in self.bodies)
            n = max(n, math.ceil(step / (0.3 * max(dmin, 10.0))))
        return min(n, MAX_SUBSTEPS)

    def _integrate(self, dt):
        """Velocity Verlet em duas fases, com subpassos adaptativos."""
        n = self._substeps(dt)
        self.substeps = n
        h = dt / n
        for _ in range(n):
            for m in self.bodies + [self.player] + self.aliens:
                m.drift(h)
            self.belt.drift(h)
            for body in self.bodies:
                body.kick(h, self.bodies)
            self.player.kick(h, self.bodies)
            for alien in self.aliens:
                alien.kick(h, self.bodies, self.player)
            self.belt.kick(h, source_arrays(self.bodies))
        for body in self.bodies:
            body.record_trail()

    def update(self, dt):
        if self.state != "playing":
            return
        self.frame += 1
        p = self.player
        self._integrate(dt)

        k = 1.0 - (1.0 - 0.09) ** (dt * 60)   # câmera suave independente do FPS
        self.cam_x += (p.x - self.cam_x) * k
        self.cam_y += (p.y - self.cam_y) * k

        for part in self.particles[:]:
            part.update(dt)
            if part.life <= 0:
                self.particles.remove(part)
        for pu in self.powerups[:]:
            pu.update(dt)
            if pu.life <= 0:
                self.powerups.remove(pu)

        self._black_holes(dt)
        self._drop_orphan_moons()
        self._aliens(dt)
        self._bullets(dt)
        self._planet_collisions()
        self._belt_collisions()
        self._powerups()
        self._refuel_and_warnings(dt)

        if not self.aliens:
            if not self.wave_cleared:
                self.wave_cleared = True
                self.wave_bonus = int(ORE_WAVE_BONUS * self.wave)
                p.ore += self.wave_bonus
                self.shop_sel, self.shop_msg = 0, ""
                p.thrust_ax = p.thrust_ay = 0.0
                p.thrusting = False
                self.state = "shop"
                return
            self.wave_timer -= dt * 60
            if self.wave_timer <= 0:
                self.wave += 1
                self.spawn_wave()
                self.wave_timer = 120.0
                self.wave_cleared = False

        self._monitor_conservation()

        if self.show_prediction and self.frame % PREDICT_EVERY == 1:
            self.pred_path, self.pred_hit = predict_trajectory(p, self.bodies)

        p.end_frame(dt)

    def _black_holes(self, dt):
        p = self.player
        black_holes = [b for b in self.bodies if getattr(b, "is_black_hole", False)]
        for bh in black_holes:
            bh.absorb(ACCRETION_RATE * dt)   # acreção passiva: o buraco negro cresce
            if bh.swallows(p.x, p.y, p.radius):
                p.lives = 0
                bh.swallowed += 1
                self.sfx.play("swallow")
                self.end_game()
                return

            if bh.active_quasar:
                intensity = bh.apply_jet_force(p, dt)
                if intensity > 0.15:
                    self.hurt_player(75)

            for alien in self.aliens[:]:
                if bh.swallows(alien.x, alien.y, alien.radius):
                    self.kill_alien(alien, 50, drop=False)
                    bh.swallowed += 1
                    bh.absorb(BH_GAIN_ALIEN)
                    continue
                if bh.active_quasar:
                    intensity = bh.apply_jet_force(alien, dt)
                    if intensity > 0.25:
                        alien.hp -= 1
                        if alien.hp <= 0:
                            self.kill_alien(alien, 80, drop=False)

            for b in self.bullets[:]:
                if bh.swallows(b.x, b.y, b.radius):
                    self.bullets.remove(b)

            for body in self.bodies[:]:
                if getattr(body, "is_black_hole", False) or body.is_sun:
                    continue
                if bh.swallows(body.x, body.y, body.radius):
                    self.bodies.remove(body)
                    bh.swallowed += 1
                    bh.absorb(BH_GAIN_PLANET)
                    spawn_explosion(self.particles, body.x, body.y, body.color, n=24, speed=100, size=4)
                    self.sfx.play("swallow")

    def _drop_orphan_moons(self):
        self.bodies = [b for b in self.bodies if not (b.is_moon and b.parent not in self.bodies)]

    def _aliens(self, dt):
        p = self.player
        for alien in self.aliens[:]:
            if alien.think(dt, p, self.bullets):
                self.sfx.play("alien")

            # Colisão alien × jogador (elástica; escudo abalroa o alien)
            impact = collide_elastic(p, alien, p.mass, alien.mass, alien.radius + p.radius, 0.8)
            if impact > 0:
                if p.shield > 0:
                    alien.hp -= 2
                    if alien.hp <= 0:
                        self.kill_alien(alien, 60)
                        continue
                else:
                    self.hurt_player(90)

            # Colisão alien × planetas / Sol
            for body in self.bodies:
                if getattr(body, "is_black_hole", False):
                    continue
                if body.is_sun:
                    dx, dy = alien.x - body.x, alien.y - body.y
                    if dx * dx + dy * dy < (body.radius + alien.radius) ** 2:
                        self.kill_alien(alien, 30, drop=False)
                        break
                else:
                    collide_elastic(alien, body, alien.mass, body.mass, alien.radius + body.radius, 0.5)

    def _bullets(self, dt):
        p = self.player
        for b in self.bullets[:]:
            b.update(dt, self.bodies)
            if b.life <= 0:
                self.bullets.remove(b)
                continue

            hit_body = None
            for body in self.bodies:
                if getattr(body, "is_black_hole", False):
                    continue
                dx, dy = body.x - b.x, body.y - b.y
                if dx * dx + dy * dy < (body.radius + b.radius) ** 2:
                    hit_body = body
                    break
            if hit_body is not None:
                spawn_explosion(self.particles, b.x, b.y, ORANGE, n=5, speed=60, size=2)
                self.bullets.remove(b)
                continue

            if b.owner == "player":
                if len(self.belt):
                    hits = np.nonzero(self.belt.hit_mask(b.x, b.y, b.radius))[0]
                    if len(hits):
                        i = int(hits[0])
                        spawn_explosion(self.particles, float(self.belt.x[i]), float(self.belt.y[i]),
                                        (170, 150, 130), n=8, speed=70, size=2)
                        dead = np.zeros(len(self.belt), dtype=bool)
                        dead[i] = True
                        self.belt.remove(dead)
                        p.score += 10
                        p.ore += ORE_ASTEROID
                        self.bullets.remove(b)
                        continue
                for alien in self.aliens[:]:
                    dx, dy = alien.x - b.x, alien.y - b.y
                    if dx * dx + dy * dy < (alien.radius + b.radius) ** 2:
                        alien.hp -= 1
                        self.bullets.remove(b)
                        if alien.hp <= 0:
                            self.kill_alien(alien, 100 * self.wave)
                        break
            else:
                dx, dy = p.x - b.x, p.y - b.y
                if dx * dx + dy * dy < (p.radius + b.radius) ** 2:
                    self.bullets.remove(b)
                    self.hurt_player(90)

    def _planet_collisions(self):
        p = self.player
        for body in self.bodies:
            if getattr(body, "is_black_hole", False):
                continue
            if body.is_sun:
                dx, dy = body.x - p.x, body.y - p.y
                if dx * dx + dy * dy < (body.radius + p.radius) ** 2:
                    p.lives = 0
                    self.end_game()
                    return
                continue
            impact = collide_elastic(p, body, p.mass, body.mass, body.radius + p.radius, 0.5)
            if impact > 70:
                self.hurt_player(60)

    def _belt_collisions(self):
        if not len(self.belt):
            return
        dead = self.belt.swallowed_mask(self.bodies)
        p = self.player
        hit = self.belt.hit_mask(p.x, p.y, p.radius)
        if hit.any():
            for i in np.nonzero(hit)[0]:
                spawn_explosion(self.particles, float(self.belt.x[i]), float(self.belt.y[i]),
                                (170, 150, 130), n=6, speed=80, size=2)
            self.hurt_player(60)
            dead |= hit
        if dead.any():
            self.belt.remove(dead)

    def _powerups(self):
        p = self.player
        for pu in self.powerups[:]:
            dx, dy = pu.x - p.x, pu.y - p.y
            if dx * dx + dy * dy < (pu.radius + p.radius + 8) ** 2:
                self.apply_powerup(pu.kind)
                self.powerups.remove(pu)

    def _refuel_and_warnings(self, dt):
        p = self.player
        self.refueling = False
        self.mining = False
        for body in self.bodies:
            if getattr(body, "is_black_hole", False) or body.is_sun:
                continue
            d = math.hypot(body.x - p.x, body.y - p.y)
            if not self.refueling and d - body.radius < FUEL_REFILL_MARGIN and p.fuel < p.fuel_max:
                p.fuel = min(p.fuel_max, p.fuel + FUEL_REFILL * dt)
                self.refueling = True
            if body.ring and body.ring[0] < d < body.ring[1]:
                p.ore += ORE_RING_RATE * dt
                self.mining = True

        self.warning = ""
        for body in self.bodies:
            d = math.hypot(body.x - p.x, body.y - p.y)
            if getattr(body, "is_black_hole", False):
                if d < body.horizon * 3.5 + 120:
                    self.warning = "HORIZONTE DE EVENTOS!"
                elif body.active_quasar:
                    inside, _ = body.in_jet_cone(p.x, p.y)
                    if inside:
                        self.warning = "JATO RELATIVÍSTICO!"
            elif body.is_sun and d < 140 and not self.warning:
                self.warning = "PERIGO: SOL!"
        if p.fuel <= 0 and not self.warning:
            self.warning = "SEM COMBUSTÍVEL — vá até um planeta"

    # ------------------------------------------------------------------ loja
    def upgrade_cost(self, key):
        item = next(i for i in SHOP_ITEMS if i[0] == key)
        return item[2](self.player.upgrades.get(key, 0))

    def can_buy(self, key):
        p = self.player
        if key in UPGRADE_MAX and p.upgrades[key] >= UPGRADE_MAX[key]:
            return False, "nível máximo"
        if key == "repair" and p.lives >= MAX_LIVES:
            return False, "vidas no máximo"
        if key == "refuel" and p.fuel >= p.fuel_max - 0.5:
            return False, "tanque já está cheio"
        if p.ore < self.upgrade_cost(key):
            return False, "minério insuficiente"
        return True, ""

    def buy(self, key):
        ok, why = self.can_buy(key)
        if not ok:
            self.shop_msg = why
            return False
        p = self.player
        p.ore -= self.upgrade_cost(key)
        if key in UPGRADE_MAX:
            p.upgrades[key] += 1
            if key == "tank":
                p.fuel = min(p.fuel_max, p.fuel + 25.0)
        elif key == "repair":
            p.lives += 1
        elif key == "refuel":
            p.fuel = p.fuel_max
        self.sfx.play("pickup")
        self.shop_msg = "comprado!"
        return True

    def leave_shop(self):
        self.state = "playing"
        self.wave_timer = 90.0

    def _monitor_conservation(self):
        E, K, U = compute_system_energy(self.bodies, self.player)
        L = compute_angular_momentum(self.bodies, self.player)
        n_solar = sum(1 for b in self.bodies if not getattr(b, "is_black_hole", False) and not b.is_moon)
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

    # ------------------------------------------------------------------ desenho
    def _screen_pos(self, x, y):
        return ((x - self.cam_x) * self.zoom + WIDTH // 2, (y - self.cam_y) * self.zoom + HEIGHT // 2)

    def draw_stars(self):
        # Lente gravitacional aproximada: estrelas perto de um buraco negro são empurradas para fora
        lenses = []
        for b in self.bodies:
            if getattr(b, "is_black_hole", False):
                bx, by = self._screen_pos(b.x, b.y)
                h = max(4.0, b.horizon * self.zoom)
                if -h * 8 < bx < WIDTH + h * 8 and -h * 8 < by < HEIGHT + h * 8:
                    lenses.append((bx, by, h))
        for x, y, b in self.stars:
            sx = (x - self.cam_x * 0.08) % WIDTH
            sy = (y - self.cam_y * 0.08) % HEIGHT
            for bx, by, h in lenses:
                dx, dy = sx - bx, sy - by
                d = math.hypot(dx, dy)
                if d < h * 7:
                    if d < h * 1.05:
                        sx = -100
                        break
                    push = min(h * 3.0, (h * 1.6) ** 2 / d)
                    sx, sy = bx + dx / d * (d + push), by + dy / d * (d + push)
            pygame.draw.circle(self.screen, (b, b, b), (int(sx), int(sy)), 1)

    def draw_prediction(self):
        if not self.show_prediction or len(self.pred_path) < 2:
            return
        n = len(self.pred_path)
        for i in range(2, n, 2):
            x, y = self.pred_path[i]
            sx, sy = self._screen_pos(x, y)
            if -10 < sx < WIDTH + 10 and -10 < sy < HEIGHT + 10:
                f = 1.0 - i / n
                col = (int(60 + 120 * f), int(160 + 80 * f), int(120 + 100 * f))
                pygame.draw.circle(self.screen, col, (int(sx), int(sy)), 2)
        if self.pred_hit is not None:
            x, y = self.pred_path[-1]
            sx, sy = self._screen_pos(x, y)
            pygame.draw.line(self.screen, RED, (sx - 6, sy - 6), (sx + 6, sy + 6), 2)
            pygame.draw.line(self.screen, RED, (sx - 6, sy + 6), (sx + 6, sy - 6), 2)

    def draw_offscreen_arrows(self):
        cx, cy = WIDTH / 2, HEIGHT / 2
        targets = [(a.x, a.y, a.spec["color"], 2600) for a in self.aliens]
        targets += [(pu.x, pu.y, POWERUP_KINDS[pu.kind][0], 1600) for pu in self.powerups]
        for x, y, color, max_d in targets:
            if math.hypot(x - self.player.x, y - self.player.y) > max_d:
                continue
            sx, sy = self._screen_pos(x, y)
            if 20 < sx < WIDTH - 20 and 90 < sy < HEIGHT - 20:
                continue
            dx, dy = sx - cx, sy - cy
            t = min((cx - 30) / max(abs(dx), 1e-6), (cy - 100) / max(abs(dy), 1e-6))
            ax, ay = cx + dx * t, cy + dy * t
            ang = math.atan2(dy, dx)
            pts = [(ax + math.cos(ang) * 11, ay + math.sin(ang) * 11),
                   (ax + math.cos(ang + 2.5) * 8, ay + math.sin(ang + 2.5) * 8),
                   (ax + math.cos(ang - 2.5) * 8, ay + math.sin(ang - 2.5) * 8)]
            pygame.draw.polygon(self.screen, color, pts)

    def draw_minimap(self):
        s = MAP_SIZE
        x0, y0 = 12, HEIGHT - s - 12
        scale = (s / 2) / MAP_RANGE
        cx, cy = x0 + s // 2, y0 + s // 2

        panel = _cached_surface(("minimap", s), lambda: self._minimap_bg(s))
        self.screen.blit(panel, (x0, y0))

        def to_map(wx, wy):
            return int(cx + wx * scale), int(cy + wy * scale)

        pygame.draw.circle(self.screen, (40, 50, 80), (cx, cy), int(1400 * scale), 1)
        for i in range(0, len(self.belt), 4):
            pygame.draw.circle(self.screen, (110, 100, 90), to_map(float(self.belt.x[i]), float(self.belt.y[i])), 0)
        for b in self.bodies:
            mx, my = to_map(b.x, b.y)
            if getattr(b, "is_black_hole", False):
                col = (255, 100, 255) if b.active_quasar else (255, 170, 80)
                pygame.draw.circle(self.screen, col, (mx, my), 4, 1)
                if b.active_quasar:
                    for sign in (0, 180):
                        a = math.radians(b.jet_angle + sign)
                        pygame.draw.line(self.screen, (150, 90, 230), (mx, my),
                                         to_map(b.x + math.cos(a) * b.jet_length, b.y + math.sin(a) * b.jet_length), 1)
            elif b.is_sun:
                pygame.draw.circle(self.screen, YELLOW, (mx, my), 3)
            else:
                pygame.draw.circle(self.screen, b.color, (mx, my), 2)
        for a in self.aliens:
            pygame.draw.circle(self.screen, a.spec["color"], to_map(a.x, a.y), 2)
        for pu in self.powerups:
            pygame.draw.circle(self.screen, WHITE, to_map(pu.x, pu.y), 2)
        # área visível + nave
        vw, vh = WIDTH / self.zoom * scale, HEIGHT / self.zoom * scale
        vx, vy = to_map(self.cam_x - WIDTH / self.zoom / 2, self.cam_y - HEIGHT / self.zoom / 2)
        pygame.draw.rect(self.screen, (70, 90, 130), (vx, vy, vw, vh), 1)
        pygame.draw.circle(self.screen, CYAN, to_map(self.player.x, self.player.y), 3)

    @staticmethod
    def _minimap_bg(s):
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((8, 10, 25, 190))
        pygame.draw.rect(surf, (60, 80, 140), (0, 0, s, s), 1)
        return surf

    def draw_bar(self, x, y, w, h, frac, color, label):
        pygame.draw.rect(self.screen, (25, 28, 50), (x, y, w, h))
        pygame.draw.rect(self.screen, color, (x, y, int(w * max(0.0, min(1.0, frac))), h))
        pygame.draw.rect(self.screen, (80, 90, 130), (x, y, w, h), 1)
        self.screen.blit(self.small_font.render(label, True, WHITE), (x + w + 8, y - 2))

    def draw_hud(self):
        p = self.player
        hud = pygame.Surface((WIDTH, 72), pygame.SRCALPHA)
        hud.fill((0, 0, 20, 170))
        self.screen.blit(hud, (0, 0))

        self.screen.blit(self.font.render(f"Vidas: {p.lives}", True, GREEN), (20, 10))
        self.screen.blit(self.font.render(f"Pontos: {p.score}", True, CYAN), (20, 40))
        self.screen.blit(self.font.render(f"Onda: {self.wave}", True, ORANGE), (170, 10))
        speed = math.hypot(p.vx, p.vy)
        self.screen.blit(self.font.render(f"Vel: {speed:.0f}", True, WHITE), (170, 40))
        self.screen.blit(self.small_font.render(f"Recorde: {self.highscore}", True, YELLOW), (300, 12))
        ore_col = (255, 200, 90) if self.mining else (200, 170, 110)
        self.screen.blit(self.small_font.render(f"Minério: {int(p.ore)}" + (" (minerando)" if self.mining else ""), True, ore_col), (430, 12))

        fuel_col = GREEN if p.fuel > 30 else (ORANGE if p.fuel > 12 else RED)
        self.draw_bar(300, 40, 140, 12, p.fuel / p.fuel_max, fuel_col,
                      "COMB." + (" +" if self.refueling else ""))
        if p.shield > 0:
            self.draw_bar(520, 30, 90, 8, p.shield / p.shield_time, CYAN, "escudo")
        if p.triple > 0:
            self.draw_bar(520, 44, 90, 8, p.triple / TRIPLE_TIME, YELLOW, "tiro x3")

        help1 = self.small_font.render(
            "A/D girar | W empuxo | Espaço atirar | +/- zoom | T trajetória | M som | F painel | P pausa | R reiniciar",
            True, GRAY)
        self.screen.blit(help1, (640, 12))
        info = self.small_font.render(
            f"Verlet ×{self.substeps}  •  Newton  •  Quasar M87*  •  Asteroides: {len(self.belt)}",
            True, (90, 210, 120))
        self.screen.blit(info, (640, 42))

        if self.warning and (self.frame // 8) % 2 == 0:
            txt = self.big_font.render(self.warning, True, RED)
            self.screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 84))

    def draw_overlay_text(self, lines, top):
        for text, font, color in lines:
            surf = font.render(text, True, color)
            self.screen.blit(surf, (WIDTH // 2 - surf.get_width() // 2, top))
            top += surf.get_height() + 10

    def draw_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 10, 175))
        self.screen.blit(overlay, (0, 0))
        self.draw_overlay_text([
            ("SISTEMA SOLAR", self.huge_font, YELLOW),
            ("Invasão Alienígena", self.big_font, ORANGE),
        ], 90)
        self.draw_overlay_text([
            ("A/D girar  |  W empuxo  |  Espaço atirar  |  +/- zoom", self.font, WHITE),
            ("T trajetória prevista  |  M som  |  F painel de física  |  P/Esc pausa", self.font, WHITE),
            ("Tiros curvam com a gravidade — use planetas como estilingue.", self.font, CYAN),
            ("Reabasteça perto de planetas. Evite o Sol, os buracos negros e o jato do quasar.", self.font, CYAN),
            ("Power-ups:  E escudo   3 tiro triplo   F combustível   + vida", self.font, GREEN),
        ], 240)
        self.draw_overlay_text([
            (f"Recorde: {self.highscore}", self.font, YELLOW),
            ("ENTER para começar   •   Esc para sair", self.big_font, WHITE),
        ], 480)

    def draw_pause(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 10, 170))
        self.screen.blit(overlay, (0, 0))
        self.draw_overlay_text([("PAUSADO", self.huge_font, YELLOW)], 170)
        top = 290
        for i, opt in enumerate(PAUSE_OPTIONS):
            selected = i == self.pause_sel
            surf = self.big_font.render(("> " if selected else "  ") + opt, True, CYAN if selected else GRAY)
            self.screen.blit(surf, (WIDTH // 2 - 150, top))
            top += 50
        self.draw_overlay_text([("↑/↓ escolher  •  Enter confirmar", self.small_font, GRAY)], top + 10)

    def draw_shop(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 10, 200))
        self.screen.blit(overlay, (0, 0))
        p = self.player
        self.draw_overlay_text([
            (f"ONDA {self.wave} CONCLUÍDA", self.big_font, GREEN),
            (f"+{self.wave_bonus} de minério de bônus   •   Minério: {int(p.ore)}", self.font, (255, 200, 90)),
        ], 70)
        top = 190
        x0 = WIDTH // 2 - 330
        for i, (key, name, cost_fn, desc) in enumerate(SHOP_ITEMS):
            selected = i == self.shop_sel
            ok, why = self.can_buy(key)
            if key in UPGRADE_MAX:
                lvl = p.upgrades[key]
                level_txt = "■" * lvl + "□" * (UPGRADE_MAX[key] - lvl)
                cost_txt = "MÁX" if lvl >= UPGRADE_MAX[key] else f"{cost_fn(lvl)}"
            else:
                level_txt, cost_txt = "", f"{cost_fn(0)}"
            col = (CYAN if ok else GRAY) if selected else (WHITE if ok else (90, 90, 110))
            if selected:
                pygame.draw.rect(self.screen, (25, 35, 70), (x0 - 12, top - 4, 680, 40), border_radius=4)
            self.screen.blit(self.font.render(("> " if selected else "  ") + name, True, col), (x0, top))
            self.screen.blit(self.font.render(level_txt, True, col), (x0 + 250, top))
            self.screen.blit(self.font.render(desc, True, GRAY if not selected else WHITE), (x0 + 340, top))
            self.screen.blit(self.font.render(cost_txt, True, (255, 200, 90) if ok else (110, 95, 70)), (x0 + 610, top))
            top += 46
        if self.shop_msg:
            self.draw_overlay_text([(self.shop_msg, self.font, YELLOW)], top + 8)
        self.draw_overlay_text([
            ("↑/↓ escolher  •  Enter comprar  •  Espaço/N próxima onda", self.font, WHITE),
            (f"Vidas {p.lives}   Combustível {int(p.fuel)}/{int(p.fuel_max)}", self.small_font, GRAY),
        ], HEIGHT - 110)

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        self.screen.blit(overlay, (0, 0))
        new_record = self.player.score >= self.highscore and self.player.score > 0
        self.draw_overlay_text([
            ("GAME OVER", self.huge_font, RED),
            (f"Pontuação final: {self.player.score}   (onda {self.wave})", self.font, WHITE),
            ("NOVO RECORDE!" if new_record else f"Recorde: {self.highscore}", self.font, YELLOW),
            ("R / Enter reiniciar   •   Esc menu", self.font, CYAN),
        ], 250)

    def draw(self):
        self.screen.fill(BLACK)
        self.draw_stars()

        for body in self.bodies:
            body.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        self.belt.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        for pu in self.powerups:
            pu.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        for b in self.bullets:
            b.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        for alien in self.aliens:
            alien.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        if self.state in ("playing", "paused", "shop"):
            self.draw_prediction()
        for part in self.particles:
            part.draw(self.screen, self.cam_x, self.cam_y, self.zoom)
        if self.state != "over":
            self.player.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        if self.state == "menu":
            self.draw_menu()
        else:
            self.draw_offscreen_arrows()
            self.draw_hud()
            self.draw_minimap()
            self.draw_physics_panel()
            if self.state == "shop":
                self.draw_shop()
            elif self.state == "paused":
                self.draw_pause()
            elif self.state == "over":
                self.draw_game_over()
        pygame.display.flip()

    # ------------------------------------------------------------------ laço
    def start(self):
        self.reset()
        self.state = "playing"

    def handle_keydown(self, key):
        """Retorna False para encerrar o jogo."""
        if self.state == "menu":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.start()
            elif key == pygame.K_ESCAPE:
                return False
            return True

        if key == pygame.K_f:
            self.show_physics_panel = not self.show_physics_panel
        elif key == pygame.K_t:
            self.show_prediction = not self.show_prediction
        elif key == pygame.K_m:
            self.sfx.muted = not self.sfx.muted

        if self.state == "playing":
            if key in (pygame.K_p, pygame.K_ESCAPE):
                self.state, self.pause_sel = "paused", 0
            elif key == pygame.K_r:
                self.start()
        elif self.state == "shop":
            if key in (pygame.K_UP, pygame.K_w):
                self.shop_sel = (self.shop_sel - 1) % len(SHOP_ITEMS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.shop_sel = (self.shop_sel + 1) % len(SHOP_ITEMS)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.buy(SHOP_ITEMS[self.shop_sel][0])
            elif key in (pygame.K_SPACE, pygame.K_n, pygame.K_ESCAPE):
                self.leave_shop()
            elif key == pygame.K_r:
                self.start()
        elif self.state == "paused":
            if key in (pygame.K_p, pygame.K_ESCAPE):
                self.state = "playing"
            elif key in (pygame.K_UP, pygame.K_w):
                self.pause_sel = (self.pause_sel - 1) % len(PAUSE_OPTIONS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.pause_sel = (self.pause_sel + 1) % len(PAUSE_OPTIONS)
            elif key == pygame.K_r:
                self.start()
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                choice = PAUSE_OPTIONS[self.pause_sel]
                if choice == "Continuar":
                    self.state = "playing"
                elif choice == "Reiniciar":
                    self.start()
                elif choice == "Voltar ao menu":
                    self.reset()
                    self.state = "menu"
                else:
                    return False
        elif self.state == "over":
            if key in (pygame.K_r, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start()
            elif key == pygame.K_ESCAPE:
                self.reset()
                self.state = "menu"
        return True

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.033)   # limita dt para estabilidade do Verlet

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if not self.handle_keydown(event.key):
                        running = False

            if self.state == "playing":
                self.handle_input(dt)
                self.update(dt)
            elif self.state == "over":
                for part in self.particles[:]:
                    part.update(dt)
                    if part.life <= 0:
                        self.particles.remove(part)

            self.draw()

        pygame.quit()
        sys.exit()


def selftest(frames=400):
    """Joga sozinho por alguns segundos (usado para validar o executável empacotado). Retorna 0 se OK."""
    try:
        g = Game()
        g.draw()
        g.start()
        for i in range(frames):
            g.player.apply_thrust(1 / 60)
            g.update(1 / 60)
            g.draw()
            if g.state == "shop":
                g.buy("refuel")
                g.leave_shop()
        for state in ("paused", "over", "shop", "menu"):
            g.state = state
            g.draw()
        return 0
    except Exception:   # noqa: BLE001 — qualquer falha no empacotamento deve virar código de erro
        return 1


def main():
    if "--selftest" in sys.argv:
        code = selftest()
        pygame.quit()
        sys.exit(code)
    Game().run()
