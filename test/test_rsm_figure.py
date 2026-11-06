# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_figure
testes unitários de rsm_figure

2026.out  mlabru  _station_percentages (e o total "nunca zero")
2026.out  mlabru  stations_from_document, source_alert, build_figure com aviso
2026.out  mlabru  work.rsm_figure; testes de cap_window e _rate_color
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime

# pytest
import pytest

# matplotlib
from matplotlib.figure import Figure

# locals
import work.rsm_config as cfg
import work.rsm_figure as fig_mod

# < code >─────────────────────────────────────────────────────────────────────────────

def _make_data(flst_pattern):
    """
    monta um dict de dados (todas as estações com o mesmo padrão de status)
    """
    return {ls_station: [(None, li_status) for li_status in flst_pattern]
            for ls_station in cfg.CLST_STATIONS}


def test_aggregate_stats_counts_and_ignores_future():
    """
    aggregate_stats deve somar por status e ignorar slots FUTURE no total
    """
    llst_pattern = [cfg.CI_ST_OK, cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL,
                    cfg.CI_ST_MISS, cfg.CI_ST_FUTURE]
    ldct_data = _make_data(llst_pattern)
    li_n_st = len(cfg.CLST_STATIONS)

    li_total, li_ok, li_delayed, li_missing, lf_rate = fig_mod.aggregate_stats(ldct_data)

    assert li_total == li_n_st * 5     # FUTURE não entra na contagem
    assert li_ok == li_n_st * 2
    assert li_delayed == li_n_st * 2   # DS + DL
    assert li_missing == li_n_st * 1
    assert lf_rate == (li_ok / li_total) * 100


def test_aggregate_stats_avoids_division_by_zero_when_all_future():
    """
    quando só há slots FUTURE, o total não pode ser zero (evita ZeroDivisionError)
    """
    ldct_data = _make_data([cfg.CI_ST_FUTURE] * 3)

    li_total, li_ok, _, _, lf_rate = fig_mod.aggregate_stats(ldct_data)

    assert li_total == 1
    assert li_ok == 0
    assert lf_rate == 0



def test_station_percentages_ignore_future_and_sum_to_100():
    """
    _station_percentages calcula o % de cada status sem contar os FUTURE
    """
    llst_slots = [(None, li_status) for li_status in
                  [cfg.CI_ST_OK, cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_MISS, cfg.CI_ST_FUTURE]]

    ldct_pct = fig_mod._station_percentages(llst_slots)

    assert ldct_pct[cfg.CI_ST_OK] == 50
    assert ldct_pct[cfg.CI_ST_DS] == 25
    assert ldct_pct[cfg.CI_ST_DL] == 0
    assert ldct_pct[cfg.CI_ST_MISS] == 25
    assert sum(ldct_pct.values()) == 100


def test_station_percentages_all_future_gives_zero_without_error():
    """
    estação só com FUTURE: todos os percentuais 0 (sem ZeroDivisionError)
    """
    ldct_pct = fig_mod._station_percentages([(None, cfg.CI_ST_FUTURE)] * 4)

    assert all(lf_pct == 0 for lf_pct in ldct_pct.values())

def test_build_figure_returns_figure_with_three_axes():
    """
    build_figure deve retornar uma Figure válida com os 3 painéis (grid, barras, stats)
    """
    li_total_slots = 2 * 6
    llst_pattern = [cfg.CI_ST_OK, cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL,
                    cfg.CI_ST_MISS, cfg.CI_ST_FUTURE] * (li_total_slots // 6)
    ldct_data = _make_data(llst_pattern)
    ldt_ref = datetime.datetime(2026, 4, 12, 12, 0, 0)

    l_fig = fig_mod.build_figure(ldct_data, ldt_ref, li_total_slots, 2)

    assert isinstance(l_fig, Figure)
    assert len(l_fig.axes) == 3

    l_fig.clear()


def test_station_order_appends_unknown_stations_sorted_after_known():
    """
    _station_order mantém a ordem curada das estações conhecidas
    (cfg.CLST_STATIONS) primeiro, e acrescenta estações desconhecidas
    (ex.: descobertas dinamicamente) em ordem alfabética no final
    """
    ldct_data = _make_data([cfg.CI_ST_OK])
    ldct_data["Zulu-999"] = [(None, cfg.CI_ST_OK)]
    ldct_data["Alfa-111"] = [(None, cfg.CI_ST_OK)]

    llst_order = fig_mod._station_order(ldct_data)

    assert llst_order[:len(cfg.CLST_STATIONS)] == list(cfg.CLST_STATIONS)
    assert llst_order[len(cfg.CLST_STATIONS):] == ["Alfa-111", "Zulu-999"]


def test_build_figure_handles_unknown_station_without_error():
    """
    uma estação fora de cfg.CLST_STATIONS em "data" não deve quebrar a
    renderização (grid/barras/cards incluem essa estação normalmente)
    """
    ldct_data = _make_data([cfg.CI_ST_OK] * 6)
    ldct_data["EstacaoNova-300"] = [(None, cfg.CI_ST_OK)] * 6
    ldt_ref = datetime.datetime(2026, 4, 12, 12, 0, 0)

    l_fig = fig_mod.build_figure(ldct_data, ldt_ref, 6, 1)

    assert isinstance(l_fig, Figure)
    assert len(l_fig.axes[0].get_yticklabels()) == len(cfg.CLST_STATIONS) + 1

    l_fig.clear()


def test_build_figure_handles_all_ok_data_without_error():
    """
    caso trivial (tudo no prazo) não deve levantar exceção ao renderizar
    """
    ldct_data = _make_data([cfg.CI_ST_OK] * 6)
    ldt_ref = datetime.datetime(2026, 4, 12, 12, 0, 0)

    l_fig = fig_mod.build_figure(ldct_data, ldt_ref, 6, 1)

    assert isinstance(l_fig, Figure)

    l_fig.clear()

# < cap_window >───────────────────────────────────────────────────────────────────────

def test_cap_window_keeps_most_recent_slots():
    """
    janela menor que o arquivo: fica com os slots MAIS RECENTES (fim da lista)
    """
    ldct_data = {"A-250": [(li, cfg.CI_ST_OK) for li in range(24 * 6)]}

    ldct_out, li_slots, li_hours = fig_mod.cap_window(ldct_data, 2)

    assert (li_slots, li_hours) == (12, 2)
    assert [lt[0] for lt in ldct_out["A-250"]] == list(range(24 * 6 - 12, 24 * 6))


def test_cap_window_limits_to_available_slots():
    """
    janela maior que o arquivo: slots e horas ficam limitados ao disponível
    """
    ldct_data = {"A-250": [(li, cfg.CI_ST_OK) for li in range(6 * 6)]}

    _, li_slots, li_hours = fig_mod.cap_window(ldct_data, 72)

    assert (li_slots, li_hours) == (36, 6)


def test_cap_window_rejects_empty_data():
    """
    JSON sem estações é erro explícito (antes: StopIteration)
    """
    with pytest.raises(ValueError):
        fig_mod.cap_window({}, 24)

# < _rate_color >──────────────────────────────────────────────────────────────────────

def test_rate_color_thresholds():
    """
    verde a partir de 90%, âmbar a partir de 75%, vermelho abaixo
    """
    assert fig_mod._rate_color(90.0) == cfg.CS_C_OK
    assert fig_mod._rate_color(89.9) == cfg.CS_C_DELAY_S
    assert fig_mod._rate_color(75.0) == cfg.CS_C_DELAY_S
    assert fig_mod._rate_color(74.9) == cfg.CS_C_MISS

# < documento de status >─────────────────────────────────────────────────────────────

# instante "agora" usado nos testes de source_alert
CDT_NOW_UTC = datetime.datetime(2026, 10, 7, 12, 0, tzinfo=datetime.timezone.utc)


def test_stations_from_document_new_and_old_format():
    """
    formato novo: devolve "stations"; formato antigo: o próprio dicionário
    """
    ldct_stations = {"A-250": [(0, cfg.CI_ST_OK)]}

    assert fig_mod.stations_from_document({"source_last_update": None,
                                           "stations": ldct_stations}) == ldct_stations
    assert fig_mod.stations_from_document(ldct_stations) == ldct_stations


def test_source_alert_fresh_source_has_no_alert():
    """
    observação nova há menos de CI_SOURCE_STALE_MINUTES: sem aviso
    """
    ldt_recent = CDT_NOW_UTC - datetime.timedelta(minutes=cfg.CI_SOURCE_STALE_MINUTES - 1)

    assert fig_mod.source_alert({"source_last_update": ldt_recent.isoformat()},
                                CDT_NOW_UTC) is None


def test_source_alert_stale_source_shows_last_update():
    """
    sem observação nova há mais de CI_SOURCE_STALE_MINUTES: aviso com o horário
    """
    ldt_old = CDT_NOW_UTC - datetime.timedelta(minutes=cfg.CI_SOURCE_STALE_MINUTES + 1)

    ls_alert = fig_mod.source_alert({"source_last_update": ldt_old.isoformat()}, CDT_NOW_UTC)

    assert ls_alert is not None
    assert f"{ldt_old:%H:%M} UTC" in ls_alert


def test_source_alert_empty_dbase_and_old_format():
    """
    banco sem observação nenhuma: aviso; JSON antigo (sem a chave): sem aviso
    """
    assert fig_mod.source_alert({"source_last_update": None}, CDT_NOW_UTC) is not None
    assert fig_mod.source_alert({"A-250": []}, CDT_NOW_UTC) is None


def test_build_figure_draws_alert_text():
    """
    o aviso aparece como texto da figura
    """
    ldct_data = _make_data([cfg.CI_ST_MISS] * 6)

    l_fig = fig_mod.build_figure(ldct_data, datetime.datetime(2026, 4, 12, 12, 0), 6, 1,
                                 "⚠  fonte parada")

    assert "⚠  fonte parada" in [l_text.get_text() for l_text in l_fig.texts]

    l_fig.clear()

# < the end >──────────────────────────────────────────────────────────────────────────
