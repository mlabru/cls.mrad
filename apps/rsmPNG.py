# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsmPNG
gera o PNG estático do monitor de recepção radar a partir do JSON de status
produzido por rsmStatus.py.

uso:
    python rsmPNG.py [-i STATUS.json] [-o SAIDA.png] [-w HORAS]

2026.out  mlabru  guia de manutenção: janela padrão vem do rsm_config
2026.out  mlabru  banco como única fonte: lê o documento novo (stations +
                  source_last_update) e desenha o aviso de fonte parada
2026.out  mlabru  refatoração para legibilidade: args_parse -> arg_parse;
                  janela recortada por rsm_figure.cap_window (a mesma regra
                  da GUI: slots mais recentes, título coerente com o grid);
                  JSON vazio vira erro com rc 1; print -> log em UTC
2025.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import argparse
import datetime
import json
import logging
import sys
import time

# locals
import work.rsm_config as cfg
import work.rsm_figure as fg

# < constants >────────────────────────────────────────────────────────────────────────

# resolução do PNG exportado
CI_PNG_DPI = 150

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────────────
def arg_parse(flst_argv: list | None = None) -> argparse.Namespace:
    """
    lê os argumentos de linha de comando.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: namespace com inp, out e win
    """
    l_parser = argparse.ArgumentParser(description="Monitor de Recepção Radar")

    l_parser.add_argument("-i", "--inp", help="JSON de status (gerado por rsmStatus.py).",
                                         type=str, default="OUT.json")

    l_parser.add_argument("-o", "--out", help="caminho do PNG de saída.",
                                         type=str, default="monrad.png")

    l_parser.add_argument("-w", "--win", help="janela de tempo em horas.",
                                         type=int, default=cfg.CI_DEFAULT_WINDOW_HOURS)

    return l_parser.parse_args(flst_argv)

# ─────────────────────────────────────────────────────────────────────────────────────
def load_status_json(fs_json_path: str) -> dict:
    """
    lê o JSON de status gerado por rsmStatus.py.

    :param fs_json_path: caminho do JSON
    :returns: documento de status (ver rsm_figure.stations_from_document)
    """
    with open(fs_json_path, "r", encoding="utf-8") as l_file:
        return json.load(l_file)

# ─────────────────────────────────────────────────────────────────────────────────────
def main(flst_argv: list | None = None) -> int:
    """
    programa principal.

    fluxo:
    1. lê o JSON de status e separa as estações;
    2. ajusta a janela pedida ao que existe no arquivo (cap_window);
    3. verifica se a fonte (catalog.db) está parada (source_alert);
    4. monta a figura e salva o PNG.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: 0 (sucesso) ou 1 (JSON de status vazio)
    """
    l_args = arg_parse(flst_argv)

    ldct_document = load_status_json(l_args.inp)
    ldct_status = fg.stations_from_document(ldct_document)

    if not ldct_status:
        M_LOG.error("JSON de status vazio: %s", l_args.inp)
        return 1

    ldct_window, li_total_slots, li_window_hours = fg.cap_window(ldct_status, l_args.win)

    ls_alert = fg.source_alert(ldct_document, datetime.datetime.now(datetime.timezone.utc))
    if ls_alert is not None:
        M_LOG.warning("%s", ls_alert)

    l_figure = fg.build_figure(ldct_window, datetime.datetime.now(),
                               li_total_slots, li_window_hours, ls_alert)

    l_figure.savefig(l_args.out, dpi=CI_PNG_DPI, bbox_inches="tight",
                     facecolor=cfg.CS_BG_DARK, edgecolor="none")

    M_LOG.info("PNG salvo em: %s", l_args.out)

    return 0

# ─────────────────────────────────────────────────────────────────────────────────────
# this is the bootstrap process

if "__main__" == __name__:
    # log em UTC, como os demais projetos met
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(datefmt="%Y/%m/%d %H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.INFO)

    sys.exit(main())

# < the end >──────────────────────────────────────────────────────────────────────────
