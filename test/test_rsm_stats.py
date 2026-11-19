# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_stats
testes das contas sobre o JSON de status (work.rsm_stats), comuns ao PNG, ao
alarme (rsmCheck.py) e ao relatório (rsmReport.py)

2026.nov  mlabru  initial version (Linux/Python): inclui os testes de
                  station_order e stations_from_document vindos do
                  test_rsm_figure.py
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import os
import pathlib
import subprocess
import sys

# pytest
import pytest

# locals
import work.rsm_config as cfg
import work.rsm_stats as rst

# < helpers >──────────────────────────────────────────────────────────────────────────

# raiz do projeto (onde está apps/)
MPTH_ROOT = pathlib.Path(__file__).resolve().parent.parent

# instante "agora" dos testes
CDT_NOW_UTC = datetime.datetime(2026, 11, 19, 12, 0, tzinfo=datetime.timezone.utc)


def _slots(*fi_statuses):
    """
    lista de (timestamp, status) a partir dos códigos de status
    """
    return [(li_index, li_status) for li_index, li_status in enumerate(fi_statuses)]

# < testes >───────────────────────────────────────────────────────────────────────────

def test_alarm_modules_do_not_import_matplotlib():
    """
    o alarme (rsmCheck.py) usa este módulo e precisa rodar com a pilha gráfica
    do virtualenv quebrada (como em 2026-10): nem matplotlib nem numpy
    """
    ls_code = ("import sys, rsmCheck, work.rsm_stats; "
               "print(sorted(m for m in ('matplotlib', 'numpy') if m in sys.modules))")
    ldct_env = dict(os.environ, PYTHONPATH=str(MPTH_ROOT / "apps"))

    lproc = subprocess.run([sys.executable, "-c", ls_code], capture_output=True,
                           text=True, env=ldct_env, check=True)

    assert lproc.stdout.strip() == "[]"


def test_station_order_appends_unknown_stations_sorted_after_known():
    """
    estações conhecidas na ordem curada (cfg.CLST_STATIONS), depois as
    desconhecidas (ex.: descobertas no banco) em ordem alfabética
    """
    ldct_data = {ls_station: [] for ls_station in cfg.CLST_STATIONS}
    ldct_data["Zulu-999"] = []
    ldct_data["Alfa-111"] = []

    llst_order = rst.station_order(ldct_data)

    assert llst_order[:len(cfg.CLST_STATIONS)] == list(cfg.CLST_STATIONS)
    assert llst_order[len(cfg.CLST_STATIONS):] == ["Alfa-111", "Zulu-999"]


def test_stations_from_document_new_and_old_format():
    """
    formato novo: devolve "stations"; formato antigo: o próprio dicionário
    """
    ldct_stations = {"A-250": [(0, cfg.CI_ST_OK)]}

    assert rst.stations_from_document({"source_last_update": None,
                                       "stations": ldct_stations}) == ldct_stations
    assert rst.stations_from_document(ldct_stations) == ldct_stations


def test_count_statuses_ignores_unjudged():
    ldct_counts = rst.count_statuses(_slots(cfg.CI_ST_OK, cfg.CI_ST_MISS, cfg.CI_ST_FUTURE,
                                            cfg.CI_ST_NOSRC, cfg.CI_ST_MAINT, cfg.CI_ST_OK))

    assert dict(ldct_counts) == {cfg.CI_ST_OK: 2, cfg.CI_ST_MISS: 1}
    # código ausente vale 0
    assert ldct_counts[cfg.CI_ST_DL] == 0


def test_percent_of_nothing_is_zero():
    assert rst.percent(0, 0) == 0.0
    assert rst.percent(1, 4) == 25.0


@pytest.mark.parametrize("flst_statuses, fi_expected", [
    ([cfg.CI_ST_OK, cfg.CI_ST_MISS, cfg.CI_ST_MISS], 2),
    # os "Aguardando" do fim são pulados, sem interromper a contagem
    ([cfg.CI_ST_MISS, cfg.CI_ST_MISS, cfg.CI_ST_FUTURE, cfg.CI_ST_FUTURE], 2),
    ([cfg.CI_ST_MISS, cfg.CI_ST_NOSRC, cfg.CI_ST_MISS], 2),
    ([cfg.CI_ST_MISS, cfg.CI_ST_DL], 0),
    ([cfg.CI_ST_MAINT, cfg.CI_ST_MAINT], 0),
    ([], 0),
])
def test_trailing_miss_count(flst_statuses, fi_expected):
    assert rst.trailing_miss_count(_slots(*flst_statuses)) == fi_expected


@pytest.mark.parametrize("fi_minutes_ago, fb_stale", [
    (cfg.CI_SOURCE_STALE_MINUTES - 1, False),
    (cfg.CI_SOURCE_STALE_MINUTES, False),
    (cfg.CI_SOURCE_STALE_MINUTES + 1, True),
])
def test_is_source_stale(fi_minutes_ago, fb_stale):
    ldt_last = CDT_NOW_UTC - datetime.timedelta(minutes=fi_minutes_ago)

    assert rst.is_source_stale(ldt_last, CDT_NOW_UTC) is fb_stale


def test_is_source_stale_without_any_observation():
    assert rst.is_source_stale(None, CDT_NOW_UTC) is True


def test_document_time_missing_or_null_key():
    assert rst.document_time({}, "generated_at") is None
    assert rst.document_time({"generated_at": None}, "generated_at") is None
    assert rst.document_time({"generated_at": CDT_NOW_UTC.isoformat()},
                             "generated_at") == CDT_NOW_UTC

# < the end >──────────────────────────────────────────────────────────────────────────
