# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsmCheck
alarme da recepção radar: lê o JSON de status do rsmStatus.py e responde, em
uma linha e com o código de saída dos plugins do Nagios, se há algo a
notificar.  O PNG só ajuda quem olha para ele; este programa é para o
monitoramento (cron + notificação), chamado pelo rsm_check.sh.

regras (as mesmas contas do painel: work.rsm_stats):
- JSON ausente ou ilegível                                -> UNKNOWN  (3)
- JSON gerado há mais de --max-age min (monrad parado)    -> CRITICAL (2)
- catalog.db sem observação nova (fonte parada)           -> CRITICAL (2)
- estação muda: os últimos cfg.CI_ALERT_SILENT_SLOTS
  slots julgados são todos "perdido"                      -> CRITICAL (2)
- estação com perdas na janela acima de
  cfg.CF_MISSING_ALERT_PCT (o "⚠" da barra do painel)     -> WARNING  (1)
- senão                                                   -> OK       (0)
status fora das estatísticas (Aguardando, Sem fonte, Manutenção) nunca
disparam alarme de estação: uma estação em manutenção não alarma.

não guarda estado: enquanto o problema durar, cada execução o repete (quem
notifica decide a frequência), como o vol_check.sh do 21.mvol.

uso:
    python rsmCheck.py [-i STATUS.json] [--max-age MIN]

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import argparse
import datetime
import json
import sys

# locals
import work.rsm_config as cfg
import work.rsm_stats as rst

# < constants >────────────────────────────────────────────────────────────────────────

# códigos de saída (plugins do Nagios)
CI_EXIT_OK = 0
CI_EXIT_WARNING = 1
CI_EXIT_CRITICAL = 2
CI_EXIT_UNKNOWN = 3

# rótulo de cada código
CDCT_EXIT_LABELS = { CI_EXIT_OK:       "OK",
                     CI_EXIT_WARNING:  "WARNING",
                     CI_EXIT_CRITICAL: "CRITICAL",
                     CI_EXIT_UNKNOWN:  "UNKNOWN" }

# ─────────────────────────────────────────────────────────────────────────────────────
def arg_parse(flst_argv: list | None = None) -> argparse.Namespace:
    """
    lê os argumentos de linha de comando.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: namespace com inp e max_age
    """
    l_parser = argparse.ArgumentParser(description="Alarme da recepção radar (formato Nagios).")

    l_parser.add_argument("-i", "--inp", help="JSON de status (gerado por rsmStatus.py).",
                                         type=str, default="OUT.json")

    l_parser.add_argument("--max-age", help="idade máxima do JSON, em minutos.",
                                       type=int, default=cfg.CI_CHECK_MAX_AGE_MINUTES)

    return l_parser.parse_args(flst_argv)

# ─────────────────────────────────────────────────────────────────────────────────────
def _document_problems(fdct_document: dict, fdt_now_utc: datetime.datetime,
                       fi_max_age_minutes: int) -> list:
    """
    confere o próprio JSON (idade) e a fonte (catalog.db parado).

    :param fdct_document: conteúdo do JSON de status
    :param fdt_now_utc: instante atual, UTC
    :param fi_max_age_minutes: idade máxima do JSON, em minutos
    :returns: lista de textos, um por problema (vazia se tudo em dia)
    """
    llst_problems = []

    ldt_generated = rst.document_time(fdct_document, "generated_at")
    ldt_age_limit = fdt_now_utc - datetime.timedelta(minutes=fi_max_age_minutes)

    if ldt_generated is None or ldt_generated < ldt_age_limit:
        ls_when = "nunca" if ldt_generated is None else f"{ldt_generated:%Y-%m-%d %H:%M} UTC"
        llst_problems.append(f"JSON de status velho (gerado: {ls_when}; monrad parado?)")

    ldt_last_update = rst.document_time(fdct_document, "source_last_update")

    if rst.is_source_stale(ldt_last_update, fdt_now_utc):
        ls_when = "nunca" if ldt_last_update is None else f"{ldt_last_update:%Y-%m-%d %H:%M} UTC"
        llst_problems.append(f"catalog.db sem observação nova desde {ls_when} "
                             f"(21.mvol parado ou nenhuma estação enviando)")

    return llst_problems

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_problems(fdct_stations: dict) -> tuple[list, list]:
    """
    procura estações mudas (CRITICAL) e com perdas demais (WARNING).

    uma estação muda não entra também na lista de perdas: o problema dela já
    está dito, e mais forte.

    :param fdct_stations: {estação: [(timestamp, código_status), ...]}
    :returns: (estações mudas, estações com perdas), como textos curtos
    """
    llst_silent = []
    llst_lossy = []

    for ls_station in rst.station_order(fdct_stations):
        llst_slots = fdct_stations[ls_station]
        li_trailing = rst.trailing_miss_count(llst_slots)

        if li_trailing >= cfg.CI_ALERT_SILENT_SLOTS:
            llst_silent.append(f"{ls_station} ({li_trailing * cfg.CI_SLOT_MINUTES} min)")
            continue

        ldct_counts = rst.count_statuses(llst_slots)
        lf_miss_pct = rst.percent(ldct_counts[cfg.CI_ST_MISS], sum(ldct_counts.values()))

        if lf_miss_pct > cfg.CF_MISSING_ALERT_PCT:
            llst_lossy.append(f"{ls_station} ({lf_miss_pct:.0f}%)")

    return llst_silent, llst_lossy

# ─────────────────────────────────────────────────────────────────────────────────────
def evaluate(fdct_document: dict, fdt_now_utc: datetime.datetime,
             fi_max_age_minutes: int = cfg.CI_CHECK_MAX_AGE_MINUTES) -> tuple[int, str]:
    """
    avalia o documento de status e decide o código e a mensagem do alarme.

    fluxo:
    1. confere a idade do JSON e a fonte (_document_problems);
    2. confere cada estação (_station_problems);
    3. o código é o do problema mais grave; a mensagem junta todos.

    :param fdct_document: conteúdo do JSON de status
    :param fdt_now_utc: instante atual, UTC
    :param fi_max_age_minutes: idade máxima do JSON, em minutos
    :returns: (código de saída Nagios, mensagem de uma linha)
    """
    ldct_stations = rst.stations_from_document(fdct_document)

    if not ldct_stations:
        return CI_EXIT_UNKNOWN, "JSON de status sem nenhuma estação"

    llst_critical = _document_problems(fdct_document, fdt_now_utc, fi_max_age_minutes)
    llst_silent, llst_lossy = _station_problems(ldct_stations)

    if llst_silent:
        llst_critical.append(f"sem recepção: {', '.join(llst_silent)}")

    llst_messages = list(llst_critical)
    if llst_lossy:
        llst_messages.append(f"perdas > {cfg.CF_MISSING_ALERT_PCT}%: {', '.join(llst_lossy)}")

    if llst_critical:
        return CI_EXIT_CRITICAL, "; ".join(llst_messages)

    if llst_lossy:
        return CI_EXIT_WARNING, "; ".join(llst_messages)

    return CI_EXIT_OK, f"recepção em dia ({len(ldct_stations)} estações)"

# ─────────────────────────────────────────────────────────────────────────────────────
def main(flst_argv: list | None = None) -> int:
    """
    programa principal: lê o JSON, avalia e escreve uma linha em stdout.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: código de saída Nagios (0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN)
    """
    l_args = arg_parse(flst_argv)

    try:
        with open(l_args.inp, "r", encoding="utf-8") as l_file:
            ldct_document = json.load(l_file)

    except (OSError, ValueError) as l_err:
        print(f"UNKNOWN: JSON de status ilegível ({l_args.inp}): {l_err}")
        return CI_EXIT_UNKNOWN

    li_code, ls_message = evaluate(ldct_document, datetime.datetime.now(datetime.timezone.utc),
                                   l_args.max_age)

    print(f"{CDCT_EXIT_LABELS[li_code]}: {ls_message}")

    return li_code

# ─────────────────────────────────────────────────────────────────────────────────────
# this is the bootstrap process

if "__main__" == __name__:
    sys.exit(main())

# < the end >──────────────────────────────────────────────────────────────────────────
