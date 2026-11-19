# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsmReport
relatório de disponibilidade da recepção radar num período (ex.: um mês),
por estação, em CSV.  O painel só mostra as últimas 24 h e não guarda nada;
o catalog.db do 21.mvol guarda todo o histórico (nada apaga as linhas), e
este programa o resume.

a classificação é EXATAMENTE a do painel (rsmStatus.classify_period: mesmos
limiares, mesma carência) e as contas são as do work.rsm_stats, então o
relatório de um dia bate com o painel daquele dia.

diferenças em relação ao painel:
- a lista de manutenção (cfg.CLST_STATIONS_MAINTENANCE) NÃO é aplicada: ela
  diz quem está em manutenção AGORA, não no período;
- o período é recortado ao histórico do banco (antes do primeiro arquivo
  registrado o banco não sabe nada) e ao slot atual (o futuro não existe).

uso:
    python rsmReport.py -d catalog.db -m 2026-10 [-o outubro.csv]
    python rsmReport.py -d catalog.db --start 2026-10-01 --end 2026-10-08

saída (CSV, separador ",", uma linha por estação e uma linha TOTAL):
    estacao, slots, julgados, no_prazo, atraso_leve, atraso_grave, perdidos,
    recebidos_pct, no_prazo_pct
    julgados = slots fora de Aguardando/Sem fonte; recebidos_pct = (no prazo
    + atrasos) / julgados; no_prazo_pct = no prazo / julgados (a "taxa de
    sucesso" do painel).

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import argparse
import contextlib
import csv
import datetime
import logging
import sqlite3
import sys
import time

# locals
import rsmStatus as rst_status
import work.rsm_config as cfg
import work.rsm_dbase as dba
import work.rsm_files as fil
import work.rsm_stats as rst

# < constants >────────────────────────────────────────────────────────────────────────

# cabeçalho do CSV
CLST_CSV_HEADER = ["estacao", "slots", "julgados", "no_prazo", "atraso_leve",
                   "atraso_grave", "perdidos", "recebidos_pct", "no_prazo_pct"]

# rótulo da linha de soma de todas as estações
CS_TOTAL_LABEL = "TOTAL"

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────────────
def _utc_date(fs_text: str, fs_format: str) -> datetime.datetime:
    """
    lê uma data do argumento como meia-noite UTC.

    :param fs_text: texto da data
    :param fs_format: formato do strptime
    :returns: instante UTC com fuso
    """
    return datetime.datetime.strptime(fs_text, fs_format).replace(tzinfo=datetime.timezone.utc)

# ─────────────────────────────────────────────────────────────────────────────────────
def arg_parse(flst_argv: list | None = None) -> argparse.Namespace:
    """
    lê os argumentos de linha de comando.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: namespace com dbase, month, start, end e out
    """
    l_parser = argparse.ArgumentParser(
                  description="Disponibilidade da recepção radar num período, por estação (CSV).")

    l_parser.add_argument("-d", "--dbase", help="catalog.db do 21.mvol (somente leitura).",
                                           type=str, required=True)

    l_group = l_parser.add_mutually_exclusive_group(required=True)
    l_group.add_argument("-m", "--month", help="mês inteiro, AAAA-MM (UTC).",
                                          type=lambda fs: _utc_date(fs, "%Y-%m"))
    l_group.add_argument("--start", help="início do período, AAAA-MM-DD (UTC, inclusive).",
                                    type=lambda fs: _utc_date(fs, "%Y-%m-%d"))

    l_parser.add_argument("--end", help="fim do período, AAAA-MM-DD (UTC, exclusive; "
                                        "com --start; padrão: agora).",
                                   type=lambda fs: _utc_date(fs, "%Y-%m-%d"))

    l_parser.add_argument("-o", "--out", help="CSV de saída (padrão: stdout).",
                                         type=str, default="-")

    l_args = l_parser.parse_args(flst_argv)

    if l_args.end is not None and l_args.start is None:
        l_parser.error("--end só vale com --start")

    return l_args

# ─────────────────────────────────────────────────────────────────────────────────────
def requested_period(f_args: argparse.Namespace,
                     fdt_now_utc: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime]:
    """
    traduz os argumentos no período pedido [início, fim).

    :param f_args: argumentos (month, ou start e end)
    :param fdt_now_utc: instante atual, UTC (fim padrão de --start sem --end)
    :returns: (início, fim), UTC
    """
    if f_args.month is not None:
        # dia 28 + 4 dias cai sempre no mês seguinte
        ldt_next = (f_args.month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        return f_args.month, ldt_next

    if f_args.end is not None:
        return f_args.start, f_args.end

    return f_args.start, fdt_now_utc

# ─────────────────────────────────────────────────────────────────────────────────────
def clip_period(fdt_start: datetime.datetime, fdt_end: datetime.datetime,
                fdt_first_file: datetime.datetime | None,
                fdt_now_utc: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime]:
    """
    recorta o período ao que o banco pode responder.

    - fim: no máximo o início do slot atual (o slot aberto ainda não venceu);
    - início: no mínimo o slot do primeiro arquivo do banco (antes dele, todo
      slot sairia "perdido" sem que nada tenha sido observado).

    :param fdt_start: início pedido
    :param fdt_end: fim pedido
    :param fdt_first_file: horário do arquivo mais antigo do banco, ou None
    :param fdt_now_utc: instante atual, UTC
    :returns: (início, fim) recortados; início >= fim = nada a relatar
    """
    ldt_end = min(fdt_end, rst_status.round_down_to_slot(fdt_now_utc))
    ldt_start = fdt_start

    if fdt_first_file is not None:
        ldt_history_start = rst_status.round_down_to_slot(fdt_first_file)

        if ldt_start < ldt_history_start:
            M_LOG.warning("o histórico do catalog.db começa em %s UTC: o período foi "
                          "recortado (antes disso não há como julgar)",
                          f"{ldt_history_start:%Y-%m-%d %H:%M}")
            ldt_start = ldt_history_start

    return ldt_start, ldt_end

# ─────────────────────────────────────────────────────────────────────────────────────
def _summary_row(fs_label: str, fdct_counts: dict, fi_slots: int) -> list:
    """
    monta uma linha do CSV a partir das contagens de status.

    :param fs_label: estação (ou CS_TOTAL_LABEL)
    :param fdct_counts: {código_status: quantidade}, de rst.count_statuses
    :param fi_slots: total de slots (julgados ou não)
    :returns: valores na ordem de CLST_CSV_HEADER
    """
    li_judged = sum(fdct_counts.values())
    li_received = sum(fdct_counts[li_status] for li_status in rst.CSET_RECEIVED_STATUSES)

    return [fs_label, fi_slots, li_judged,
            fdct_counts[cfg.CI_ST_OK], fdct_counts[cfg.CI_ST_DS],
            fdct_counts[cfg.CI_ST_DL], fdct_counts[cfg.CI_ST_MISS],
            f"{rst.percent(li_received, li_judged):.2f}",
            f"{rst.percent(fdct_counts[cfg.CI_ST_OK], li_judged):.2f}"]

# ─────────────────────────────────────────────────────────────────────────────────────
def summarize(fdct_stations: dict) -> list:
    """
    resume o status de cada estação numa linha, mais a linha TOTAL.

    :param fdct_stations: {estação: [(timestamp, código_status), ...]}
    :returns: linhas do CSV (sem o cabeçalho), na ordem de exibição do painel
    """
    llst_rows = []
    ldct_total = rst.count_statuses([])
    li_total_slots = 0

    for ls_station in rst.station_order(fdct_stations):
        llst_slots = fdct_stations[ls_station]
        ldct_counts = rst.count_statuses(llst_slots)

        llst_rows.append(_summary_row(ls_station, ldct_counts, len(llst_slots)))

        for li_status, li_count in ldct_counts.items():
            ldct_total[li_status] += li_count
        li_total_slots += len(llst_slots)

    llst_rows.append(_summary_row(CS_TOTAL_LABEL, ldct_total, li_total_slots))

    return llst_rows

# ─────────────────────────────────────────────────────────────────────────────────────
def write_csv(fs_out: str, flst_rows: list) -> None:
    """
    grava o CSV (cabeçalho + linhas) num arquivo, de forma atômica, ou em stdout.

    :param fs_out: caminho do CSV, ou "-" para stdout
    :param flst_rows: linhas, na ordem de CLST_CSV_HEADER
    """
    if fs_out == "-":
        l_writer = csv.writer(sys.stdout, lineterminator="\n")
        l_writer.writerow(CLST_CSV_HEADER)
        l_writer.writerows(flst_rows)
        return

    with contextlib.ExitStack() as l_stack:
        lpth_tmp = l_stack.enter_context(fil.atomic_output(fs_out))
        l_file = l_stack.enter_context(open(lpth_tmp, "w", encoding="utf-8", newline=""))

        l_writer = csv.writer(l_file, lineterminator="\n")
        l_writer.writerow(CLST_CSV_HEADER)
        l_writer.writerows(flst_rows)

# ─────────────────────────────────────────────────────────────────────────────────────
def main(flst_argv: list | None = None) -> int:
    """
    programa principal.

    fluxo:
    1. traduz os argumentos no período pedido;
    2. recorta o período ao histórico do banco e ao agora;
    3. classifica o período como o painel (rsmStatus.classify_period, sem a
       lista de manutenção);
    4. resume por estação e grava o CSV.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: 0 (sucesso) ou 1 (banco indisponível, ou período vazio)
    """
    l_args = arg_parse(flst_argv)
    ldt_now_utc = datetime.datetime.now(datetime.timezone.utc)

    ldt_start, ldt_end = requested_period(l_args, ldt_now_utc)

    try:
        l_conn = dba.connect(l_args.dbase)
        try:
            ldt_first_file = dba.fetch_first_file_time(l_conn)
        finally:
            l_conn.close()

        ldt_start, ldt_end = clip_period(ldt_start, ldt_end, ldt_first_file, ldt_now_utc)

        if ldt_start >= ldt_end:
            M_LOG.error("período vazio depois do recorte (%s a %s UTC): nada a relatar",
                        f"{ldt_start:%Y-%m-%d %H:%M}", f"{ldt_end:%Y-%m-%d %H:%M}")
            return 1

        ldct_stations, _, ldt_last_update = rst_status.classify_period(
                                               l_args.dbase, ldt_start, ldt_end,
                                               ldt_now_utc, fb_use_maintenance=False)

    except sqlite3.OperationalError as l_err:
        M_LOG.error("catalog.db indisponível (%s): %s", l_args.dbase, l_err)
        return 1

    M_LOG.info("período relatado: %s a %s UTC",
               f"{ldt_start:%Y-%m-%d %H:%M}", f"{ldt_end:%Y-%m-%d %H:%M}")

    # depois da última observação o banco não julga nada: esses slots saem
    # "Sem fonte" e ficam fora de "julgados" -- avisa, para ninguém ler um
    # período parcial como completo
    if ldt_last_update is not None and ldt_last_update < ldt_end:
        M_LOG.warning("o catalog.db só tem observações até %s UTC: os slots seguintes "
                      "ficam fora dos julgados", f"{ldt_last_update:%Y-%m-%d %H:%M}")

    write_csv(l_args.out, summarize(ldct_stations))

    return 0

# ─────────────────────────────────────────────────────────────────────────────────────
# this is the bootstrap process

if "__main__" == __name__:
    # log em UTC, como os demais projetos cls (em stderr: o CSV pode ir para stdout)
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(datefmt="%Y/%m/%d %H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.INFO)

    sys.exit(main())

# < the end >──────────────────────────────────────────────────────────────────────────
