# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsmGUI
testes unitários de rsmGUI

2026.out  mlabru  JSON no formato novo (source_last_update + stations); alert
2026.out  mlabru  arg_parse (era args_parse); work.rsm_config
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import json
import sys

# PyQt
from PyQt5 import QtWidgets

# pytest
import pytest

# locals
import work.rsm_config as cfg
import rsmGUI

# < fixtures >─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def status_json_path(tmp_path):
    """
    escreve em disco um JSON de status (24h, todas as estações) e retorna o caminho,
    no mesmo formato produzido por rsmStatus.py
    """
    li_total_slots = 24 * 6
    llst_pattern = [cfg.CI_ST_OK, cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL,
                    cfg.CI_ST_MISS, cfg.CI_ST_FUTURE]
    llst_slots = [llst_pattern[li % len(llst_pattern)] for li in range(li_total_slots)]

    ldct_data = {ls_station: [[0, li_status] for li_status in llst_slots]
                for ls_station in cfg.CLST_STATIONS}

    lpth_file = tmp_path / "status.json"
    ldct_document = {"source_last_update": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "stations": ldct_data}

    lpth_file.write_text(json.dumps(ldct_document), encoding="utf-8")

    return str(lpth_file)

# < arg_parse >───────────────────────────────────────────────────────────────────────

def test_arg_parse_default_points_to_production_status_file(monkeypatch):
    """
    o default deve apontar para o mesmo caminho que rsm_run.sh grava
    (RSM_STATUS_JSON = data/temp/rsm_temp.json) - sem isso, rodar sem -i
    quebra com FileNotFoundError logo na inicialização
    """
    monkeypatch.setattr(sys, "argv", ["rsmGUI.py"])

    l_args = rsmGUI.arg_parse()

    assert l_args.inp == "data/temp/rsm_temp.json"


def test_arg_parse_override(monkeypatch):
    """
    -i/--inp explícito deve sobrescrever o default
    """
    monkeypatch.setattr(sys, "argv", ["rsmGUI.py", "-i", "outro.json"])

    l_args = rsmGUI.arg_parse()

    assert l_args.inp == "outro.json"

# < code >─────────────────────────────────────────────────────────────────────────────

def test_dashboard_builds_with_expected_defaults(qapp, status_json_path):
    """
    ao construir, o dashboard deve iniciar com janela de 24h e dados de todas
    as estações configuradas
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    assert l_dash.n_hours == 24
    assert l_dash.total_slots == 24 * 6
    assert set(l_dash.data.keys()) == set(cfg.CLST_STATIONS)

    l_dash.close()


def test_btn_style_embeds_given_color(qapp, status_json_path):
    """
    o stylesheet do botão deve conter a cor solicitada
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    ls_style = l_dash._btn_style("#ff0000")

    assert "#ff0000" in ls_style

    l_dash.close()


def test_refresh_applies_new_window_size_from_spinbox(qapp, status_json_path):
    """
    _refresh deve ler o valor do spinbox e regerar os dados/figura com a nova janela
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    l_dash._spin.setValue(6)
    l_dash._refresh()

    assert l_dash.n_hours == 6
    assert l_dash.total_slots == 6 * 6

    l_dash.close()


def test_refresh_caps_window_to_data_actually_available(qapp, status_json_path):
    """
    se a janela pedida exceder o que existe no JSON, total_slots (e n_hours,
    usado no título da figura) devem ficar limitados ao disponível - evita
    tanto estourar o índice da matriz em build_figure quanto um título
    divergente do grid renderizado
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    l_dash._spin.setValue(72)   # máximo do spinbox, acima das 24h do arquivo
    l_dash._refresh()

    assert l_dash.n_hours == 24
    assert l_dash.total_slots == 24 * 6

    l_dash.close()


def test_export_without_chosen_path_does_not_raise(qapp, status_json_path, monkeypatch):
    """
    se o usuário cancelar o diálogo de salvamento (path vazio), nada deve ser escrito
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))

    # não deve levantar exceção
    l_dash._export()

    l_dash.close()


def test_export_writes_png_when_path_given(qapp, status_json_path, tmp_path, monkeypatch):
    """
    ao escolher um caminho, _export deve salvar um PNG não vazio nesse caminho
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    ls_out = str(tmp_path / "out.png")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (ls_out, "")))

    l_dash._export()

    lpth_out = tmp_path / "out.png"
    assert lpth_out.exists()
    assert lpth_out.stat().st_size > 0

    l_dash.close()


def test_hline_spacer_has_fixed_width(qapp, status_json_path):
    """
    o espaçador horizontal deve ter largura fixa de 8px
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    l_frame = l_dash._hline_spacer()

    assert l_frame.width() == 8

    l_dash.close()

def test_dashboard_has_no_alert_when_source_is_fresh(qapp, status_json_path):
    """
    fonte atualizada agora: sem aviso de fonte parada
    """
    l_dash = rsmGUI.Dashboard(status_json_path)

    assert l_dash.alert is None

    l_dash.close()

# < the end >──────────────────────────────────────────────────────────────────────────
