# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsmStatus
classifica a recepção dos arquivos radar (.mvol) de cada estação, slot a slot
(10 min), a partir do catalog.db do 21.mvol, e grava o resultado num JSON.

o banco é a ÚNICA fonte de dados do monrad: ele não acessa os .mvol nem o
servidor de onde eles vêm.  Quem lista o servidor e grava as observações
(vol_raw_observations) é o 21.mvol; o monrad só lê (mode=ro).

uso:
    python rsmStatus.py -d catalog.db [-w HORAS] [-s SAIDA.json]

saída:
    { "source_last_update": "<ISO UTC>" | null,
      "stations": { "Belem-250": [[timestamp, código_status], ...], ... } }

2026.out  mlabru  guia de manutenção: sem o apelido CI_STEP (usa
                  cfg.CI_SLOT_MINUTES); janela padrão vem do rsm_config;
                  tipos em _parse_observation
2026.out  mlabru  banco como única fonte: sem a listagem ssh/find (-d
                  obrigatório, sem argumento posicional); estações novas
                  sempre descobertas; carência para slots recentes (atraso do
                  sync do mvol); JSON com source_last_update (alerta de fonte
                  parada); banco ausente -> rc 1
2026.out  mlabru  refatoração para legibilidade: check_status -> classify_slot,
                  processa_lista_dados -> build_station_status; log em UTC
2026.out  mlabru  catalog.db só lido (rsm_dbase somente leitura)
2026.abr  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import argparse
import datetime
import json
import logging
import pathlib
import sqlite3
import sys
import time

# locals
import work.rsm_config as cfg
import work.rsm_dbase as dba

# < constants >────────────────────────────────────────────────────────────────────────

# diferença para converter hora local (GMT-3, sem horário de verão) em UTC.
# ATENÇÃO: offset fixo -- só é correto numa máquina configurada em GMT-3
CDT_OFFSET_UTC = datetime.timedelta(hours=3)

# folga, em horas, somada à janela na consulta ao catalog.db (evita cortar
# slots na borda por causa do offset local/UTC)
CI_DBASE_QUERY_MARGIN_HOURS = 6

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────────────
def arg_parse(flst_argv: list | None = None) -> argparse.Namespace:
    """
    lê os argumentos de linha de comando.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: namespace com dbase, hours e out
    """
    l_parser = argparse.ArgumentParser(
                  description="Classifica a recepção dos arquivos radar a partir do catalog.db.")

    l_parser.add_argument("-d", "--dbase", help="catalog.db do 21.mvol (somente leitura).",
                                           type=str, required=True)

    l_parser.add_argument("-w", "--hours", help="janela de horas a verificar.",
                                           type=int, default=cfg.CI_DEFAULT_WINDOW_HOURS)

    l_parser.add_argument("-s", "--out", help="arquivo JSON de saída.",
                                         type=pathlib.Path, default="OUT.json")

    return l_parser.parse_args(flst_argv)

# ─────────────────────────────────────────────────────────────────────────────────────
def classify_slot(fdct_observations: dict, fs_station: str,
                  fdt_slot: datetime.datetime) -> tuple[float, int]:
    """
    classifica um único slot de uma estação.

    regras (diferença = chegada real - horário esperado do slot):
    - arquivo não recebido        -> MISS
    - diferença negativa          -> FUTURE (chegou "antes": slot ainda aberto)
    - até 9 min (inclusive)       -> OK
    - até 20 min (inclusive)      -> DS (atraso pequeno)
    - acima de 20 min             -> DL (atraso grande)

    :param fdct_observations: {(estação, horário_esperado): horário_chegada}, UTC
    :param fs_station: estação, no formato "{sítio}-{alcance}"
    :param fdt_slot: horário esperado do slot (UTC, múltiplo de 10 min)
    :returns: (timestamp, código_status); o timestamp é o da chegada, ou o do
              próprio slot se o arquivo não foi recebido
    """
    lt_key = (fs_station, fdt_slot)

    if lt_key not in fdct_observations:
        return fdt_slot.timestamp(), cfg.CI_ST_MISS

    ldt_arrival = fdct_observations[lt_key]
    lf_delay_seconds = (ldt_arrival - fdt_slot).total_seconds()

    if lf_delay_seconds < 0:
        li_status = cfg.CI_ST_FUTURE
    elif lf_delay_seconds <= cfg.CI_ON_TIME_MAX_SECONDS:
        li_status = cfg.CI_ST_OK
    elif lf_delay_seconds <= cfg.CI_SMALL_DELAY_MAX_SECONDS:
        li_status = cfg.CI_ST_DS
    else:
        li_status = cfg.CI_ST_DL

    return ldt_arrival.timestamp(), li_status

# ─────────────────────────────────────────────────────────────────────────────────────
def _round_down_to_slot(fdt_time: datetime.datetime) -> datetime.datetime:
    """
    arredonda um horário para baixo, para o início do seu slot de 10 min.

    ex.: 00:03:23 -> 00:00:00; 00:17:59 -> 00:10:00

    :param fdt_time: horário qualquer
    :returns: o mesmo horário, com minutos múltiplos de 10 e segundos zerados
    """
    li_slot_minute = (fdt_time.minute // cfg.CI_SLOT_MINUTES) * cfg.CI_SLOT_MINUTES

    return fdt_time.replace(minute=li_slot_minute, second=0, microsecond=0)

# ─────────────────────────────────────────────────────────────────────────────────────
def _parse_observation(fs_mtime: str | float,
                       fs_filepath: str) -> tuple[tuple[str, datetime.datetime], datetime.datetime] | None:
    """
    interpreta uma observação bruta do banco (mtime, caminho do arquivo).

    é o ÚNICO lugar com a regra de negócio do parsing.  Só o TEXTO do caminho
    gravado pelo 21.mvol é interpretado; nenhum arquivo é acessado.

    fluxo:
    1. converte o mtime (epoch, hora local do servidor) para UTC (+3h);
    2. extrai sítio e alcance das duas pastas acima do arquivo;
    3. extrai do nome do arquivo o horário esperado
       (STI-250--2026-04-12--00-03-23.mvol -> 2026-04-12 00:03:23);
    4. arredonda o horário esperado para o início do slot de 10 min.

    :param fs_mtime: horário de modificação no servidor (epoch; str ou float)
    :param fs_filepath: caminho "{sítio}/{alcance}/{nome}.mvol"
    :returns: ((estação, horário_esperado), horário_chegada_utc), ou None se a
              observação estiver malformada (o motivo vai para o log)
    """
    try:
        ldt_arrival_local = datetime.datetime.fromtimestamp(float(fs_mtime))
        ldt_arrival_utc = ldt_arrival_local + CDT_OFFSET_UTC

        lpth_file = pathlib.PurePosixPath(fs_filepath)
        ls_site = lpth_file.parent.parent.name
        ls_range = lpth_file.parent.name
        ls_station = f"{ls_site}-{ls_range}"

        # "STI-250--2026-04-12--00-03-23" -> ["2026-04-12", "00-03-23"]
        llst_date_and_time = lpth_file.stem.split("--")[1:3]
        ldt_expected = datetime.datetime.strptime(
                          f"{llst_date_and_time[0]} {llst_date_and_time[1]}",
                          "%Y-%m-%d %H-%M-%S")

    except (ValueError, IndexError) as l_err:
        M_LOG.warning("observação ignorada (%s): mtime=%s path=%s",
                      l_err, fs_mtime, fs_filepath)
        return None

    return (ls_station, _round_down_to_slot(ldt_expected)), ldt_arrival_utc

# ─────────────────────────────────────────────────────────────────────────────────────
def _load_dbase(fs_dbase_path: str, fdt_now_local: datetime.datetime,
                fi_window_hours: int) -> tuple[dict, datetime.datetime | None]:
    """
    lê do catalog.db (somente leitura) as observações da janela e o instante
    da observação mais nova.

    a consulta é feita pelo mtime bruto, que está em hora LOCAL -- por isso
    os limites usam fdt_now_local, sem o offset UTC.

    :param fs_dbase_path: caminho do catalog.db
    :param fdt_now_local: instante atual, hora local
    :param fi_window_hours: janela pedida, em horas
    :returns: ({(estação, horário_esperado): horário_chegada}, última_atualização)
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    ldt_query_start = fdt_now_local - datetime.timedelta(
                                         hours=fi_window_hours + CI_DBASE_QUERY_MARGIN_HOURS)

    l_conn = dba.connect(fs_dbase_path)

    try:
        llst_rows = dba.fetch_observations(l_conn, ldt_query_start.timestamp(),
                                           fdt_now_local.timestamp())
        ldt_last_update = dba.fetch_last_update(l_conn)
    finally:
        l_conn.close()

    # se o mesmo slot aparecer mais de uma vez, vale a última linha lida
    ldct_observations = {}
    for ls_filepath, lf_mtime in llst_rows:
        lt_parsed = _parse_observation(lf_mtime, ls_filepath)
        if lt_parsed is None:
            continue

        lt_key, ldt_arrival_utc = lt_parsed
        ldct_observations[lt_key] = ldt_arrival_utc

    return ldct_observations, ldt_last_update

# ─────────────────────────────────────────────────────────────────────────────────────
def _list_stations(fdct_observations: dict) -> list:
    """
    decide quais estações entram no relatório.

    as estações de cfg.CLST_STATIONS entram sempre (mesmo sem nenhuma
    observação: 100% MISS).  Estações vistas no banco e ainda desconhecidas
    entram em seguida, em ordem alfabética.

    :param fdct_observations: {(estação, horário_esperado): horário_chegada}
    :returns: lista de estações
    """
    lset_seen = {ls_station for ls_station, _ in fdct_observations}
    llst_new = sorted(lset_seen - set(cfg.CLST_STATIONS))

    return list(cfg.CLST_STATIONS) + llst_new

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_slots(fdct_observations: dict, fs_station: str,
                   fdt_start_utc: datetime.datetime,
                   fdt_end_utc: datetime.datetime) -> list:
    """
    classifica todos os slots de 10 min de uma estação dentro da janela.

    carência: um slot sem observação e mais novo que (fim - 20 min) sai como
    FUTURE ("Aguardando"), não MISS -- o arquivo pode já ter chegado ao
    servidor sem que o 21.mvol (sync a cada 10 min) o tenha gravado no banco.

    :param fdct_observations: {(estação, horário_esperado): horário_chegada}
    :param fs_station: estação
    :param fdt_start_utc: início da janela (inclusive)
    :param fdt_end_utc: fim da janela (exclusive)
    :returns: lista de (timestamp, código_status), do slot mais antigo ao mais novo
    """
    ldt_pending_start = fdt_end_utc - datetime.timedelta(minutes=cfg.CI_PENDING_GRACE_MINUTES)

    llst_slots = []
    li_received_count = 0
    ldt_current = fdt_start_utc

    while ldt_current < fdt_end_utc:
        ldt_slot = _round_down_to_slot(ldt_current)
        lf_timestamp, li_status = classify_slot(fdct_observations, fs_station, ldt_slot)

        if li_status == cfg.CI_ST_MISS and ldt_slot >= ldt_pending_start:
            li_status = cfg.CI_ST_FUTURE

        if li_status in (cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL):
            li_received_count += 1

        llst_slots.append((lf_timestamp, li_status))
        ldt_current += datetime.timedelta(minutes=cfg.CI_SLOT_MINUTES)

    M_LOG.info("%d/%d registros válidos encontrados para %s.",
               li_received_count, len(llst_slots), fs_station)

    return llst_slots

# ─────────────────────────────────────────────────────────────────────────────────────
def build_station_status(fs_dbase_path: str,
                         fi_window_hours: int = cfg.CI_DEFAULT_WINDOW_HOURS) -> dict:
    """
    monta o status de recepção de todas as estações na janela pedida.

    fluxo:
    1. lê do catalog.db as observações da janela e a última atualização;
    2. decide a lista de estações (conhecidas + novas vistas no banco);
    3. calcula a janela [agora - horas, agora) em UTC;
    4. classifica cada slot de cada estação.

    :param fs_dbase_path: catalog.db do 21.mvol (só lido, nunca alterado)
    :param fi_window_hours: janela, em horas
    :returns: {"source_last_update": ISO UTC ou None,
               "stations": {estação: [(timestamp, código_status), ...]}}
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    # um único "agora" (hora local) para toda a rodada
    ldt_now_local = datetime.datetime.now()

    ldct_observations, ldt_last_update = _load_dbase(fs_dbase_path, ldt_now_local,
                                                     fi_window_hours)

    # a janela termina no minuto atual (segundos descartados), já em UTC
    ldt_end_utc = ldt_now_local.replace(second=0, microsecond=0) + CDT_OFFSET_UTC
    ldt_start_utc = ldt_end_utc - datetime.timedelta(hours=fi_window_hours)

    ldct_stations = {}
    for ls_station in _list_stations(ldct_observations):
        ldct_stations[ls_station] = _station_slots(ldct_observations, ls_station,
                                                   ldt_start_utc, ldt_end_utc)

    ls_last_update = None
    if ldt_last_update is not None:
        ls_last_update = ldt_last_update.isoformat()

    return {"source_last_update": ls_last_update, "stations": ldct_stations}

# ─────────────────────────────────────────────────────────────────────────────────────
def main(flst_argv: list | None = None) -> int:
    """
    programa principal: lê o banco, classifica e grava o JSON de status.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: 0 (sucesso) ou 1 (catalog.db inexistente ou ilegível)
    """
    l_args = arg_parse(flst_argv)

    try:
        ldct_status = build_station_status(l_args.dbase, l_args.hours)

    except sqlite3.OperationalError as l_err:
        # sem o banco não há fonte nenhuma: melhor falhar do que gravar 100% MISS
        M_LOG.error("catalog.db indisponível (%s): %s", l_args.dbase, l_err)
        return 1

    with open(l_args.out, "w", encoding="utf-8") as l_file:
        json.dump(ldct_status, l_file)

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
