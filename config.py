"""Constantes e cores do jogo."""

WIDTH, HEIGHT = 1280, 720
FPS = 60
G = 1200.0          # Constante gravitacional (ajustada para escala do jogo)
SOFTENING = 25.0    # Evita singularidade quando r → 0
MAX_SPEED = 450.0   # Velocidade máxima da nave (px/s; órbita da Terra ≈ 165 px/s)
THRUST = 1.2        # Empuxo (×60 = px/s²; gravidade na órbita da Terra ≈ 75 px/s²)
ROT_SPEED = 4.5     # Velocidade de rotação (graus/frame)
BULLET_SPEED = 720.0   # px/s (relativo à nave que atira)
BULLET_LIFE = 90       # "frames" a 60 Hz (escala com dt)
PLAYER_RADIUS = 12
ALIEN_BULLET_SPEED = 480.0  # px/s

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

PLANET_MASS_SCALE = 0.15  # massas planetárias reduzidas: órbitas estáveis (Sol domina)
BH_GRAVITY_RANGE = 500.0   # alcance efetivo da gravidade dos buracos negros (escala do jogo)
DT_REF = 1.0 / 60.0        # passo de referência: contadores em "frames" são escalados por dt*60

# Combustível
FUEL_MAX = 100.0
FUEL_USE = 16.0          # por segundo de empuxo
FUEL_REFILL = 28.0       # por segundo perto de um planeta
FUEL_REFILL_MARGIN = 95  # distância da superfície para reabastecer

# Física / integração
MAX_SUBSTEPS = 8
PREDICT_SECONDS = 6.0
PREDICT_STEP = 0.06
PREDICT_EVERY = 8        # recalcula a trajetória a cada N frames

# Cinturão de asteroides
BELT_COUNT = 170
BELT_R_MIN, BELT_R_MAX = 545.0, 650.0

# Power-ups
POWERUP_DROP_CHANCE = 0.32
POWERUP_LIFE = 15.0      # segundos no espaço
SHIELD_TIME = 8.0
TRIPLE_TIME = 10.0

HIGHSCORE_FILE = "highscore.json"
