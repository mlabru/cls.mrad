# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsmReport
testes do relatório de disponibilidade por período (rsmReport.py)

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import csv
import datetime

# pytest
import pytest

# locals
import rsmReport as rrp
import work.rsm_config as cfg

# < helpers >──────────────────────────────────────────────────────────────────────────

CDT_UTC = datetime.timezone.utc

# instante "agora" dos testes de período
CDT_NOW_UTC = datetime.datetime(2026, 11, 19, 12, 34, 56, tzinfo=CDT_UTC)

# dia do relatório nos testes com banco (bem no passado: tudo já venceu)
CDT_DAY = datetime.datetime(2026, 10, 5, tzinfo=CDT_UTC)


def _row(fs_station, fdt_file_time, ff_delay_seconds):
    """
    linha (fullpath, mtime) do banco: arquivo de fdt_file_time que chegou com
    o atraso pedido
    """
    ls_site, ls_range = fs_station.rsplit("-", 1)
    ls_fname = f"STI-{ls_range}--{fdt_file_time:%Y-%m-%d}--{fdt_file_time:%H-%M-%S}.mvol"

    return f"{ls_site}/{ls_range}/{ls_fname}", fdt_file_time.timestamp() + ff_delay_seconds


def _read_csv(fpth):
    """
    CSV do relatório como {estação: linha (dict)}
    """
    with open(fpth, encoding="utf-8", newline="") as l_file:
        return {ldct["estacao"]: ldct for ldct in csv.DictReader(l_file)}

# < período >──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fs_month, fs_next", [("2026-10", "2026-11-01"),
                                               ("2026-12", "2027-01-01"),
                                               ("2026-02", "2026-03-01")])
def test_month_period_ends_on_first_day_of_next_month(fs_month, fs_next):
    l_args = rrp.arg_parse(["-d", "x.db", "-m", fs_month])

    ldt_start, ldt_end = rrp.requested_period(l_args, CDT_NOW_UTC)

    assert ldt_start == datetime.datetime.strptime(fs_month, "%Y-%m").replace(tzinfo=CDT_UTC)
    assert ldt_end == datetime.datetime.strptime(fs_next, "%Y-%m-%d").replace(tzinfo=CDT_UTC)


def test_start_without_end_goes_until_now():
    l_args = rrp.arg_parse(["-d", "x.db", "--start", "2026-11-01"])

    assert rrp.requested_period(l_args, CDT_NOW_UTC)[1] == CDT_NOW_UTC


def test_end_requires_start(capsys):
    with pytest.raises(SystemExit):
        rrp.arg_parse(["-d", "x.db", "-m", "2026-10", "--end", "2026-10-10"])


def test_clip_period_to_current_slot_and_history_start(caplog):
    ldt_first_file = datetime.datetime(2026, 11, 3, 7, 44, 10, tzinfo=CDT_UTC)

    ldt_start, ldt_end = rrp.clip_period(datetime.datetime(2026, 11, 1, tzinfo=CDT_UTC),
                                         datetime.datetime(2026, 12, 1, tzinfo=CDT_UTC),
                                         ldt_first_file, CDT_NOW_UTC)

    assert ldt_start == datetime.datetime(2026, 11, 3, 7, 40, tzinfo=CDT_UTC)
    assert ldt_end == datetime.datetime(2026, 11, 19, 12, 30, tzinfo=CDT_UTC)
    assert "histórico do catalog.db começa" in caplog.text


def test_clip_period_inside_history_is_unchanged():
    ldt_start = datetime.datetime(2026, 10, 1, tzinfo=CDT_UTC)
    ldt_end = datetime.datetime(2026, 11, 1, tzinfo=CDT_UTC)

    assert rrp.clip_period(ldt_start, ldt_end, datetime.datetime(2026, 9, 1, tzinfo=CDT_UTC),
                           CDT_NOW_UTC) == (ldt_start, ldt_end)

# < summarize >────────────────────────────────────────────────────────────────────────

def test_summarize_counts_percentages_and_total():
    ldct_stations = {"Belem-250": [(0, cfg.CI_ST_OK), (1, cfg.CI_ST_DS), (2, cfg.CI_ST_MISS),
                                   (3, cfg.CI_ST_OK), (4, cfg.CI_ST_NOSRC)],
                     "Belem-400": [(0, cfg.CI_ST_DL), (1, cfg.CI_ST_OK), (2, cfg.CI_ST_OK),
                                   (3, cfg.CI_ST_OK), (4, cfg.CI_ST_FUTURE)]}

    llst_rows = rrp.summarize(ldct_stations)

    assert llst_rows[0] == ["Belem-250", 5, 4, 2, 1, 0, 1, "75.00", "50.00"]
    assert llst_rows[1] == ["Belem-400", 5, 4, 3, 0, 1, 0, "100.00", "75.00"]
    assert llst_rows[2] == [rrp.CS_TOTAL_LABEL, 10, 8, 5, 1, 1, 1, "87.50", "62.50"]


def test_summarize_nothing_judged_is_zero_percent():
    llst_rows = rrp.summarize({"Belem-250": [(0, cfg.CI_ST_NOSRC)]})

    assert llst_rows[0][-2:] == ["0.00", "0.00"]

# < main >─────────────────────────────────────────────────────────────────────────────

def test_main_reports_a_day_from_the_dbase(make_dbase, tmp_path):
    """
    um dia inteiro no passado: Belem-250 com metade dos slots no prazo, um
    atrasado demais e o resto perdido; as demais estações 100% perdidas
    """
    ls_station = "Belem-250"
    li_slots = 24 * cfg.CI_SLOTS_PER_HOUR
    li_on_time_max, li_small_max = cfg.CDCT_DELAY_LIMITS_BY_RANGE["250"]

    llst_rows = [_row(ls_station, CDT_DAY + datetime.timedelta(minutes=10 * li_slot, seconds=30),
                      li_on_time_max - 60)
                 for li_slot in range(0, li_slots, 2)]
    llst_rows.append(_row(ls_station, CDT_DAY + datetime.timedelta(minutes=10, seconds=30),
                          li_small_max + 60))
    lpth_dbase = make_dbase(llst_rows)
    lpth_out = tmp_path / "out.csv"

    li_rc = rrp.main(["-d", str(lpth_dbase), "--start", "2026-10-05",
                      "--end", "2026-10-06", "-o", str(lpth_out)])

    assert li_rc == 0
    ldct_csv = _read_csv(lpth_out)
    assert ldct_csv[ls_station] == {"estacao": ls_station, "slots": str(li_slots),
                                    "julgados": str(li_slots),
                                    "no_prazo": str(li_slots // 2), "atraso_leve": "0",
                                    "atraso_grave": "1", "perdidos": str(li_slots // 2 - 1),
                                    "recebidos_pct": "50.69", "no_prazo_pct": "50.00"}
    assert ldct_csv[cfg.CLST_STATIONS[1]]["perdidos"] == str(li_slots)
    assert rrp.CS_TOTAL_LABEL in ldct_csv


def test_main_ignores_maintenance_list(make_dbase, tmp_path, monkeypatch):
    """
    a lista de manutenção vale para agora, não para o período: no relatório
    a estação é julgada como as outras
    """
    ls_station = cfg.CLST_STATIONS[0]
    monkeypatch.setattr(cfg, "CLST_STATIONS_MAINTENANCE", frozenset((ls_station,)))
    lpth_dbase = make_dbase([_row(ls_station, CDT_DAY, 0)])
    lpth_out = tmp_path / "out.csv"

    rrp.main(["-d", str(lpth_dbase), "--start", "2026-10-05", "--end", "2026-10-06",
              "-o", str(lpth_out)])

    assert _read_csv(lpth_out)[ls_station]["perdidos"] == str(24 * cfg.CI_SLOTS_PER_HOUR - 1)


def test_main_period_before_history_returns_1(make_dbase, tmp_path, caplog):
    lpth_dbase = make_dbase([_row("Belem-250", CDT_DAY, 0)])
    lpth_out = tmp_path / "out.csv"

    li_rc = rrp.main(["-d", str(lpth_dbase), "-m", "2026-09", "-o", str(lpth_out)])

    assert li_rc == 1
    assert not lpth_out.exists()
    assert "período vazio" in caplog.text


def test_main_missing_dbase_returns_1(tmp_path):
    assert rrp.main(["-d", str(tmp_path / "nao_existe.db"), "-m", "2026-10"]) == 1
    assert not (tmp_path / "nao_existe.db").exists()


def test_main_writes_stdout_by_default(make_dbase, capsys):
    lpth_dbase = make_dbase([_row("Belem-250", CDT_DAY, 0)])

    assert rrp.main(["-d", str(lpth_dbase), "--start", "2026-10-05", "--end", "2026-10-06"]) == 0
    assert capsys.readouterr().out.startswith(",".join(rrp.CLST_CSV_HEADER) + "\n")


def test_main_does_not_change_the_dbase(make_dbase, tmp_path):
    lpth_dbase = make_dbase([_row("Belem-250", CDT_DAY, 0)])
    lby_before = lpth_dbase.read_bytes()

    rrp.main(["-d", str(lpth_dbase), "-m", "2026-10", "-o", str(tmp_path / "out.csv")])

    assert lpth_dbase.read_bytes() == lby_before

# < the end >──────────────────────────────────────────────────────────────────────────
