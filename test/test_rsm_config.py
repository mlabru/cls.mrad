# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_config
testes unitários de rsm_config

2026.out  mlabru  work.rsm_config; limiares nomeados
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import re

# locals
import work.rsm_config as cfg

# < code >─────────────────────────────────────────────────────────────────────────────

def test_stations_are_unique_and_nonempty():
    """
    lista de estações não pode ser vazia nem ter duplicatas
    """
    assert len(cfg.CLST_STATIONS) > 0
    assert len(cfg.CLST_STATIONS) == len(set(cfg.CLST_STATIONS))


def test_status_codes_are_unique_sequential_indices():
    """
    os códigos de status devem formar um conjunto de índices 0..N-1 sem furos
    """
    lst_codes = [cfg.CI_ST_DL, cfg.CI_ST_DS, cfg.CI_ST_FUTURE,
                 cfg.CI_ST_MISS, cfg.CI_ST_OK]

    assert sorted(lst_codes) == list(range(len(lst_codes)))


def test_status_colors_and_labels_cover_every_status_code():
    """
    cada código de status deve ter uma cor e um label correspondentes
    """
    lst_codes = [cfg.CI_ST_DL, cfg.CI_ST_DS, cfg.CI_ST_FUTURE,
                 cfg.CI_ST_MISS, cfg.CI_ST_OK]

    assert len(cfg.CLST_STATUS_COLORS) == len(lst_codes)
    assert len(cfg.CLST_STATUS_LABELS) == len(lst_codes)

    for li_code in lst_codes:
        assert 0 <= li_code < len(cfg.CLST_STATUS_COLORS)
        assert 0 <= li_code < len(cfg.CLST_STATUS_LABELS)


def test_colors_are_valid_hex_strings():
    """
    todas as cores da paleta devem ser strings hexadecimais válidas (#RRGGBB)
    """
    lre_hex = re.compile(r"^#[0-9a-fA-F]{6}$")

    lst_colors = cfg.CLST_STATUS_COLORS + [cfg.CS_ACCENT, cfg.CS_BG_CARD,
                                           cfg.CS_BG_DARK, cfg.CS_BG_PANEL,
                                           cfg.CS_GRAY, cfg.CS_TEXT_MAIN,
                                           cfg.CS_TEXT_SUB]
    for ls_color in lst_colors:
        assert lre_hex.match(ls_color), f"cor inválida: {ls_color}"

def test_delay_thresholds_are_ordered():
    """
    o limite de "no prazo" vem antes do limite de "atraso pequeno"
    """
    assert 0 < cfg.CI_ON_TIME_MAX_SECONDS < cfg.CI_SMALL_DELAY_MAX_SECONDS


def test_slots_per_hour_matches_slot_size():
    """
    slots por hora coerente com o tamanho do slot
    """
    assert cfg.CI_SLOTS_PER_HOUR * cfg.CI_SLOT_MINUTES == 60

# < the end >──────────────────────────────────────────────────────────────────────────
