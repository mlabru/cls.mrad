# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_figure
renderizador do monitor de recepção radar, compartilhado por rsmPNG.py (PNG
estático) e rsmGUI.py (janela PyQt).

entrada: o documento de status gerado por rsmStatus.py
    { "source_last_update": "<ISO UTC>" | null,
      "stations": { "Belem-250": [(timestamp, código_status), ...], ... } }
    (stations_from_document e source_alert extraem as duas partes)
saída: uma matplotlib Figure com três painéis empilhados:
    1. grade estações x slots (cada célula pintada pela cor do status);
    2. barras empilhadas com o % de cada status por estação;
    3. cards de métricas gerais (total, no prazo, atrasados, perdidos, taxa).

não faz I/O nem depende de Qt -- por isso é testável sem display.

2026.out  mlabru  guia de manutenção: total "nunca zero" num lugar só
                  (_nonzero_total); percentuais por estação em
                  _station_percentages (eram 4 listas paralelas); geometria
                  dos cards e das barras em constantes nomeadas
2026.out  mlabru  banco como única fonte: stations_from_document,
                  source_alert (aviso de fonte parada) e build_figure(fs_alert)
2026.out  mlabru  refatoração para legibilidade: build_figure dividido em
                  _draw_status_grid, _draw_station_bars e _draw_metric_cards;
                  contagem por status num único lugar (_count_statuses);
                  ternário aninhado da cor da taxa vira _rate_color;
                  cap_window (recorte da janela, antes duplicado na GUI);
                  imports mortos removidos; movido para apps/work/
2025.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import collections
import datetime
import logging

# numpy
import numpy as np

# matplotlib
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches

from matplotlib.axes import Axes
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

# locals
import work.rsm_config as cfg

# < constants >────────────────────────────────────────────────────────────────────────

# tamanho da figura, em polegadas (largura, altura)
CT_FIGURE_SIZE = (20, 11)

# largura das barras do painel por estação
CF_BAR_WIDTH = 0.78
# o eixo Y das barras vai de 0 a 108%: sobra espaço acima dos 100% para o "⚠"
CF_BAR_ALERT_Y = 102
CF_BAR_Y_MAX = 108

# ordem de empilhamento das barras (de baixo para cima)
CLST_BAR_STATUSES = [cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL, cfg.CI_ST_MISS]

# card de métrica, em coordenadas do painel (0..1): largura e posição vertical
# de cada linha de texto
CF_CARD_WIDTH = 0.17
CF_CARD_LABEL_Y = 0.75
CF_CARD_VALUE_Y = 0.38
CF_CARD_FOOTNOTE_Y = 0.10

# status mostrados na legenda do grid (FUTURE fica de fora: é "vazio")
CLST_LEGEND_STATUSES = [cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL, cfg.CI_ST_MISS]

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────────────
def stations_from_document(fdct_document: dict) -> dict:
    """
    extrai o status por estação do documento gravado por rsmStatus.py.

    aceita também o formato antigo (o próprio dicionário de estações, sem a
    chave "stations"), para a GUI não quebrar com um JSON gravado antes da
    atualização -- o rsm_run.sh o regrava no ciclo seguinte.

    :param fdct_document: conteúdo do JSON de status
    :returns: {estação: [(timestamp, código_status), ...]}
    """
    if "stations" not in fdct_document:
        return fdct_document

    return fdct_document["stations"]

# ─────────────────────────────────────────────────────────────────────────────────────
def source_alert(fdct_document: dict, fdt_now_utc: datetime.datetime) -> str | None:
    """
    decide se o painel deve avisar que a fonte de dados pode estar parada.

    o monrad só vê o que o 21.mvol grava no catalog.db.  Se nenhuma
    observação nova entrou há mais de cfg.CI_SOURCE_STALE_MINUTES, os slots
    aparecem como perdidos sem que se saiba se a culpa é dos radares ou do
    mvol -- o aviso deixa isso explícito.

    :param fdct_document: conteúdo do JSON de status
    :param fdt_now_utc: instante atual, UTC, com fuso
    :returns: texto do aviso, ou None se a fonte está em dia (ou se o JSON é do
              formato antigo, que não traz essa informação)
    """
    if "source_last_update" not in fdct_document:
        return None

    ls_last_update = fdct_document["source_last_update"]

    if ls_last_update is None:
        return "⚠  catalog.db sem nenhuma observação registrada pelo 21.mvol"

    ldt_last_update = datetime.datetime.fromisoformat(ls_last_update)
    ldt_stale_limit = fdt_now_utc - datetime.timedelta(minutes=cfg.CI_SOURCE_STALE_MINUTES)

    if ldt_last_update >= ldt_stale_limit:
        return None

    return (f"⚠  catalog.db sem observações novas desde "
            f"{ldt_last_update:%Y-%m-%d %H:%M} UTC  "
            f"(21.mvol parado ou nenhuma estação enviando)")

# ─────────────────────────────────────────────────────────────────────────────────────
def cap_window(fdct_data: dict, fi_window_hours: int) -> tuple[dict, int, int]:
    """
    ajusta a janela pedida ao que realmente existe no JSON de status.

    o JSON guarda a janela com que rsmStatus.py rodou; quem desenha pode pedir
    outra (ex.: o spin box da GUI).  Esta função garante que título e grid
    falem da mesma janela.

    fluxo:
    1. slots pedidos = horas x slots por hora;
    2. limita ao número de slots disponível no arquivo;
    3. recalcula as horas a partir dos slots que sobraram;
    4. recorta cada estação para os slots MAIS RECENTES.

    :param fdct_data: status por estação, como gerado por rsmStatus.py
    :param fi_window_hours: janela pedida, em horas
    :returns: (dados recortados, número de slots, número de horas)
    :raises ValueError: JSON de status sem nenhuma estação
    """
    if not fdct_data:
        raise ValueError("JSON de status vazio (nenhuma estação)")

    # todas as estações têm o mesmo número de slots: basta olhar a primeira
    llst_first_station_slots = next(iter(fdct_data.values()))
    li_available_slots = len(llst_first_station_slots)

    li_requested_slots = fi_window_hours * cfg.CI_SLOTS_PER_HOUR
    li_total_slots = min(li_requested_slots, li_available_slots)
    li_window_hours = li_total_slots // cfg.CI_SLOTS_PER_HOUR

    ldct_capped = {}
    for ls_station, llst_slots in fdct_data.items():
        ldct_capped[ls_station] = llst_slots[-li_total_slots:]

    return ldct_capped, li_total_slots, li_window_hours

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_order(fdct_data: dict) -> list:
    """
    define a ordem das linhas (grid) e colunas (barras) das estações.

    primeiro as estações conhecidas, na ordem de cfg.CLST_STATIONS; depois
    qualquer outra presente nos dados (ex.: estação nova, descoberta pelo
    rsmStatus.py), em ordem alfabética.

    :param fdct_data: status por estação
    :returns: lista com os nomes das estações, na ordem de exibição
    """
    llst_known = [ls_station for ls_station in cfg.CLST_STATIONS
                  if ls_station in fdct_data]

    llst_new = sorted(ls_station for ls_station in fdct_data
                      if ls_station not in cfg.CLST_STATIONS)

    return llst_known + llst_new

# ─────────────────────────────────────────────────────────────────────────────────────
def _count_statuses(flst_slots: list) -> collections.defaultdict:
    """
    conta quantos slots há de cada status, ignorando os FUTURE.

    FUTURE (slot que ainda não venceu) não é sucesso nem falha, por isso não
    entra em nenhuma estatística.

    :param flst_slots: lista de (timestamp, código_status)
    :returns: dicionário {código_status: quantidade} (0 para códigos ausentes)
    """
    ldct_counts = collections.defaultdict(int)

    for _, li_status in flst_slots:
        if li_status == cfg.CI_ST_FUTURE:
            continue
        ldct_counts[li_status] += 1

    return ldct_counts

# ─────────────────────────────────────────────────────────────────────────────────────
def _nonzero_total(fdct_counts: dict) -> int:
    """
    soma as contagens de status, para servir de divisor nos percentuais.

    se só havia slots FUTURE a soma seria 0; devolve 1 nesse caso, para
    evitar divisão por zero (todos os percentuais saem 0%).

    :param fdct_counts: {código_status: quantidade}, como em _count_statuses
    :returns: a soma das quantidades, ou 1 se a soma for 0
    """
    li_total = sum(fdct_counts.values())

    if li_total == 0:
        return 1

    return li_total

# ─────────────────────────────────────────────────────────────────────────────────────
def aggregate_stats(fdct_data: dict) -> tuple[int, int, int, int, float]:
    """
    soma os status de todas as estações para o painel de métricas.

    :param fdct_data: status por estação
    :returns: (total, no_prazo, atrasados, perdidos, taxa_de_sucesso_%).
              total nunca é 0 (vale 1 quando só há FUTURE), para evitar
              divisão por zero nos percentuais
    """
    ldct_counts = collections.defaultdict(int)

    for llst_slots in fdct_data.values():
        for li_status, li_count in _count_statuses(llst_slots).items():
            ldct_counts[li_status] += li_count

    li_total = _nonzero_total(ldct_counts)

    li_on_time = ldct_counts[cfg.CI_ST_OK]
    li_delayed = ldct_counts[cfg.CI_ST_DS] + ldct_counts[cfg.CI_ST_DL]
    li_missing = ldct_counts[cfg.CI_ST_MISS]
    lf_success_rate = li_on_time / li_total * 100

    return li_total, li_on_time, li_delayed, li_missing, lf_success_rate

# ─────────────────────────────────────────────────────────────────────────────────────
def _rate_color(ff_success_rate: float) -> str:
    """
    escolhe a cor do card "Taxa de Sucesso".

    :param ff_success_rate: % de slots no prazo
    :returns: verde (>= 90%), âmbar (>= 75%) ou vermelho (abaixo disso)
    """
    if ff_success_rate >= cfg.CF_RATE_GOOD_PCT:
        return cfg.CS_C_OK

    if ff_success_rate >= cfg.CF_RATE_WARN_PCT:
        return cfg.CS_C_DELAY_S

    return cfg.CS_C_MISS

# ─────────────────────────────────────────────────────────────────────────────────────
def _hide_spines(fax: Axes) -> None:
    """
    esconde as bordas (spines) de um painel.

    :param fax: painel matplotlib
    """
    for l_spine in fax.spines.values():
        l_spine.set_visible(False)

# ─────────────────────────────────────────────────────────────────────────────────────
def _draw_status_grid(fax: Axes, fdct_data: dict, flst_stations: list,
                      fdt_ref_time: datetime.datetime, fi_total_slots: int,
                      fi_window_hours: int) -> None:
    """
    desenha o painel 1: a grade estações (linhas) x slots (colunas).

    fluxo:
    1. monta uma matriz de códigos de status (começa toda FUTURE);
    2. pinta a matriz com imshow, uma cor por código;
    3. marca uma linha vertical e um rótulo de horário a cada hora;
    4. escreve título e legenda.

    :param fax: painel onde desenhar
    :param fdct_data: status por estação
    :param flst_stations: estações, na ordem das linhas
    :param fdt_ref_time: instante de referência (o slot mais recente)
    :param fi_total_slots: número de colunas da grade
    :param fi_window_hours: janela em horas (só para o título)
    """
    li_station_count = len(flst_stations)

    # 1. matriz de status; slots além de fi_total_slots são ignorados
    lnp_matrix = np.full((li_station_count, fi_total_slots), cfg.CI_ST_FUTURE, dtype=float)

    for li_row, ls_station in enumerate(flst_stations):
        for li_col, (_, li_status) in enumerate(fdct_data[ls_station]):
            if li_col >= fi_total_slots:
                break
            lnp_matrix[li_row, li_col] = li_status

    # 2. uma cor por código de status (código = índice da cor)
    l_colormap = ListedColormap(cfg.CLST_STATUS_COLORS)
    li_highest_code = len(cfg.CLST_STATUS_COLORS) - 1

    fax.set_facecolor(cfg.CS_BG_DARK)
    fax.imshow(lnp_matrix, aspect="auto", cmap=l_colormap,
               vmin=0, vmax=li_highest_code, interpolation="nearest", origin="upper")

    # 3. linha vertical e rótulo de horário no início de cada hora
    llst_tick_positions = []
    llst_tick_labels = []

    for li_col in range(0, fi_total_slots, cfg.CI_SLOTS_PER_HOUR):
        # a última coluna é fdt_ref_time; cada coluna anterior é 1 slot antes
        li_slots_before_ref = fi_total_slots - 1 - li_col
        ldt_column_time = fdt_ref_time - datetime.timedelta(
                                  minutes=cfg.CI_SLOT_MINUTES * li_slots_before_ref)

        llst_tick_positions.append(li_col)
        llst_tick_labels.append(ldt_column_time.strftime("%H:%M"))
        fax.axvline(li_col - 0.5, color=cfg.CS_BG_DARK, lw=0.5, alpha=0.7)

    fax.set_xticks(llst_tick_positions)
    fax.set_xticklabels(llst_tick_labels, rotation=45, ha="right",
                        fontsize=6.5, color=cfg.CS_TEXT_SUB,
                        fontfamily="monospace")
    fax.set_yticks(range(li_station_count))
    fax.set_yticklabels(flst_stations,
                        fontsize=8.5, color=cfg.CS_TEXT_MAIN,
                        fontfamily="monospace")
    fax.tick_params(length=0, pad=5)

    _hide_spines(fax)

    # 4. título e legenda
    fax.set_title(f"  Grade de Recepção  ·"
                  f"  últimas {fi_window_hours}h  ·"
                  f"  {fi_total_slots} slots × {li_station_count} estações  ."
                  f"  ref: {fdt_ref_time.strftime('%Y-%m-%d %H:%M')}",
                  color=cfg.CS_TEXT_MAIN, fontsize=10, pad=10, loc="left",
                  fontfamily="monospace")

    llst_legend_patches = []
    for li_status in CLST_LEGEND_STATUSES:
        llst_legend_patches.append(mpatches.Patch(facecolor=cfg.CLST_STATUS_COLORS[li_status],
                                                  label=cfg.CLST_STATUS_LABELS[li_status],
                                                  edgecolor="none"))

    fax.legend(handles=llst_legend_patches, loc="upper right", frameon=True,
               facecolor=cfg.CS_BG_PANEL, edgecolor=cfg.CS_GRAY,
               labelcolor=cfg.CS_TEXT_MAIN, fontsize=8.5,
               ncol=4, columnspacing=1.2, handlelength=1.4)

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_percentages(flst_slots: list) -> dict:
    """
    calcula o % de cada status de UMA estação (FUTURE ignorado).

    :param flst_slots: lista de (timestamp, código_status) da estação
    :returns: {código_status: percentual 0..100} para cada status de
              CLST_BAR_STATUSES (0 para os ausentes)
    """
    ldct_counts = _count_statuses(flst_slots)
    li_station_total = _nonzero_total(ldct_counts)

    ldct_percentages = {}
    for li_status in CLST_BAR_STATUSES:
        ldct_percentages[li_status] = ldct_counts[li_status] / li_station_total * 100

    return ldct_percentages

# ─────────────────────────────────────────────────────────────────────────────────────
def _draw_station_bars(fax: Axes, fdct_data: dict, flst_stations: list) -> None:
    """
    desenha o painel 2: uma barra empilhada (100%) por estação.

    fluxo:
    1. calcula, por estação, o % de cada status (_station_percentages);
    2. empilha as barras na ordem de CLST_BAR_STATUSES (no prazo, atraso
       leve, atraso grave, perdido): cada uma começa onde a anterior terminou;
    3. marca com "⚠" as estações com mais de 10% de perdidos.

    :param fax: painel onde desenhar
    :param fdct_data: status por estação
    :param flst_stations: estações, na ordem das colunas
    """
    li_station_count = len(flst_stations)
    lnp_x = np.arange(li_station_count)

    # 1. percentuais: uma linha por estação
    llst_percentages = [_station_percentages(fdct_data[ls_station])
                        for ls_station in flst_stations]

    fax.set_facecolor(cfg.CS_BG_DARK)

    # 2. barras empilhadas; lnp_bottom é a altura já ocupada em cada coluna
    lnp_bottom = np.zeros(li_station_count)

    for li_status in CLST_BAR_STATUSES:
        lnp_heights = np.array([ldct_pct[li_status] for ldct_pct in llst_percentages])

        fax.bar(lnp_x, lnp_heights, bottom=lnp_bottom,
                color=cfg.CLST_STATUS_COLORS[li_status], width=CF_BAR_WIDTH)

        lnp_bottom = lnp_bottom + lnp_heights

    # 3. alerta nas estações com muitos perdidos
    for li_col, ldct_pct in enumerate(llst_percentages):
        if ldct_pct[cfg.CI_ST_MISS] > cfg.CF_MISSING_ALERT_PCT:
            fax.text(li_col, CF_BAR_ALERT_Y, "⚠", ha="center", va="bottom",
                     fontsize=8, color=cfg.CS_C_MISS)

    fax.set_xlim(-0.5, li_station_count - 0.5)
    fax.set_ylim(0, CF_BAR_Y_MAX)
    fax.set_xticks(lnp_x)
    fax.set_xticklabels(flst_stations, fontsize=7.5,
                        color=cfg.CS_TEXT_SUB, fontfamily="monospace")
    fax.set_yticks([0, 50, 100])
    fax.set_yticklabels(["0%", "50%", "100%"], fontsize=7, color=cfg.CS_TEXT_SUB)
    fax.tick_params(length=0)

    _hide_spines(fax)

    fax.set_title("  Breakdown por Estação", color=cfg.CS_TEXT_MAIN,
                  fontsize=9, pad=5, loc="left", fontfamily="monospace")

# ─────────────────────────────────────────────────────────────────────────────────────
def _draw_one_card(fax: Axes, ff_left: float, fs_label: str, fs_value: str,
                   fs_value_color: str, fs_footnote: str | None = None) -> None:
    """
    desenha um card de métrica: fundo arredondado, rótulo, valor e rodapé.

    :param fax: painel de métricas (coordenadas 0..1)
    :param ff_left: posição horizontal da borda esquerda do card (0..1)
    :param fs_label: rótulo, exibido em maiúsculas no topo
    :param fs_value: valor em destaque, no meio
    :param fs_value_color: cor do valor
    :param fs_footnote: texto pequeno no rodapé (opcional)
    """
    # o texto fica centralizado no card
    lf_center = ff_left + CF_CARD_WIDTH / 2

    fax.add_patch(mpatches.FancyBboxPatch(
        (ff_left, 0.05), CF_CARD_WIDTH, 0.9,
        boxstyle="round,pad=0.02",
        facecolor=cfg.CS_BG_CARD, edgecolor=cfg.CS_GRAY, linewidth=0.8,
        transform=fax.transAxes, zorder=1,
    ))

    fax.text(lf_center, CF_CARD_LABEL_Y, fs_label.upper(),
             ha="center", va="center", fontsize=7.5,
             color=cfg.CS_TEXT_SUB, fontfamily="monospace",
             transform=fax.transAxes, zorder=2)

    fax.text(lf_center, CF_CARD_VALUE_Y, fs_value,
             ha="center", va="center", fontsize=16, fontweight="bold",
             color=fs_value_color, fontfamily="monospace",
             transform=fax.transAxes, zorder=2)

    if fs_footnote is None:
        return

    fax.text(lf_center, CF_CARD_FOOTNOTE_Y, fs_footnote,
             ha="center", va="center", fontsize=7.5,
             color=cfg.CS_TEXT_SUB, fontfamily="monospace",
             transform=fax.transAxes, zorder=2)

# ─────────────────────────────────────────────────────────────────────────────────────
def _draw_metric_cards(fax: Axes, fdct_data: dict) -> None:
    """
    desenha o painel 3: cinco cards com as métricas gerais.

    :param fax: painel onde desenhar
    :param fdct_data: status por estação
    """
    li_total, li_on_time, li_delayed, li_missing, lf_success_rate = aggregate_stats(fdct_data)

    fax.set_facecolor(cfg.CS_BG_PANEL)
    fax.set_xlim(0, 1)
    fax.set_ylim(0, 1)
    fax.axis("off")

    _draw_one_card(fax, 0.01, "Total de Slots", f"{li_total:,}", cfg.CS_TEXT_MAIN)

    _draw_one_card(fax, 0.21, "No Prazo", f"{li_on_time:,}", cfg.CS_C_OK,
                   f"{li_on_time / li_total * 100:.1f}%")

    _draw_one_card(fax, 0.41, "Com Atraso", f"{li_delayed:,}", cfg.CS_C_DELAY_S,
                   f"{li_delayed / li_total * 100:.1f}%")

    _draw_one_card(fax, 0.61, "Perdidos", f"{li_missing:,}", cfg.CS_C_MISS,
                   f"{li_missing / li_total * 100:.1f}%")

    _draw_one_card(fax, 0.81, "Taxa de Sucesso", f"{lf_success_rate:.1f}%",
                   _rate_color(lf_success_rate), "(apenas no prazo)")

# ─────────────────────────────────────────────────────────────────────────────────────
def build_figure(fdct_data: dict, fdt_ref_time: datetime.datetime,
                 fi_total_slots: int, fi_window_hours: int,
                 fs_alert: str | None = None) -> Figure:
    """
    monta a figura completa do monitor.

    fluxo:
    1. define a ordem das estações;
    2. cria a figura com três painéis empilhados (grid, barras, cards);
    3. desenha cada painel;
    4. se houver aviso (fonte parada), escreve-o em vermelho no topo.

    :param fdct_data: status por estação ({estação: [(timestamp, status), ...]})
    :param fdt_ref_time: instante de referência (horário do slot mais recente)
    :param fi_total_slots: número de slots (colunas) a desenhar
    :param fi_window_hours: janela em horas (aparece no título)
    :param fs_alert: aviso sobre a fonte de dados (ver source_alert), ou None
    :returns: a Figure pronta (salvar com savefig ou embutir num canvas Qt)
    """
    llst_stations = _station_order(fdct_data)

    l_figure = Figure(figsize=CT_FIGURE_SIZE, facecolor=cfg.CS_BG_DARK)

    l_grid_spec = gridspec.GridSpec(3, 1, figure=l_figure,
                                    height_ratios=[5.5, 1.2, 1.5],
                                    hspace=0.35,
                                    left=0.055, right=0.985, top=0.91, bottom=0.07)

    lax_grid = l_figure.add_subplot(l_grid_spec[0])
    lax_bars = l_figure.add_subplot(l_grid_spec[1])
    lax_cards = l_figure.add_subplot(l_grid_spec[2])

    _draw_status_grid(lax_grid, fdct_data, llst_stations,
                      fdt_ref_time, fi_total_slots, fi_window_hours)
    _draw_station_bars(lax_bars, fdct_data, llst_stations)
    _draw_metric_cards(lax_cards, fdct_data)

    if fs_alert is not None:
        l_figure.text(0.5, 0.965, fs_alert, ha="center", va="center",
                      fontsize=12, fontweight="bold", color=cfg.CS_C_MISS,
                      fontfamily="monospace")

    return l_figure

# < the end >──────────────────────────────────────────────────────────────────────────
