"""Testes de física e regras do jogo. Execute:  python -m unittest discover -s tests -v"""
import math
import os
import random
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from config import *
from physics import *
from entities import *
import game as game_mod


def solar_system_without_bh():
    g = game_mod.Game()
    g.reset()
    g.bodies = [b for b in g.bodies if not getattr(b, "is_black_hole", False)]
    g.aliens.clear()
    g.player.x = g.player.y = 1e7   # nave fora do caminho
    g.player.vx = g.player.vy = 0.0
    g.state = "playing"
    return g


class TestGravity(unittest.TestCase):
    def test_bh_gravity_range_taper(self):
        bh = BlackHole("t", 0, 0, mass=50000, horizon_radius=30)
        near = compute_gravity_accel(200, 0, [bh])
        far = compute_gravity_accel(3000, 0, [bh])
        plain = G * 50000 / (3000 ** 2 + SOFTENING ** 2)
        self.assertLess(abs(far[0]), plain * 0.01)   # alcance limita a força a longa distância
        self.assertLess(near[0], 0)                  # e ela atrai para o buraco negro

    def test_numpy_matches_python(self):
        random.seed(1)
        g = game_mod.Game()
        src = source_arrays(g.bodies)
        pts = np.array([[300.0, 50.0], [-900.0, 400.0], [2500.0, -800.0]])
        ax, ay = accel_points(pts[:, 0], pts[:, 1], src)
        for i, (x, y) in enumerate(pts):
            gx, gy = compute_gravity_accel(x, y, g.bodies)
            self.assertAlmostEqual(ax[i], gx, places=6)
            self.assertAlmostEqual(ay[i], gy, places=6)


class TestIntegrator(unittest.TestCase):
    def test_energy_conserved_without_bh(self):
        random.seed(1)
        g = solar_system_without_bh()
        E0 = compute_system_energy(g.bodies)[0]
        for _ in range(60 * 30):
            g._integrate(1 / 60)
        E1 = compute_system_energy(g.bodies)[0]
        self.assertLess(abs((E1 - E0) / E0), 1e-3)

    def test_planets_stay_bound_with_bh(self):
        random.seed(2)
        g = game_mod.Game()
        g.aliens.clear()
        g.player.x = g.player.y = 1e7
        g.player.vx = g.player.vy = 0.0
        for _ in range(60 * 60):
            g._integrate(1 / 60)
        for b in g.bodies:
            if not b.is_sun and not getattr(b, "is_black_hole", False):
                self.assertLess(math.hypot(b.x, b.y), 2200, b.name)


class TestBlackHole(unittest.TestCase):
    def test_swallow_and_jet_cone(self):
        bh = BlackHole("q", 0, 0, mass=90000, horizon_radius=50, active_quasar=True, jet_angle=0.0)
        self.assertTrue(bh.swallows(30, 0))
        self.assertFalse(bh.swallows(80, 0))
        inside, intensity = bh.in_jet_cone(500, 10)
        self.assertTrue(inside)
        self.assertGreater(intensity, 0.3)
        self.assertFalse(bh.in_jet_cone(0, 500)[0])    # perpendicular ao eixo
        self.assertTrue(bh.in_jet_cone(-500, 0)[0])    # contra-jato
        quiet = BlackHole("s", 0, 0, mass=1000, horizon_radius=20)
        self.assertFalse(quiet.in_jet_cone(300, 0)[0])


class TestCollisions(unittest.TestCase):
    class P:
        def __init__(self, x, y, vx, vy):
            self.x, self.y, self.vx, self.vy = x, y, vx, vy

    def test_momentum_conserved(self):
        a, b = self.P(0, 0, 100, 0), self.P(15, 3, -40, 10)
        ma, mb = 1.0, 3.0
        p0 = (ma * a.vx + mb * b.vx, ma * a.vy + mb * b.vy)
        impact = collide_elastic(a, b, ma, mb, 20, 0.6)
        p1 = (ma * a.vx + mb * b.vx, ma * a.vy + mb * b.vy)
        self.assertGreater(impact, 0)
        self.assertAlmostEqual(p0[0], p1[0], places=6)
        self.assertAlmostEqual(p0[1], p1[1], places=6)
        self.assertGreaterEqual(math.hypot(b.x - a.x, b.y - a.y), 20 - 1e-9)   # sem sobreposição

    def test_no_collision_when_apart(self):
        a, b = self.P(0, 0, 1, 0), self.P(100, 0, 0, 0)
        self.assertEqual(collide_elastic(a, b, 1, 1, 20), 0.0)


class TestPrediction(unittest.TestCase):
    def test_matches_real_coasting(self):
        random.seed(4)
        g = solar_system_without_bh()
        terra = next(b for b in g.bodies if b.name == "Terra")
        p = g.player
        p.x, p.y = terra.x + 120, terra.y
        p.vx, p.vy = terra.vx, terra.vy + 25
        p.compute_accel(g.bodies)
        path, _ = predict_trajectory(p, g.bodies, seconds=2.0, step=1 / 60)
        for _ in range(120):
            g._integrate(1 / 60)
        self.assertLess(math.hypot(path[-1][0] - p.x, path[-1][1] - p.y), 5.0)


class TestBelt(unittest.TestCase):
    def test_belt_stays_in_region(self):
        random.seed(5)
        g = solar_system_without_bh()
        n0 = len(g.belt)
        for _ in range(60 * 10):
            g._integrate(1 / 60)
        dead = g.belt.swallowed_mask(g.bodies)
        self.assertLess(dead.sum(), n0 * 0.1)
        r = np.hypot(g.belt.x, g.belt.y)
        self.assertGreater(np.median(r), 450)
        self.assertLess(np.median(r), 800)


class TestGameRules(unittest.TestCase):
    def test_fuel_runs_out(self):
        p = Player(0, 0)
        p.fuel = FUEL_USE * 0.05
        p.apply_thrust(0.1)               # consome mais do que resta
        self.assertEqual(p.fuel, 0.0)
        p.end_frame(0.1)
        p.apply_thrust(0.1)
        self.assertFalse(p.thrusting)     # sem combustível não há empuxo
        self.assertEqual(p.thrust_ax, 0.0)

    def test_shield_blocks_damage(self):
        g = solar_system_without_bh()
        g.player.shield = 5.0
        self.assertFalse(g.hurt_player())
        self.assertEqual(g.player.lives, 3)
        g.player.shield = 0.0
        self.assertTrue(g.hurt_player())
        self.assertEqual(g.player.lives, 2)

    def test_swallowed_by_horizon_ends_game(self):
        g = game_mod.Game()
        g.start()
        bh = next(b for b in g.bodies if getattr(b, "is_black_hole", False))
        g.player.x, g.player.y = bh.x, bh.y
        g.update(1 / 60)
        self.assertTrue(g.game_over)

    def test_bullets_curve_with_gravity(self):
        sun = Body("Sol", 0, 0, 0, 0, 8000, 45, YELLOW, is_sun=True)
        b = Bullet(400, 0, -90, speed=300)     # atira "para cima", sem gravidade seguiria reto
        for _ in range(30):
            b.update(1 / 60, [sun])
        self.assertLess(b.x, 400)              # foi puxado em direção ao Sol

    def test_highscore_roundtrip(self):
        old = game_mod.load_highscore()
        try:
            game_mod.save_highscore(12345)
            self.assertEqual(game_mod.load_highscore(), 12345)
        finally:
            game_mod.save_highscore(old)

    def test_full_frame_smoke(self):
        random.seed(7)
        g = game_mod.Game()
        g.draw()
        g.start()
        for i in range(600):
            g.player.apply_thrust(1 / 60)
            g.update(1 / 60)
            g.draw()
        for st in ("paused", "over", "menu"):
            g.state = st
            g.draw()


if __name__ == "__main__":
    unittest.main()
