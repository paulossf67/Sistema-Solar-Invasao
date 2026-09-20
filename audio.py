"""Efeitos sonoros sintetizados com NumPy (sem arquivos externos). Silencioso se o mixer falhar."""
import numpy as np
import pygame

RATE = 22050


def _env(n, attack=0.01, power=2.0):
    t = np.linspace(0.0, 1.0, n)
    return np.minimum(1.0, t / max(attack, 1e-6)) * (1.0 - t) ** power


def _tone(freq0, freq1, dur, vol=0.4, noise=0.0):
    n = int(RATE * dur)
    f = np.linspace(freq0, freq1, n)
    phase = 2 * np.pi * np.cumsum(f) / RATE
    wave = np.sign(np.sin(phase)) * 0.5 + np.sin(phase) * 0.5
    if noise:
        wave = wave * (1 - noise) + np.random.uniform(-1, 1, n) * noise
    return wave * _env(n) * vol


def _noise(dur, vol=0.5, power=2.0):
    n = int(RATE * dur)
    raw = np.random.uniform(-1, 1, n)
    k = 6   # filtro passa-baixa simples → estouro mais grave
    raw = np.convolve(raw, np.ones(k) / k, mode="same")
    return raw * _env(n, 0.005, power) * vol


class Sfx:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.muted = False
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=1)
            info = pygame.mixer.get_init()
            if info is None:
                return
            self._channels = info[2]
            self.sounds = {
                "shoot":   self._make(_tone(880, 300, 0.10, 0.25)),
                "alien":   self._make(_tone(300, 150, 0.14, 0.2, noise=0.2)),
                "explode": self._make(_noise(0.45, 0.7)),
                "hit":     self._make(_tone(200, 60, 0.30, 0.5, noise=0.4)),
                "pickup":  self._make(np.concatenate([_tone(500, 700, 0.07, 0.3), _tone(700, 1100, 0.10, 0.3)])),
                "swallow": self._make(_tone(400, 40, 0.6, 0.4)),
                "thrust":  self._make(_noise(0.25, 0.10, 0.3)),
            }
            self.enabled = True
        except (pygame.error, NotImplementedError):
            self.enabled = False

    def _make(self, wave):
        data = (np.clip(wave, -1, 1) * 32767).astype(np.int16)
        if self._channels == 2:
            data = np.repeat(data[:, None], 2, axis=1)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def play(self, name):
        if self.enabled and not self.muted:
            snd = self.sounds.get(name)
            if snd is not None:
                snd.play()

    def thrust(self):
        """Ronco do motor: só toca de novo quando o anterior terminou."""
        if self.enabled and not self.muted:
            snd = self.sounds["thrust"]
            if snd.get_num_channels() == 0:
                snd.play()
