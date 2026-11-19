# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsmCheck
testes do alarme da recepção radar (rsmCheck.py, formato Nagios)

2026.nov  mlabru  frase da fonte comum com o PNG; caso do heartbeat do mvol
2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import json

# pytest
import pytest

# locals
import rsmCheck as rck
import work.rsm_config as cfg

# < helpers >──────────────────────────────────────────────────────────────────────────

# instante "agora" dos testes
CDT_NOW_UTC = datetime.datetime(2026, 11, 19, 12, 0, tzinfo=datetime.timezone.utc)

# slots por estação nos documentos de teste (24 h)
CI_SLOTS = 24 * cfg.CI_SLOTS_PER_HOUR


def _document(fdct_overrides=None, fi_age_minutes=0, fi_source_minutes=0):
    """
    documento de status com todas as estações 100% no prazo (e os 3 últimos
    slots "Aguardando"), gerado há fi_age_minutes e com a fonte atualizada há
    fi_source_minutes; fdct_overrides troca a lista de status de estações
    """
    llst_ok = [cfg.CI_ST_OK] * (CI_SLOTS - 3) + [cfg.CI_ST_FUTURE] * 3
    ldct_statuses = {ls_station: list(llst_ok) for ls_station in cfg.CLST_STATIONS}
    ldct_statuses.update(fdct_overrides or {})

    ldt_generated = CDT_NOW_UTC - datetime.timedelta(minutes=fi_age_minutes)
    ldt_source = CDT_NOW_UTC - datetime.timedelta(minutes=fi_source_minutes)

    return {"generated_at": ldt_generated.isoformat(),
            "last_slot": ldt_generated.isoformat(),
            "source_last_update": ldt_source.isoformat(),
            "stations": {ls_station: [[li_index, li_status]
                                      for li_index, li_status in enumerate(llst_statuses)]
                         for ls_station, llst_statuses in ldct_statuses.items()}}


def _with_tail(fi_status, fi_count, fb_future_tail=True):
    """
    lista de status 100% no prazo cujos fi_count últimos slots julgados são
    fi_status (seguidos de 3 "Aguardando", se fb_future_tail)
    """
    li_future = 3 if fb_future_tail else 0
    li_ok = CI_SLOTS - fi_count - li_future

    return [cfg.CI_ST_OK] * li_ok + [fi_status] * fi_count + [cfg.CI_ST_FUTURE] * li_future

# < evaluate >─────────────────────────────────────────────────────────────────────────

def test_everything_fine_is_ok():
    li_code, ls_msg = rck.evaluate(_document(), CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_OK
    assert f"{len(cfg.CLST_STATIONS)} estações" in ls_msg


def test_silent_station_is_critical():
    """
    os últimos CI_ALERT_SILENT_SLOTS slots julgados perdidos: estação muda,
    mesmo com os "Aguardando" do fim
    """
    ls_station = cfg.CLST_STATIONS[0]
    ldct_doc = _document({ls_station: _with_tail(cfg.CI_ST_MISS, cfg.CI_ALERT_SILENT_SLOTS)})

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert f"sem recepção: {ls_station} " in ls_msg


def test_short_gap_is_not_silent():
    """
    um slot a menos que CI_ALERT_SILENT_SLOTS: ainda não é estação muda (e a
    perda na janela é pequena: OK)
    """
    ls_station = cfg.CLST_STATIONS[0]
    ldct_doc = _document({ls_station: _with_tail(cfg.CI_ST_MISS,
                                                 cfg.CI_ALERT_SILENT_SLOTS - 1)})

    assert rck.evaluate(ldct_doc, CDT_NOW_UTC)[0] == rck.CI_EXIT_OK


def test_lossy_station_is_warning():
    """
    perdas acima de CF_MISSING_ALERT_PCT espalhadas (sem estação muda): WARNING
    """
    ls_station = cfg.CLST_STATIONS[1]
    # 1 perdido a cada 5 slots = 20%, nunca dois seguidos
    llst_statuses = [cfg.CI_ST_MISS if li % 5 == 0 else cfg.CI_ST_OK for li in range(CI_SLOTS)]

    li_code, ls_msg = rck.evaluate(_document({ls_station: llst_statuses}), CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_WARNING
    assert f"{ls_station} (20%)" in ls_msg


def test_silent_station_is_not_repeated_as_lossy():
    ls_station = cfg.CLST_STATIONS[0]
    ldct_doc = _document({ls_station: [cfg.CI_ST_MISS] * CI_SLOTS})

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "perdas" not in ls_msg


@pytest.mark.parametrize("fi_status", [cfg.CI_ST_MAINT, cfg.CI_ST_NOSRC, cfg.CI_ST_FUTURE])
def test_unjudged_statuses_never_alarm(fi_status):
    """
    estação em manutenção (ou sem fonte, ou aguardando) o dia inteiro: sem alarme
    """
    ldct_doc = _document({cfg.CLST_STATIONS[0]: [fi_status] * CI_SLOTS})

    assert rck.evaluate(ldct_doc, CDT_NOW_UTC)[0] == rck.CI_EXIT_OK


def test_stale_json_is_critical():
    """
    JSON mais velho que a idade máxima: o monrad parou de rodar
    """
    li_code, ls_msg = rck.evaluate(_document(fi_age_minutes=cfg.CI_CHECK_MAX_AGE_MINUTES + 1),
                                   CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "JSON de status velho" in ls_msg


def test_max_age_is_a_parameter():
    ldct_doc = _document(fi_age_minutes=45)

    assert rck.evaluate(ldct_doc, CDT_NOW_UTC, 60)[0] == rck.CI_EXIT_OK
    assert rck.evaluate(ldct_doc, CDT_NOW_UTC, 30)[0] == rck.CI_EXIT_CRITICAL


def test_stale_source_is_critical():
    ldct_doc = _document(fi_source_minutes=cfg.CI_SOURCE_STALE_MINUTES + 1)

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "catalog.db sem observações novas" in ls_msg


def test_silent_radars_with_mvol_running_say_so():
    """
    com o heartbeat do mvol recente, o alarme diz que as estações pararam (não
    "mvol parado ou estações")
    """
    ldct_doc = _document(fi_source_minutes=cfg.CI_SOURCE_STALE_MINUTES + 60)
    ldct_doc["source_heartbeat"] = CDT_NOW_UTC.isoformat()

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "as estações pararam de enviar" in ls_msg


def test_empty_dbase_is_critical():
    ldct_doc = _document()
    ldct_doc["source_last_update"] = None

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "sem nenhuma observação" in ls_msg


def test_critical_message_also_lists_warnings():
    llst_lossy = [cfg.CI_ST_MISS if li % 5 == 0 else cfg.CI_ST_OK for li in range(CI_SLOTS)]
    ldct_doc = _document({cfg.CLST_STATIONS[0]: [cfg.CI_ST_MISS] * CI_SLOTS,
                          cfg.CLST_STATIONS[1]: llst_lossy})

    li_code, ls_msg = rck.evaluate(ldct_doc, CDT_NOW_UTC)

    assert li_code == rck.CI_EXIT_CRITICAL
    assert "sem recepção" in ls_msg and "perdas" in ls_msg


def test_document_without_stations_is_unknown():
    assert rck.evaluate({"stations": {}}, CDT_NOW_UTC)[0] == rck.CI_EXIT_UNKNOWN

# < main >─────────────────────────────────────────────────────────────────────────────

def test_main_prints_label_and_returns_code(tmp_path, capsys):
    ldt_now = datetime.datetime.now(datetime.timezone.utc)
    ldct_doc = _document()
    ldct_doc["generated_at"] = ldt_now.isoformat()
    ldct_doc["source_last_update"] = ldt_now.isoformat()

    lpth = tmp_path / "status.json"
    lpth.write_text(json.dumps(ldct_doc), encoding="utf-8")

    assert rck.main(["-i", str(lpth)]) == rck.CI_EXIT_OK
    assert capsys.readouterr().out.startswith("OK: ")


@pytest.mark.parametrize("fs_content", [None, "{ não é json"])
def test_main_missing_or_broken_json_is_unknown(tmp_path, capsys, fs_content):
    lpth = tmp_path / "status.json"
    if fs_content is not None:
        lpth.write_text(fs_content, encoding="utf-8")

    assert rck.main(["-i", str(lpth)]) == rck.CI_EXIT_UNKNOWN
    assert capsys.readouterr().out.startswith("UNKNOWN: ")

# < the end >──────────────────────────────────────────────────────────────────────────
