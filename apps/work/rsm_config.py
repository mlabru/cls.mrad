# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_config
constantes do monitor de recepção radar: códigos de status, cores, rótulos,
limiares de atraso e a lista mínima de estações monitoradas.

é o único lugar onde esses valores são definidos; rsmStatus.py, rsm_figure.py,
rsmPNG.py e rsmGUI.py só os leem.

2026.out  mlabru  guia de manutenção: CI_DEFAULT_WINDOW_HOURS (antes repetida
                  em rsmStatus, rsmPNG e rsmGUI)
2026.out  mlabru  banco como única fonte: CI_PENDING_GRACE_MINUTES e
                  CI_SOURCE_STALE_MINUTES (atraso do sync do 21.mvol)
2026.out  mlabru  refatoração para legibilidade: limiares de atraso, tamanho do
                  slot e limiares do painel de métricas viram constantes
                  nomeadas (antes eram números soltos no código); um código
                  de status por linha; movido para apps/work/
2025.nov  mlabru  initial version (Linux/Python)
"""
# < constants >────────────────────────────────────────────────────────────────────────

# paleta de cores (tema escuro) --------------------------------------------------------

CS_ACCENT    = "#58a6ff"

CS_BG_CARD   = "#21262d"
CS_BG_DARK   = "#0d1117"
CS_BG_PANEL  = "#161b22"

CS_GRAY      = "#30363d"
CS_TEXT_MAIN = "#e6edf3"
CS_TEXT_SUB  = "#8b949e"

# cor de cada status
CS_C_DELAY_L = "#db6d28"   # laranja  - atraso grande (> 20 min)
CS_C_DELAY_S = "#d29922"   # âmbar    - atraso pequeno (9 a 20 min)
CS_C_MISS    = "#f85149"   # vermelho - perdido
CS_C_OK      = "#3fb950"   # verde    - chegou no prazo
# slot que ainda não venceu: mesma cor do fundo dos cards, para "sumir" no grid
CS_C_FUTURE  = CS_BG_CARD

# códigos de status --------------------------------------------------------------------
# os códigos são índices (0..4) das listas CLST_STATUS_COLORS e
# CLST_STATUS_LABELS logo abaixo, e também os valores da matriz desenhada pelo
# imshow em rsm_figure.py.  Ao adicionar um status, acrescente o código aqui e,
# NA MESMA POSIÇÃO, a cor e o rótulo nas duas listas.

CI_ST_DL     = 0   # atraso grande (delay large)
CI_ST_DS     = 1   # atraso pequeno (delay small)
CI_ST_FUTURE = 2   # slot ainda não venceu (aguardando)
CI_ST_MISS   = 3   # arquivo não recebido
CI_ST_OK     = 4   # recebido no prazo

# cor de cada status, indexada pelo código
CLST_STATUS_COLORS = [ CS_C_DELAY_L,      # CI_ST_DL
                       CS_C_DELAY_S,      # CI_ST_DS
                       CS_C_FUTURE,       # CI_ST_FUTURE
                       CS_C_MISS,         # CI_ST_MISS
                       CS_C_OK ]          # CI_ST_OK

# rótulo de cada status, indexado pelo código
CLST_STATUS_LABELS = [ "Atraso grave (>20 min)",    # CI_ST_DL
                       "Atraso leve (9–20 min)",    # CI_ST_DS
                       "Aguardando",                # CI_ST_FUTURE
                       "Perdido",                   # CI_ST_MISS
                       "No prazo" ]                 # CI_ST_OK

# grade de tempo -----------------------------------------------------------------------

# cada estação envia um arquivo a cada 10 minutos (um "slot")
CI_SLOT_MINUTES = 10
# slots em uma hora (6)
CI_SLOTS_PER_HOUR = 60 // CI_SLOT_MINUTES

# janela padrão do monitor, em horas (rsmStatus, rsmPNG e a GUI começam nela)
CI_DEFAULT_WINDOW_HOURS = 24

# limiares de atraso (chegada real - horário esperado, em segundos) --------------------

# até 9 min (inclusive): no prazo
CI_ON_TIME_MAX_SECONDS = 9 * 60
# acima de 9 até 20 min (inclusive): atraso pequeno; acima disso: atraso grande
CI_SMALL_DELAY_MAX_SECONDS = 20 * 60

# atraso da fonte (21.mvol) ------------------------------------------------------------
# o monrad só enxerga um arquivo depois que o vol_sync.sh do 21.mvol (cron a cada
# 10 min) o grava no catalog.db.  Por isso:

# slot sem observação mais novo que (agora - carência) ainda não é "perdido":
# aparece como "Aguardando" (FUTURE) até o mvol ter tido tempo de registrá-lo
CI_PENDING_GRACE_MINUTES = 20

# sem NENHUMA observação nova no banco há mais que isto (3 ciclos do vol_sync),
# o painel avisa que a fonte pode estar parada
CI_SOURCE_STALE_MINUTES = 30

# painel de métricas (rsm_figure.py) ---------------------------------------------------

# taxa de sucesso (% no prazo) a partir da qual o card fica verde
CF_RATE_GOOD_PCT = 90
# taxa de sucesso a partir da qual o card fica âmbar (abaixo disso: vermelho)
CF_RATE_WARN_PCT = 75
# % de slots perdidos acima do qual a barra da estação ganha um alerta "⚠"
CF_MISSING_ALERT_PCT = 10

# estações -----------------------------------------------------------------------------
# lista MÍNIMA de estações, no formato "{sítio}-{alcance}".  Estas sempre
# aparecem no painel (100% perdido, se a estação estiver muda).  Estações novas,
# vistas no catalog.db, aparecem sozinhas, sem precisar editar esta lista.

CLST_STATIONS = [ "Belem-250",         "Belem-400",
                  "BoaVista-250",      "BoaVista-400",
                  "Cangucu-250",       "Cangucu-400",
                  "Gama-250",          "Gama-400",
                  "Macapa-250",        "Macapa-400",
                  "Manaus-250",        "Manaus-400",
                  "MorroDaIgreja-250", "MorroDaIgreja-400",
                  "PicoDoCouto-250",   "PicoDoCouto-400",
                  "Santiago-250",      "Santiago-400",
                  "SaoRoque-250",      "SaoRoque-400" ]

# < the end >──────────────────────────────────────────────────────────────────────────
