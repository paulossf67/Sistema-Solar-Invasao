# Sistema Solar — Invasão Alienígena

Física orbital (Velocity Verlet) + buracos negros + **quasar ativo** com **jatos relativísticos** e discos de acreção.

## Como jogar

```bash
python sistema_solar.py
```

| Tecla | Ação |
|-------|------|
| A/D ou ←→ | Girar |
| W ou ↑ | Empuxo |
| Espaço | Atirar |
| +/- | Zoom |
| P | Pausar |
| F | Painel de física |
| R | Reiniciar |

## Jatos Relativísticos (M87*)

O quasar possui dois jatos bipolares inspirados em observações reais de AGN (especialmente M87):

| Estrutura | Descrição |
|-----------|-----------|
| **Núcleo (spine)** | Partículas rápidas e muito colimadas, brilho alto |
| **Envelope (sheath)** | Material mais lento e largo ao redor do núcleo |
| **Filamentos helicoidais** | Movimento em hélice ao longo do jato |
| **Nós de choque (knots)** | Pontos brilhantes que se movem (como nos jatos reais) |
| **Glow / feixe difuso** | Brilho de fundo que se alarga com a distância |
| **Assimetria Doppler** | Um lado do jato aparece mais brilhante (efeito visual de relatividade) |

### Física no jogo
- Entrar no cone do jato → aceleração forte para longe + dano
- Aliens no jato podem ser destruídos (bônus de pontos)
- Intensidade cai com a distância e com o desvio do eixo

### Disco de acreção
- Perfil de temperatura \( T \propto r^{-3/4} \)
- Rotação diferencial Kepleriana
- Gradiente de cor (quente no centro → frio na borda)

## Buracos negros
- **Sagitarius A\*** — quieto, sem jatos (disco de acreção simples).
- **M87\* (Quasar)** — ativo, com jatos bipolares.
- Ambos engolem nave, aliens, tiros e planetas que cruzam o horizonte de eventos.
- A gravidade deles tem **alcance suave** (~500 px): dominam a vizinhança, mas não desestabilizam as órbitas planetárias.

## Física e integração
- Sol, planetas, nave e aliens usam **Velocity Verlet em duas fases** (todos avançam a posição; depois as acelerações são recalculadas). Sem buracos negros, a energia do sistema se conserva a ~1e-4 % em 2 min.
- As massas planetárias são escaladas (`PLANET_MASS_SCALE`) para manter as órbitas estáveis.
- Unidades: velocidades em px/s; contadores (tiros, invencibilidade, ondas) escalam com `dt`, então o ritmo do jogo não depende do FPS.
- **Painel de física (F):** energia e momento angular de Sol + planetas + nave. Empuxo e jatos realizam trabalho externo e alteram E; o baseline é refeito quando um planeta é engolido.

## Arquivos
- `sistema_solar.py` — jogo atual (Verlet)
- `sistema_solar_euler_backup.py` — versão antiga com Euler, só referência

## Objetivo
Sobreviver aos aliens e não ser destruído pelo horizonte de eventos nem pelos jatos relativísticos do quasar.
