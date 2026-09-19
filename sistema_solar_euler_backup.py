#!/usr/bin/env python3
"""
Sistema Solar - Invasão Alienígena
Jogo com física orbital realista (Newton + integração numérica)
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
        self.trail = deque(maxlen=80 if not is_sun else 0)

    def distance_to(self, other):
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx*dx + dy*dy)

    def apply_gravity(self, others, dt):
        ax, ay = 0.0, 0.0
        for other in others:
            if other is self:
                continue
            dx = other.x - self.x
            dy = other.y - self.y
            dist_sq = dx*dx + dy*dy + SOFTENING*SOFTENING
            dist = math.sqrt(dist_sq)
            force = G * other.mass / dist_sq
            ax += force * dx / dist
            ay += force * dy / dist
        self.vx += ax * dt
        self.vy += ay * dt

    def update_position(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not self.is_sun:
            self.trail.append((self.x, self.y))

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(2, self.radius * zoom)

        # Trilha
        if len(self.trail) > 2:
            points = []
            for i, (tx, ty) in enumerate(self.trail):
                px = (tx - cam_x) * zoom + WIDTH // 2
                py = (ty - cam_y) * zoom + HEIGHT // 2
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    points.append((px, py))
            if len(points) > 1:
                alpha = 80
                for i in range(1, len(points)):
                    col = (*self.color[:3], alpha)
                    # Pygame não tem linha com alpha fácil, desenhamos linhas simples
                    pygame.draw.line(screen, self.color, points[i-1], points[i], 1)

        # Corpo
        if self.is_sun:
            # Brilho do sol
            for i in range(4, 0, -1):
                glow_r = r + i * 8
                glow_col = (min(255, self.color[0] + 20*i), 
                           min(255, self.color[1] + 10*i), 
                           max(0, self.color[2] - 20*i))
                s = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
                pygame.draw.circle(s, (*glow_col, 30), (glow_r, glow_r), glow_r)
                screen.blit(s, (sx - glow_r, sy - glow_r))
        pygame.draw.circle(screen, self.color, (int(sx), int(sy)), int(r))
        
        # Nome (só se zoom suficiente)
        if zoom > 0.4 and not self.is_sun:
            font = pygame.font.SysFont("consolas", 12)
            text = font.render(self.name, True, (200, 200, 220))
            screen.blit(text, (sx + r + 4, sy - 6))


# ==================== NAVE DO JOGADOR ====================
class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = -90.0   # apontando para cima
        self.radius = PLAYER_RADIUS
        self.mass = 1.0
        self.lives = 3
        self.score = 0
        self.invincible = 0
        self.thrusting = False
        self.trail = deque(maxlen=25)

    def rotate(self, direction, dt):
        self.angle += direction * ROT_SPEED * dt * 60

    def thrust(self, dt):
        rad = math.radians(self.angle)
        self.vx += math.cos(rad) * THRUST * dt * 60
        self.vy += math.sin(rad) * THRUST * dt * 60
        # Limita velocidade
        speed = math.sqrt(self.vx**2 + self.vy**2)
        if speed > MAX_SPEED:
            self.vx = self.vx / speed * MAX_SPEED
            self.vy = self.vy / speed * MAX_SPEED
        self.thrusting = True

    def apply_gravity(self, bodies, dt):
        ax, ay = 0.0, 0.0
        for body in bodies:
            dx = body.x - self.x
            dy = body.y - self.y
            dist_sq = dx*dx + dy*dy + SOFTENING*SOFTENING
            dist = math.sqrt(dist_sq)
            force = G * body.mass / dist_sq
            ax += force * dx / dist
            ay += force * dy / dist
        self.vx += ax * dt
        self.vy += ay * dt

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.trail.append((self.x, self.y))
        if self.invincible > 0:
            self.invincible -= 1
        self.thrusting = False

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2

        # Trilha de foguete
        if len(self.trail) > 2 and self.thrusting:
            for i, (tx, ty) in enumerate(list(self.trail)[-8:]):
                px = (tx - cam_x) * zoom + WIDTH // 2
                py = (ty - cam_y) * zoom + HEIGHT // 2
                alpha = int(40 + i * 15)
                pygame.draw.circle(screen, (255, 180, 50), (int(px), int(py)), 3)

        # Nave (triângulo)
        rad = math.radians(self.angle)
        size = self.radius * zoom * 1.8
        points = []
        # Ponta
        points.append((sx + math.cos(rad) * size, sy + math.sin(rad) * size))
        # Asas
        points.append((sx + math.cos(rad + 2.4) * size * 0.7, sy + math.sin(rad + 2.4) * size * 0.7))
        points.append((sx + math.cos(rad - 2.4) * size * 0.7, sy + math.sin(rad - 2.4) * size * 0.7))

        color = CYAN if self.invincible % 10 < 5 or self.invincible == 0 else (100, 100, 120)
        pygame.draw.polygon(screen, color, points)
        pygame.draw.polygon(screen, WHITE, points, 1)

        # Chama do motor
        if self.thrusting:
            flame = []
            flame.append((sx - math.cos(rad) * size * 0.3, sy - math.sin(rad) * size * 0.3))
            flame.append((sx + math.cos(rad + 2.8) * size * 0.5, sy + math.sin(rad + 2.8) * size * 0.5))
            flame.append((sx + math.cos(rad - 2.8) * size * 0.5, sy + math.sin(rad - 2.8) * size * 0.5))
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
        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60
        self.life -= 1

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
        # Velocidade inicial orbital aproximada + perturbação
        angle = random.uniform(0, 360)
        speed = random.uniform(1.5, 3.5)
        self.vx = math.cos(math.radians(angle)) * speed
        self.vy = math.sin(math.radians(angle)) * speed
        self.radius = ALIEN_RADIUS
        self.mass = 0.5
        self.hp = 2
        self.shoot_cooldown = random.randint(40, 100)
        self.angle = 0
        self.target = target

    def apply_gravity(self, bodies, dt):
        ax, ay = 0.0, 0.0
        for body in bodies:
            dx = body.x - self.x
            dy = body.y - self.y
            dist_sq = dx*dx + dy*dy + SOFTENING*SOFTENING
            dist = math.sqrt(dist_sq)
            force = G * body.mass / dist_sq * 0.7  # aliens um pouco menos sensíveis
            ax += force * dx / dist
            ay += force * dy / dist
        self.vx += ax * dt
        self.vy += ay * dt

    def update(self, dt, player, bullets):
        # IA simples: tenta ir em direção ao jogador com empuxo leve
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            dist = math.sqrt(dx*dx + dy*dy) + 1
            # Empuxo em direção ao jogador
            self.vx += (dx / dist) * 0.04
            self.vy += (dy / dist) * 0.04
            self.angle = math.degrees(math.atan2(dy, dx))

        # Limita velocidade
        speed = math.sqrt(self.vx**2 + self.vy**2)
        if speed > 8:
            self.vx = self.vx / speed * 8
            self.vy = self.vy / speed * 8

        self.x += self.vx * dt
        self.y += self.vy * dt

        self.shoot_cooldown -= 1
        if self.shoot_cooldown <= 0 and player and dist < 450:
            bullets.append(Bullet(self.x, self.y, self.angle, owner="alien"))
            self.shoot_cooldown = random.randint(50, 110)

    def draw(self, screen, cam_x, cam_y, zoom):
        sx = (self.x - cam_x) * zoom + WIDTH // 2
        sy = (self.y - cam_y) * zoom + HEIGHT // 2
        r = max(4, self.radius * zoom)

        # Corpo alienígena (disco + detalhes)
        pygame.draw.circle(screen, PURPLE, (int(sx), int(sy)), int(r))
        pygame.draw.circle(screen, (220, 150, 255), (int(sx), int(sy)), int(r * 0.6))
        # "Olhos"
        pygame.draw.circle(screen, RED, (int(sx - r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))
        pygame.draw.circle(screen, RED, (int(sx + r*0.3), int(sy - r*0.2)), max(2, int(r*0.25)))


# ==================== JOGO PRINCIPAL ====================
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sistema Solar — Invasão Alienígena | Física Orbital Realista")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big_font = pygame.font.SysFont("consolas", 36, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 14)

        self.reset()

    def reset(self):
        # Sol
        self.bodies = [
            Body("Sol", 0, 0, 0, 0, 8000, 45, YELLOW, is_sun=True)
        ]

        # Planetas com condições iniciais para órbitas aproximadamente estáveis
        # (raio orbital, velocidade circular aproximada = sqrt(G*M/r))
        planets_data = [
            # nome, raio_orbital, massa, raio visual, cor, velocidade angular offset
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
            # Posição inicial aleatória na órbita
            theta = random.uniform(0, 2 * math.pi)
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            # Velocidade circular: v = sqrt(G * M_sun / r)
            v = math.sqrt(G * 8000 / r) * 0.98  # leve ajuste
            vx = -v * math.sin(theta)
            vy =  v * math.cos(theta)
            self.bodies.append(Body(name, x, y, vx, vy, mass, rad, color))

        # Jogador começa perto da Terra
        terra = self.bodies[3]  # Terra
        self.player = Player(terra.x + 50, terra.y)
        # Dá uma velocidade orbital inicial aproximada
        self.player.vx = terra.vx
        self.player.vy = terra.vy - 1.5

        self.bullets = []
        self.aliens = []
        self.wave = 1
        self.wave_timer = 180
        self.game_over = False
        self.paused = False
        self.cam_x = 0
        self.cam_y = 0
        self.zoom = 0.55
        self.spawn_wave()

    def spawn_wave(self):
        n = 3 + self.wave * 2
        for _ in range(n):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(1600, 2200)
            x = dist * math.cos(angle)
            y = dist * math.sin(angle)
            self.aliens.append(Alien(x, y, self.player))

    def handle_input(self, dt):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player.rotate(-1, dt)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player.rotate(1, dt)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.player.thrust(dt)
        if keys[pygame.K_SPACE]:
            # Tiro com cooldown simples
            if not hasattr(self, "shoot_cd") or self.shoot_cd <= 0:
                self.bullets.append(Bullet(self.player.x, self.player.y, self.player.angle))
                self.shoot_cd = 12
        if hasattr(self, "shoot_cd") and self.shoot_cd > 0:
            self.shoot_cd -= 1

        # Zoom
        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS]:
            self.zoom = min(1.8, self.zoom + 0.01)
        if keys[pygame.K_MINUS]:
            self.zoom = max(0.15, self.zoom - 0.01)

    def update(self, dt):
        if self.game_over or self.paused:
            return

        # Física dos corpos (só planeta ↔ sol e interações leves)
        for body in self.bodies:
            if not body.is_sun:
                body.apply_gravity(self.bodies, dt)
        for body in self.bodies:
            body.update_position(dt)

        # Jogador
        self.player.apply_gravity(self.bodies, dt)
        self.player.update(dt)

        # Câmera segue o jogador suavemente
        self.cam_x += (self.player.x - self.cam_x) * 0.08
        self.cam_y += (self.player.y - self.cam_y) * 0.08

        # Aliens
        for alien in self.aliens[:]:
            alien.apply_gravity(self.bodies, dt)
            alien.update(dt, self.player, self.bullets)

            # Colisão alien x jogador
            if self.player.invincible <= 0:
                dx = alien.x - self.player.x
                dy = alien.y - self.player.y
                if dx*dx + dy*dy < (alien.radius + self.player.radius)**2:
                    self.player.lives -= 1
                    self.player.invincible = 90
                    # Empurra o alien
                    alien.vx += dx * 0.1
                    alien.vy += dy * 0.1
                    if self.player.lives <= 0:
                        self.game_over = True

        # Tiros
        for b in self.bullets[:]:
            b.update(dt)
            if b.life <= 0:
                self.bullets.remove(b)
                continue

            # Tiro do jogador acerta alien
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
            # Tiro alien acerta jogador
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

        # Colisão com planetas / sol (dano)
        for body in self.bodies:
            dx = body.x - self.player.x
            dy = body.y - self.player.y
            min_dist = body.radius + self.player.radius
            if dx*dx + dy*dy < min_dist**2:
                if body.is_sun:
                    self.player.lives = 0
                    self.game_over = True
                else:
                    # Empurra para fora e tira vida
                    if self.player.invincible <= 0:
                        self.player.lives -= 1
                        self.player.invincible = 60
                        # Bounce
                        dist = math.sqrt(dx*dx + dy*dy) + 0.1
                        self.player.vx -= (dx / dist) * 4
                        self.player.vy -= (dy / dist) * 4
                        if self.player.lives <= 0:
                            self.game_over = True

        # Próxima onda
        if not self.aliens:
            self.wave_timer -= 1
            if self.wave_timer <= 0:
                self.wave += 1
                self.spawn_wave()
                self.wave_timer = 120

    def draw_hud(self):
        # Fundo semi-transparente do HUD
        hud = pygame.Surface((WIDTH, 70), pygame.SRCALPHA)
        hud.fill((0, 0, 20, 160))
        self.screen.blit(hud, (0, 0))

        # Vidas
        lives_text = self.font.render(f"Vidas: {self.player.lives}", True, GREEN)
        self.screen.blit(lives_text, (20, 12))

        # Score
        score_text = self.font.render(f"Pontos: {self.player.score}", True, CYAN)
        self.screen.blit(score_text, (20, 38))

        # Onda
        wave_text = self.font.render(f"Onda: {self.wave}", True, ORANGE)
        self.screen.blit(wave_text, (220, 12))

        # Velocidade
        speed = math.sqrt(self.player.vx**2 + self.player.vy**2)
        spd_text = self.font.render(f"Vel: {speed:.1f}", True, WHITE)
        self.screen.blit(spd_text, (220, 38))

        # Instruções
        help1 = self.small_font.render("A/D ou ←→ girar | W ou ↑ empuxo | Espaço atirar | +/- zoom | P pausar | R reiniciar", True, GRAY)
        self.screen.blit(help1, (400, 18))

        # Indicador de física
        phys = self.small_font.render("Física Orbital Newtoniana ativa", True, (100, 200, 100))
        self.screen.blit(phys, (400, 42))

        if self.paused:
            pause_txt = self.big_font.render("PAUSADO", True, YELLOW)
            self.screen.blit(pause_txt, (WIDTH//2 - 90, HEIGHT//2 - 20))

        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self.screen.blit(overlay, (0, 0))
            go = self.big_font.render("GAME OVER", True, RED)
            self.screen.blit(go, (WIDTH//2 - 110, HEIGHT//2 - 60))
            sc = self.font.render(f"Pontuação final: {self.player.score}", True, WHITE)
            self.screen.blit(sc, (WIDTH//2 - 100, HEIGHT//2))
            rs = self.font.render("Pressione R para reiniciar", True, CYAN)
            self.screen.blit(rs, (WIDTH//2 - 130, HEIGHT//2 + 40))

    def draw(self):
        self.screen.fill(BLACK)

        # Estrelas de fundo (fixas em relação à câmera)
        random.seed(42)
        for i in range(120):
            sx = (random.randint(-2000, 2000) - self.cam_x * 0.1) % WIDTH
            sy = (random.randint(-2000, 2000) - self.cam_y * 0.1) % HEIGHT
            bright = random.randint(100, 255)
            pygame.draw.circle(self.screen, (bright, bright, bright), (int(sx), int(sy)), 1)
        random.seed()

        # Corpos celestes
        for body in self.bodies:
            body.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        # Tiros
        for b in self.bullets:
            b.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        # Aliens
        for alien in self.aliens:
            alien.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        # Jogador
        self.player.draw(self.screen, self.cam_x, self.cam_y, self.zoom)

        self.draw_hud()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0  # segundos
            # Limita dt para estabilidade numérica
            dt = min(dt, 0.05)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_p:
                        self.paused = not self.paused
                    if event.key == pygame.K_r:
                        self.reset()
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
