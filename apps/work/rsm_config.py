# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_config
constantes do monitor de recepção radar: códigos de status, cores, rótulos,
limiares de atraso e a lista mínima de estações monitoradas.

é o único lugar onde esses valores são definidos; rsmStatus.py, rsm_figure.py,
rsmPNG.py e rsm_figure.py só os leem.

2026.nov  mlabru  aviso de relógio do radar adiantado (CI_CLOCK_AHEAD_*)
2026.nov  mlabru  limiares de atraso por alcance (CDCT_DELAY_LIMITS_BY_RANGE:
                  250 km = 10/20 min, 400 km = 3/10 min; decisão do
                  usuário, 2026-11-17): o 250 km leva 5-8 min de varredura,
                  o 400 km ~1 min, e um limiar único de 9 min não via
                  atraso no 400 km; rótulos dos atrasos sem minutos
2026.nov  mlabru  estação em manutenção (CLST_STATIONS_MAINTENANCE,
                  CI_ST_MAINT): slot sem arquivo não é cobrado dela
2026.nov  mlabru  status "sem fonte" (CI_ST_NOSRC): slot sem arquivo que o
                  21.mvol, parado, ainda não poderia ter registrado não é
                  culpa do radar -- sai das estatísticas em vez de virar MISS
2026.nov  mlabru  comentários sem a GUI PyQt (removida); o atraso dos
                  limiares conta do horário do NOME do arquivo
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
CS_C_DELAY_L = "#db6d28"   # laranja  - atraso grande
CS_C_DELAY_S = "#d29922"   # âmbar    - atraso pequeno
CS_C_MISS    = "#f85149"   # vermelho - perdido
CS_C_OK      = "#3fb950"   # verde    - chegou no prazo
# slot que ainda não venceu: mesma cor do fundo dos cards, para "sumir" no grid
CS_C_FUTURE  = CS_BG_CARD
# cinza   - sem fonte (o 21.mvol parou de registrar; não dá para julgar o radar)
CS_C_NOSRC   = "#6e7681"
# cinza escuro - estação em manutenção (desligada de propósito: não é falha)
CS_C_MAINT   = "#484f58"

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
CI_ST_NOSRC  = 5   # sem fonte: o 21.mvol parou antes de poder registrar o arquivo
CI_ST_MAINT  = 6   # estação em manutenção (CLST_STATIONS_MAINTENANCE), sem arquivo

# cor de cada status, indexada pelo código
CLST_STATUS_COLORS = [ CS_C_DELAY_L,      # CI_ST_DL
                       CS_C_DELAY_S,      # CI_ST_DS
                       CS_C_FUTURE,       # CI_ST_FUTURE
                       CS_C_MISS,         # CI_ST_MISS
                       CS_C_OK,           # CI_ST_OK
                       CS_C_NOSRC,        # CI_ST_NOSRC
                       CS_C_MAINT ]       # CI_ST_MAINT

# rótulo de cada status, indexado pelo código
# (os atrasos não citam minutos: os limiares dependem do alcance)
CLST_STATUS_LABELS = [ "Atraso grave",              # CI_ST_DL
                       "Atraso leve",               # CI_ST_DS
                       "Aguardando",                # CI_ST_FUTURE
                       "Perdido",                   # CI_ST_MISS
                       "No prazo",                  # CI_ST_OK
                       "Sem fonte (mvol)",          # CI_ST_NOSRC
                       "Manutenção" ]               # CI_ST_MAINT

# grade de tempo -----------------------------------------------------------------------

# cada estação envia um arquivo a cada 10 minutos (um "slot")
CI_SLOT_MINUTES = 10
# slots em uma hora (6)
CI_SLOTS_PER_HOUR = 60 // CI_SLOT_MINUTES

# janela padrão do monitor, em horas (rsmStatus e rsmPNG começam nela)
CI_DEFAULT_WINDOW_HOURS = 24

# limiares de atraso (chegada no servidor - horário do NOME do arquivo, em segundos) --
# (não o início do slot: ver rsmStatus.classify_slot)
# até o 1º limite (inclusive): no prazo -- atraso negativo (relógio do radar
# adiantado) também; até o 2º (inclusive): atraso pequeno; acima: atraso grande

# por alcance (a parte "{alcance}" da estação): {alcance: (no prazo, atraso pequeno)}.
# O nome do arquivo traz o INÍCIO da varredura, então o atraso normal inclui a
# duração dela: no 250 km, 5-8 min (mediana 348 s, p99 503 s em 2026-11); no
# 400 km, ~1 min (mediana 65 s, p99 86 s).  Os limites acompanham esse normal.
CDCT_DELAY_LIMITS_BY_RANGE = { "250": (10 * 60, 20 * 60),
                               "400": ( 3 * 60, 10 * 60) }

# alcance fora da tabela acima (estação nova): limites padrão
CI_ON_TIME_MAX_SECONDS = 9 * 60
CI_SMALL_DELAY_MAX_SECONDS = 20 * 60

# relógio do radar adiantado ----------------------------------------------------------
# chegada ANTES do horário do nome conta como "no prazo" (o arquivo chegou), mas
# esconde o atraso real: com o relógio 4 min adiantado, um atraso de 7 min
# aparece como 3.  Se a MEDIANA do atraso da estação na janela fica abaixo de
# -CI_CLOCK_AHEAD_WARN_SECONDS, o rsmStatus avisa no log (não muda o status)

# mediana do atraso abaixo de -1 min: relógio adiantado (a mediana, e não um
# arquivo só, para um caso isolado não disparar o aviso)
CI_CLOCK_AHEAD_WARN_SECONDS = 60
# mínimo de arquivos da estação na janela para avaliar (1 h de envios)
CI_CLOCK_AHEAD_MIN_FILES = 6

# atraso da fonte (21.mvol) ------------------------------------------------------------
# o monrad só enxerga um arquivo depois que o vol_sync.sh do 21.mvol (cron a cada
# 10 min) o grava no catalog.db.  Por isso:

# tempo, contado do início do slot, que o mvol leva para registrar o arquivo.
# Slot sem observação só vira "perdido" (MISS) se o mvol registrou algo DEPOIS
# disso (max(created_at) >= início + carência); antes, é "Aguardando" (FUTURE)
# ou, com a fonte parada, "Sem fonte" (NOSRC) -- ver rsmStatus._unseen_status
CI_PENDING_GRACE_MINUTES = 20

# sem NENHUMA observação nova no banco há mais que isto (3 ciclos do vol_sync),
# a fonte é dada como parada: o painel avisa e os slots que o mvol não chegou a
# cobrir saem como "Sem fonte"
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

# estações em manutenção (ou desativadas): continuam no painel, mas um slot sem
# arquivo sai "Manutenção" (CI_ST_MAINT), fora das estatísticas, em vez de
# "Perdido".  Se um arquivo chegar, ele é classificado normalmente.  Cada
# estação tem de estar em CLST_STATIONS; anote o motivo e a data ao incluir, e
# tire-a daqui quando voltar a operar -- senão uma falha real fica escondida.
#   ex.: "Macapa-250",   # radar em reforma desde 2026-08 (OS 1234)
CLST_STATIONS_MAINTENANCE = frozenset((
))

# < the end >──────────────────────────────────────────────────────────────────────────
