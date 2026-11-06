# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsmPNG
testes unitários de rsmPNG

2026.out  mlabru  JSON no formato novo (source_last_update + stations)
2026.out  mlabru  arg_parse (era args_parse); main retorna 0; JSON vazio
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import json
import sys

# locals
import work.rsm_config as cfg
import rsmPNG as png

# < arg_parse >───────────────────────────────────────────────────────────────────────

def test_arg_parse_defaults(monkeypatch):
    """
    valores default dos argumentos de linha de comando
    """
    monkeypatch.setattr(sys, "argv", ["rsmPNG.py"])

    l_args = png.arg_parse()

    assert l_args.inp == "OUT.json"
    assert l_args.out == "monrad.png"
    assert l_args.win == 24


def test_arg_parse_overrides(monkeypatch):
    """
    argumentos explícitos devem sobrescrever os defaults
    """
    monkeypatch.setattr(sys, "argv",
                        ["rsmPNG.py", "-i", "in.json", "-o", "out.png", "-w", "6"])

    l_args = png.arg_parse()

    assert l_args.inp == "in.json"
    assert l_args.out == "out.png"
    assert l_args.win == 6

# < main >─────────────────────────────────────────────────────────────────────────────

def test_main_reads_json_and_writes_png(tmp_path, monkeypatch):
    """
    fluxo completo: lê JSON de status e gera um PNG não vazio
    """
    li_total_slots = 2 * 6
    llst_pattern = [cfg.CI_ST_OK, cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL,
                    cfg.CI_ST_MISS, cfg.CI_ST_FUTURE] * (li_total_slots // 6)
    ldct_data = {ls_station: [[0, li_status] for li_status in llst_pattern]
                for ls_station in cfg.CLST_STATIONS}

    lpth_in = tmp_path / "in.json"
    ldct_document = {"source_last_update": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "stations": ldct_data}

    lpth_in.write_text(json.dumps(ldct_document), encoding="utf-8")

    lpth_out = tmp_path / "out.png"

    monkeypatch.setattr(sys, "argv",
                        ["rsmPNG.py", "-i", str(lpth_in), "-o", str(lpth_out), "-w", "2"])

    assert png.main() == 0

    assert lpth_out.exists()
    assert lpth_out.stat().st_size > 0

def test_main_returns_error_on_empty_json(tmp_path):
    """
    JSON de status vazio: rc 1, nenhum PNG gerado
    """
    lpth_in = tmp_path / "in.json"
    lpth_in.write_text("{}", encoding="utf-8")
    lpth_out = tmp_path / "out.png"

    assert png.main(["-i", str(lpth_in), "-o", str(lpth_out)]) == 1
    assert not lpth_out.exists()

def test_main_accepts_stale_source_and_old_format(tmp_path):
    """
    fonte parada (aviso desenhado) e JSON no formato antigo: PNG gerado
    """
    ldct_data = {ls_station: [[0, cfg.CI_ST_MISS]] * 6 for ls_station in cfg.CLST_STATIONS}

    for li_index, ldct_document in enumerate([{"source_last_update": None, "stations": ldct_data},
                                              ldct_data]):
        lpth_in = tmp_path / f"in{li_index}.json"
        lpth_in.write_text(json.dumps(ldct_document), encoding="utf-8")
        lpth_out = tmp_path / f"out{li_index}.png"

        assert png.main(["-i", str(lpth_in), "-o", str(lpth_out), "-w", "1"]) == 0
        assert lpth_out.stat().st_size > 0

# < the end >──────────────────────────────────────────────────────────────────────────
