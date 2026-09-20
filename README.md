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
ou pelo jato do quasar. O recorde é salvo na pasta de dados do usuário.

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
- **Cinturão de asteroides** entre Marte e Júpiter — perigo, mas também minério e pontos ao destruir.
- **Luas e anéis:** Lua (Terra); Io, Europa e Ganimedes (Júpiter); anéis de Saturno. As luas são sólidas e bloqueiam tiros; voar dentro dos anéis **minera minério**.
- **Minério e loja:** aliens, asteroides e anéis dão minério. Ao limpar uma onda abre-se a **loja** (↑/↓, Enter compra, Espaço continua):
  - **Motor:** +12% de empuxo por nível.
  - **Tanque:** +25 de combustível máximo por nível.
  - **Gerador de escudo:** +25% de duração por nível.
  - **Canhão:** cadência de tiro +18% por nível.
  - **Reparo:** +1 vida.
  - **Reabastecer:** tanque cheio.
- **Interface:** setas nas bordas apontam aliens e power-ups fora da tela, mini-mapa mostra o sistema e os jatos, alertas piscam perto do Sol, dos horizontes e do jato.

## Buracos negros
- **Sagitarius A\*** — quieto, sem jatos.
- **M87\* (Quasar)** — ativo, com jatos bipolares (núcleo e envelope, filamentos helicoidais, nós de choque, assimetria Doppler).
- **Eles crescem:** absorvem massa passivamente e ao engolir planetas e aliens. O horizonte e o alcance da gravidade crescem com a raiz da massa (limite de 2× a massa inicial). Quanto mais tempo passa, mais perigosos ficam.
- Ambos engolem nave, aliens, tiros, asteroides e planetas (as luas somem junto com o planeta). Estrelas ao redor sofrem **lente gravitacional** aproximada.
- A gravidade deles tem **alcance suave** (~500 px) para não desestabilizar as órbitas planetárias.
- Disco de acreção: T ∝ r^(-3/4), rotação kepleriana diferencial, gradiente de cor.
- No cone do jato: aceleração forte para longe e dano (aliens também morrem).

## Física
- **Velocity Verlet em duas fases** (todos avançam a posição; depois as acelerações são recalculadas) com **subpassos adaptativos** quando algo rápido passa perto de um corpo (`Verlet ×N` no HUD).
- Gravidade das partículas de teste (asteroides, previsão de trajetória) **vetorizada com NumPy**.
- As massas planetárias são escaladas (`PLANET_MASS_SCALE`) e a atração planeta↔planeta é reduzida (`PLANET_COUPLING`) para manter as órbitas estáveis; a nave e os tiros sentem a gravidade completa.
- As **luas ficam "em trilhos"** (órbita circular analítica ao redor do planeta), porque o softening da gravidade impede órbitas lunares estáveis em N-corpos.
- Unidades: px e px/s; contadores (tiros, invencibilidade, ondas) escalam com `dt`, então o ritmo não depende do FPS.
- **Painel de física (F):** energia e momento angular de Sol + planetas + nave. Empuxo e jatos realizam trabalho externo e alteram E; o baseline é refeito quando um planeta é engolido. Sem buracos negros, a energia se conserva a ~1e-4 %.

## Executável e instalador (Windows)
```bash
pip install pyinstaller          # uma vez
python build.py                  # gera dist/SistemaSolar/ e installer/SistemaSolar_Setup_1.0.0.exe
python build.py --exe-only       # só o executável
```
- O instalador usa o [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`). Sem ele, o `build.py` gera só o executável.
- Instala por padrão só para o usuário atual (sem administrador), com atalhos no menu Iniciar e opção de atalho na área de trabalho.
- O recorde fica em `%APPDATA%\SistemaSolarInvasao\highscore.json`, então continua funcionando instalado em qualquer pasta.
- `SistemaSolar.exe --selftest` joga sozinho por alguns segundos e sai com código 0 (validação do pacote).

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
| `build.py`, `packaging/` | executável (PyInstaller), ícone e script do instalador (Inno Setup) |
| `sistema_solar_euler_backup.py` | versão antiga com Euler, só referência |

## Testes
```bash
python -m unittest discover -s tests -v
```
Cobrem luas, crescimento dos buracos negros, loja e melhorias, conservação de energia, estabilidade orbital, alcance da gravidade dos buracos negros, horizonte e cone do jato, colisões (momento), previsão × simulação real, asteroides, combustível, escudo, gravidade nos tiros e um teste de fumaça de render.
