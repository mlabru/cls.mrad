# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsmStatus
testes unitários de rsmStatus

2026.nov  mlabru  atraso medido do horário do arquivo; chegada antes dele = OK
2026.nov  mlabru  UTC com fuso (sem CDT_OFFSET_UTC): independe do fuso da
                  máquina; generated_at/last_slot; JSON gravado atômico
2026.out  mlabru  banco como única fonte: testes montam um catalog.db
                  (fixture make_dbase) em vez de uma listagem; carência,
                  descoberta de estação, source_last_update, banco ausente
2026.out  mlabru  nomes novos (classify_slot, load_listing_observations,
                  build_station_status); work.rsm_config
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import json
import os
import sqlite3
import time

# pytest
import pytest

# locals
import work.rsm_config as cfg
import rsmStatus as rs

# < constants >────────────────────────────────────────────────────────────────────────

# instante de referência usado nos testes de classify_slot
CDT_BASE = datetime.datetime(2026, 4, 12, 0, 0, 0, tzinfo=datetime.timezone.utc)

# < classify_slot >─────────────────────────────────────────────────────────────────────

# horário gravado no nome do arquivo: 8 min depois do início do slot (CDT_BASE)
CDT_FILE_TIME = CDT_BASE + datetime.timedelta(minutes=8)


def _received(ff_delay_minutes):
    """
    observação do slot CDT_BASE cujo arquivo (CDT_FILE_TIME) chegou com o
    atraso pedido, em minutos
    """
    ldt_arrival = CDT_FILE_TIME + datetime.timedelta(minutes=ff_delay_minutes)

    return {("Cangucu-250", CDT_BASE): (CDT_FILE_TIME, ldt_arrival)}, ldt_arrival


def test_classify_slot_missing_when_key_absent():
    """
    se o arquivo esperado não está no dict recebido, o status é MISS
    """
    lt_ts, li_status = rs.classify_slot({}, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_MISS
    assert lt_ts == CDT_BASE.timestamp()


def test_classify_slot_on_time_within_9_minutes():
    """
    chegada até 9 min após o horário do arquivo é considerada no prazo
    """
    ldct_received, ldt_arrival = _received(5)

    lt_ts, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_OK
    assert lt_ts == ldt_arrival.timestamp()


def test_classify_slot_delay_counts_from_file_time_not_slot_start():
    """
    arquivo das 00:08 que chega às 00:10 atrasou 2 min (no prazo), não 10 min
    a partir do início do slot (regressão: era classificado como atraso leve)
    """
    ldct_received, _ = _received(2)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_OK


def test_classify_slot_boundary_9_minutes_is_still_on_time():
    """
    exatamente 9 min de atraso ainda conta como no prazo (limite inclusive)
    """
    ldct_received, _ = _received(9)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_OK


def test_classify_slot_small_delay_between_9_and_20_minutes():
    """
    atraso entre 9 e 20 min é classificado como atraso pequeno (DS)
    """
    ldct_received, _ = _received(15)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_DS


def test_classify_slot_boundary_20_minutes_is_still_small_delay():
    """
    exatamente 20 min de atraso ainda conta como atraso pequeno (limite inclusive)
    """
    ldct_received, _ = _received(20)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_DS


def test_classify_slot_large_delay_over_20_minutes():
    """
    atraso acima de 20 min é classificado como atraso grande (DL)
    """
    ldct_received, _ = _received(25)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_DL


@pytest.mark.parametrize("ff_delay_minutes", [-1, -9, -15])
def test_classify_slot_arrival_before_file_time_is_on_time(ff_delay_minutes):
    """
    chegada antes do horário do arquivo (relógio do radar adiantado) conta
    como no prazo -- o arquivo chegou (antes saía FUTURE, escondido no painel)
    """
    ldct_received, _ = _received(ff_delay_minutes)

    _, li_status = rs.classify_slot(ldct_received, "Cangucu-250", CDT_BASE)

    assert li_status == cfg.CI_ST_OK

# < helpers >──────────────────────────────────────────────────────────────────────────

def _row_on_time(fs_station, fdt_expected_slot):
    """
    monta uma linha (fullpath, mtime) do banco cujo status resultante é OK
    para fdt_expected_slot (o mtime, epoch, cai exatamente no slot)
    """
    ls_site, ls_range = fs_station.rsplit("-", 1)
    lf_mtime = fdt_expected_slot.timestamp()

    ls_fname = (f"STI-{ls_range}--{fdt_expected_slot:%Y-%m-%d}"
                f"--{fdt_expected_slot:%H-%M-%S}.mvol")

    return f"{ls_site}/{ls_range}/{ls_fname}", lf_mtime


def _first_slot_of_window(fi_window_hours):
    """
    replica o cálculo interno do primeiro slot de uma janela de fi_window_hours
    """
    ldt_end = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
    ldt_start = ldt_end - datetime.timedelta(hours=fi_window_hours)
    li_min = (ldt_start.minute // cfg.CI_SLOT_MINUTES) * cfg.CI_SLOT_MINUTES
    return ldt_start.replace(minute=li_min, second=0, microsecond=0)

# < _parse_observation >───────────────────────────────────────────────────────────────

def test_parse_observation_extracts_station_and_rounds_to_10min_block():
    """
    o caminho gravado pelo mvol vira a chave sítio-alcance e o horário esperado
    (do nome do arquivo) é arredondado para o bloco de 10 min
    """
    lf_mtime = 1700000000.0

    lt_key, (ldt_file_time, ldt_arrival) = rs._parse_observation(
                              lf_mtime, "Cangucu/250/STI-250--2026-04-12--00-03-23.mvol")

    assert lt_key == ("Cangucu-250", datetime.datetime(2026, 4, 12, 0, 0, 0,
                                                       tzinfo=datetime.timezone.utc))
    # o horário exato do arquivo fica junto (o atraso é medido a partir dele)
    assert ldt_file_time == datetime.datetime(2026, 4, 12, 0, 3, 23,
                                              tzinfo=datetime.timezone.utc)
    # o mtime é epoch: 1700000000 = 2023-11-14 22:13:20 UTC, em qualquer fuso
    assert ldt_arrival == datetime.datetime(2023, 11, 14, 22, 13, 20,
                                            tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("fs_tz", ["UTC", "America/Sao_Paulo", "Asia/Tokyo"])
def test_parse_observation_does_not_depend_on_host_timezone(monkeypatch, fs_tz):
    """
    o resultado é o mesmo em qualquer fuso da máquina (antes só era certo em
    GMT-3, por causa do offset fixo de +3h)
    """
    monkeypatch.setenv("TZ", fs_tz)
    time.tzset()

    try:
        lt_key, (_, ldt_arrival) = rs._parse_observation(
                                  1776002603.0, "Cangucu/250/STI-250--2026-04-12--14-03-23.mvol")
    finally:
        monkeypatch.undo()
        time.tzset()

    assert lt_key[1] == datetime.datetime(2026, 4, 12, 14, 0, tzinfo=datetime.timezone.utc)
    assert ldt_arrival == datetime.datetime(2026, 4, 12, 14, 3, 23,
                                            tzinfo=datetime.timezone.utc)


def test_parse_observation_returns_none_for_malformed_rows():
    """
    nome fora do padrão ou mtime não numérico: observação ignorada
    """
    assert rs._parse_observation(1.0, "Cangucu/250/nome-invalido.mvol") is None
    assert rs._parse_observation("abc", "Cangucu/250/STI-250--2026-04-12--00-00-00.mvol") is None

# < build_station_status >─────────────────────────────────────────────────────────────

def test_build_station_status_empty_dbase_is_miss_except_grace_period(make_dbase):
    """
    banco vazio: todo slot é MISS, menos os dos últimos 20 min (carência do
    sync do mvol), que saem como FUTURE ("Aguardando")
    """
    li_window_hours = 10
    ldct_out = rs.build_station_status(str(make_dbase([])), li_window_hours)
    ldct_stations = ldct_out["stations"]

    assert set(ldct_stations.keys()) == set(cfg.CLST_STATIONS)

    for ls_station in cfg.CLST_STATIONS:
        llst_status = [li_status for _, li_status in ldct_stations[ls_station]]

        assert len(llst_status) == li_window_hours * 60 // cfg.CI_SLOT_MINUTES
        li_grace_slots = llst_status.count(cfg.CI_ST_FUTURE)
        # slots que COMEÇARAM há menos de 20 min: 1 ou 2, conforme o minuto atual
        assert 1 <= li_grace_slots <= 2
        assert llst_status[-li_grace_slots:] == [cfg.CI_ST_FUTURE] * li_grace_slots
        assert set(llst_status[:-li_grace_slots]) == {cfg.CI_ST_MISS}


def test_build_station_status_small_window_still_covers_full_requested_hours(make_dbase):
    """
    janela pequena (2h) gera todos os slots pedidos (regressão do offset duplicado)
    """
    ldct_out = rs.build_station_status(str(make_dbase([])), 2)

    for ls_station in cfg.CLST_STATIONS:
        assert len(ldct_out["stations"][ls_station]) == 2 * 60 // cfg.CI_SLOT_MINUTES


def test_build_station_status_matches_observation_to_ok_status(make_dbase):
    """
    uma observação gravada pelo mvol no horário esperado gera exatamente um OK
    """
    li_window_hours = 6
    ls_station = cfg.CLST_STATIONS[0]
    lpth = make_dbase([_row_on_time(ls_station, _first_slot_of_window(li_window_hours))])

    ldct_out = rs.build_station_status(str(lpth), li_window_hours)

    llst_ok = [s for _, s in ldct_out["stations"][ls_station] if s == cfg.CI_ST_OK]
    assert len(llst_ok) == 1


def test_build_station_status_discovers_new_station(make_dbase):
    """
    estação nunca vista (fora de cfg.CLST_STATIONS) aparece sozinha, depois
    das conhecidas
    """
    li_window_hours = 6
    ls_new_station = "EstacaoNova-300"
    lpth = make_dbase([_row_on_time(ls_new_station, _first_slot_of_window(li_window_hours))])

    ldct_stations = rs.build_station_status(str(lpth), li_window_hours)["stations"]

    assert list(ldct_stations.keys()) == list(cfg.CLST_STATIONS) + [ls_new_station]
    assert [s for _, s in ldct_stations[ls_new_station]].count(cfg.CI_ST_OK) == 1


def test_build_station_status_reports_generation_and_last_slot(make_dbase):
    """
    o documento diz quando foi gerado e qual é o slot da última coluna (o PNG
    rotula o eixo por ele); a última coluna é o slot anterior ao atual
    """
    ldt_before = datetime.datetime.now(datetime.timezone.utc)
    ldct_out = rs.build_station_status(str(make_dbase([])), 2)
    ldt_after = datetime.datetime.now(datetime.timezone.utc)

    ldt_generated = datetime.datetime.fromisoformat(ldct_out["generated_at"])
    ldt_last_slot = datetime.datetime.fromisoformat(ldct_out["last_slot"])

    assert ldt_before <= ldt_generated <= ldt_after
    assert ldt_last_slot.minute % cfg.CI_SLOT_MINUTES == 0
    assert ldt_last_slot.second == 0
    ldt_end = ldt_generated.replace(second=0, microsecond=0)
    assert ldt_end - datetime.timedelta(minutes=2 * cfg.CI_SLOT_MINUTES) < ldt_last_slot
    assert ldt_last_slot <= ldt_end - datetime.timedelta(minutes=cfg.CI_SLOT_MINUTES)


def test_build_station_status_slot_timestamps_are_utc_epochs(make_dbase):
    """
    o timestamp de cada slot MISS é o epoch do início do slot (antes saía 3h
    adiantado: datetime UTC sem fuso convertido como hora local)
    """
    ldct_out = rs.build_station_status(str(make_dbase([])), 1)
    llst_slots = ldct_out["stations"][cfg.CLST_STATIONS[0]]

    ldt_last_slot = datetime.datetime.fromisoformat(ldct_out["last_slot"])

    assert llst_slots[-1][0] == ldt_last_slot.timestamp()


def test_build_station_status_reports_source_last_update(make_dbase):
    """
    o documento traz o max(created_at) do banco (para o aviso de fonte parada)
    """
    lpth = make_dbase([("A/250/x.mvol", 1.0)], fs_created_at="2026-10-07T12:00:00+00:00")

    ldct_out = rs.build_station_status(str(lpth), 1)

    assert ldct_out["source_last_update"] == "2026-10-07T12:00:00+00:00"


def test_build_station_status_does_not_change_the_dbase(make_dbase):
    """
    o monrad só monitora e informa: o banco fica idêntico, byte a byte
    """
    lpth = make_dbase([("A/250/antiga.mvol", 1.0)])
    lby_before = lpth.read_bytes()

    rs.build_station_status(str(lpth), 6)

    assert lpth.read_bytes() == lby_before


def test_build_station_status_missing_dbase_raises(tmp_path):
    """
    sem o banco não há fonte: erro (e o arquivo não é criado)
    """
    lpth = tmp_path / "catalog.db"

    with pytest.raises(sqlite3.OperationalError):
        rs.build_station_status(str(lpth), 6)

    assert not lpth.exists()

# < main >─────────────────────────────────────────────────────────────────────────────

def test_main_writes_status_document(make_dbase, tmp_path):
    """
    fluxo completo: banco -> JSON com source_last_update e stations
    """
    lpth_out = tmp_path / "out.json"

    assert rs.main(["-d", str(make_dbase([])), "-w", "1", "-s", str(lpth_out)]) == 0

    ldct = json.loads(lpth_out.read_text(encoding="utf-8"))
    assert set(ldct.keys()) == {"generated_at", "last_slot", "source_last_update", "stations"}
    # gravação atômica: nenhum temporário sobra no diretório
    assert sorted(os.listdir(tmp_path)) == ["catalog.db", "out.json"]


def test_main_missing_dbase_returns_1_without_output(tmp_path):
    """
    banco inexistente: rc 1 e nenhum JSON (melhor que um painel 100% perdido)
    """
    lpth_out = tmp_path / "out.json"

    assert rs.main(["-d", str(tmp_path / "nao.db"), "-s", str(lpth_out)]) == 1
    assert not lpth_out.exists()


def test_arg_parse_requires_dbase():
    """
    -d é obrigatório: o banco é a única fonte
    """
    with pytest.raises(SystemExit):
        rs.arg_parse([])

# < the end >──────────────────────────────────────────────────────────────────────────
