# Sistema Solar — Invasão Alienígena

Jogo de física orbital em pygame: gravidade newtoniana com **Velocity Verlet**, buracos negros,
um **quasar ativo** com jatos relativísticos, cinturão de asteroides e ondas de aliens.

## Como jogar

```bash
pip install -r requirements.txt
python sistema_solar.py
```

| Tecla | Ação |
|-------|------|
| A/D ou ←→ | Girar |
| W ou ↑ | Empuxo (gasta combustível) |
| Espaço | Atirar |
| +/- | Zoom |
| T | Mostrar/ocultar trajetória prevista |
| M | Som liga/desliga |
| F | Painel de física |
| P ou Esc | Pausa (menu: continuar, reiniciar, voltar, sair) |
| R | Reiniciar |

**Objetivo:** sobreviver às ondas de aliens sem ser engolido pelo Sol, pelos horizontes de eventos
ou pelo jato do quasar. O recorde é salvo em `highscore.json`.

## Jogabilidade
- **Trajetória prevista (T):** linha pontilhada de onde a nave vai se ela ficar à deriva (planetas também se movem na simulação). Um **X vermelho** marca uma colisão prevista.
- **Combustível:** o empuxo gasta combustível; ele recarrega perto de planetas.
- **Tiros com gravidade:** os tiros herdam a velocidade da nave e curvam com a gravidade — dá para usar planetas como estilingue.
- **Aliens** (aparecem conforme a onda):
  - roxo — normal
  - laranja — rápido, 1 de vida (onda 2+)
  - verde — atirador, mantém distância (onda 3+)
  - vermelho grande — tanque, 6 de vida (onda 4+)
- **Power-ups** (soltos pelos aliens): **E** escudo (também abalroa aliens), **3** tiro triplo, **F** combustível, **+** vida.
- **Colisões elásticas** com planetas e aliens (conservam momento); só batidas fortes causam dano.
- **Cinturão de asteroides** entre Marte e Júpiter — perigo, mas também pontos ao destruir.
- **Interface:** setas nas bordas apontam aliens e power-ups fora da tela, mini-mapa mostra o sistema e os jatos, alertas piscam perto do Sol, dos horizontes e do jato.

## Buracos negros
- **Sagitarius A\*** — quieto, sem jatos.
- **M87\* (Quasar)** — ativo, com jatos bipolares (núcleo e envelope, filamentos helicoidais, nós de choque, assimetria Doppler).
- Ambos engolem nave, aliens, tiros, asteroides e planetas. Estrelas ao redor sofrem **lente gravitacional** aproximada.
- A gravidade deles tem **alcance suave** (~500 px) para não desestabilizar as órbitas planetárias.
- Disco de acreção: T ∝ r^(-3/4), rotação kepleriana diferencial, gradiente de cor.
- No cone do jato: aceleração forte para longe e dano (aliens também morrem).

## Física
- **Velocity Verlet em duas fases** (todos avançam a posição; depois as acelerações são recalculadas) com **subpassos adaptativos** quando algo rápido passa perto de um corpo (`Verlet ×N` no HUD).
- Gravidade das partículas de teste (asteroides, previsão de trajetória) **vetorizada com NumPy**.
- As massas planetárias são escaladas (`PLANET_MASS_SCALE`) para manter as órbitas estáveis.
- Unidades: px e px/s; contadores (tiros, invencibilidade, ondas) escalam com `dt`, então o ritmo não depende do FPS.
- **Painel de física (F):** energia e momento angular de Sol + planetas + nave. Empuxo e jatos realizam trabalho externo e alteram E; o baseline é refeito quando um planeta é engolido. Sem buracos negros, a energia se conserva a ~1e-4 %.

## Estrutura
| Arquivo | Conteúdo |
|---------|----------|
| `sistema_solar.py` | ponto de entrada |
| `game.py` | laço, estados (menu/jogo/pausa/game over), colisões, HUD, mini-mapa |
| `entities.py` | corpos, buracos negros, nave, tiros, aliens, partículas, power-ups, asteroides |
| `physics.py` | gravidade, energia, colisão elástica, previsão de trajetória |
| `audio.py` | efeitos sonoros sintetizados (sem arquivos) |
| `render.py`, `config.py` | caches de render, constantes |
| `tests/` | testes automatizados |
| `sistema_solar_euler_backup.py` | versão antiga com Euler, só referência |

## Testes
```bash
python -m unittest discover -s tests -v
```
Cobrem conservação de energia, estabilidade orbital, alcance da gravidade dos buracos negros, horizonte e cone do jato, colisões (momento), previsão × simulação real, asteroides, combustível, escudo, gravidade nos tiros e um teste de fumaça de render.
