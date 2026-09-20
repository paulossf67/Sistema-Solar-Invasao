"""Gera packaging/icon.ico (PNG embutido em vários tamanhos) desenhando o ícone com pygame."""
import io
import os
import struct

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [16, 32, 48, 64, 128, 256]


def draw_master(n=256):
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = n // 2
    pygame.draw.circle(s, (8, 10, 28), (c, c), c - 2)
    pygame.draw.circle(s, (60, 80, 140), (c, c), c - 2, 4)
    for r in (52, 84, 112):
        pygame.draw.circle(s, (55, 70, 120), (c, c), r, 2)
    for i in range(6, 0, -1):                               # brilho do Sol
        surf = pygame.Surface((n, n), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 200, 60, 30), (c, c), 22 + i * 5)
        s.blit(surf, (0, 0))
    pygame.draw.circle(s, (255, 225, 90), (c, c), 24)
    pygame.draw.circle(s, (80, 150, 255), (c + 84, c), 11)   # planeta
    pygame.draw.circle(s, (220, 120, 60), (c - 52 * 0.7, c + 52 * 0.7), 7)
    pygame.draw.circle(s, (180, 100, 255), (c + 40, c - 104), 6)   # alien
    pygame.draw.circle(s, (255, 60, 60), (c + 38, c - 106), 2)
    pygame.draw.circle(s, (255, 60, 60), (c + 43, c - 106), 2)
    return s


def png_bytes(surf):
    path = os.path.join(HERE, "_tmp_icon.png")
    pygame.image.save(surf, path)
    with open(path, "rb") as f:
        data = f.read()
    os.remove(path)
    return data


def main():
    pygame.init()
    master = draw_master()
    pngs = [(n, png_bytes(pygame.transform.smoothscale(master, (n, n)))) for n in SIZES]
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(pngs)))
    offset = 6 + 16 * len(pngs)
    for n, data in pngs:
        out.write(struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, data in pngs:
        out.write(data)
    with open(os.path.join(HERE, "icon.ico"), "wb") as f:
        f.write(out.getvalue())
    with open(os.path.join(HERE, "icon.png"), "wb") as f:
        f.write(pngs[-1][1])
    print("icon.ico gerado")


if __name__ == "__main__":
    main()
