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
from entities import *
from audio import Sfx


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
            body = Body(name, x, y, vx, vy, mass * PLANET_MASS_SCALE, rad, color)
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

