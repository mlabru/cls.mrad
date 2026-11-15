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
    { "generated_at": "<ISO UTC>",          (quando este JSON foi gerado)
      "last_slot": "<ISO UTC>",             (início do slot da última coluna)
      "source_last_update": "<ISO UTC>" | null,
      "stations": { "Belem-250": [[timestamp, código_status], ...], ... } }

tudo é UTC, com fuso explícito: o mtime do banco é um epoch (não tem fuso) e
o horário no nome do arquivo é UTC.  Não depende do fuso da máquina.

2026.nov  mlabru  robustez: consulta pela coluna timestamp (horário do nome
                  do arquivo, a mesma base da regra de atraso; antes pelo
                  mtime, com 6h de folga); slot com mais de um arquivo fica
                  com a chegada MAIS CEDO (antes: "o último lido", sem ORDER
                  BY, logo não determinístico); estação fora de
                  CLST_STATIONS vai para o log como aviso (um caminho fora
                  do padrão no banco vira "estação nova" no painel)
2026.nov  mlabru  atraso = chegada - horário do NOME do arquivo (antes:
                  chegada - início do slot, o que somava o minuto do
                  arquivo dentro do slot e gerava ~99% dos "atrasos leves"
                  nos dados reais); chegada antes do horário do arquivo
                  (relógio do radar adiantado) conta como no prazo (antes:
                  FUTURE, escondido e fora das estatísticas).  Decisão do
                  usuário, 2026-11-14
2026.nov  mlabru  UTC com fuso de ponta a ponta: sai o CDT_OFFSET_UTC (+3h
                  fixo, só correto num host em GMT-3); o mtime é epoch e vira
                  UTC direto.  Os timestamps do JSON saem corretos (antes
                  eram datetimes UTC "ingênuos" convertidos como hora local:
                  3h a mais).  JSON ganha generated_at e last_slot, para o
                  PNG rotular o eixo pelo próprio JSON; gravação atômica
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
import collections
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
import work.rsm_files as fil

# < constants >────────────────────────────────────────────────────────────────────────

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

    regras (atraso = chegada no servidor - horário gravado no nome do arquivo;
    NÃO o início do slot: um arquivo das 12:08 que chega às 12:10 atrasou
    2 min, não 10):
    - arquivo não recebido        -> MISS
    - até 9 min (inclusive)       -> OK, inclusive atraso negativo (o relógio
                                     do radar está adiantado em relação ao do
                                     servidor, mas o arquivo chegou)
    - até 20 min (inclusive)      -> DS (atraso pequeno)
    - acima de 20 min             -> DL (atraso grande)

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}, UTC
    :param fs_station: estação, no formato "{sítio}-{alcance}"
    :param fdt_slot: horário esperado do slot (UTC com fuso, múltiplo de 10 min)
    :returns: (timestamp, código_status); o timestamp é o da chegada, ou o do
              próprio slot se o arquivo não foi recebido
    """
    lt_key = (fs_station, fdt_slot)

    if lt_key not in fdct_observations:
        return fdt_slot.timestamp(), cfg.CI_ST_MISS

    ldt_file_time, ldt_arrival = fdct_observations[lt_key]
    lf_delay_seconds = (ldt_arrival - ldt_file_time).total_seconds()

    if lf_delay_seconds <= cfg.CI_ON_TIME_MAX_SECONDS:
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
def _parse_observation(fs_mtime: str | float, fs_filepath: str) -> \
        tuple[tuple[str, datetime.datetime], tuple[datetime.datetime, datetime.datetime]] | None:
    """
    interpreta uma observação bruta do banco (mtime, caminho do arquivo).

    é o ÚNICO lugar com a regra de negócio do parsing.  Só o TEXTO do caminho
    gravado pelo 21.mvol é interpretado; nenhum arquivo é acessado.

    fluxo:
    1. converte o mtime (epoch: instante absoluto, sem fuso) para UTC;
    2. extrai sítio e alcance das duas pastas acima do arquivo;
    3. extrai do nome do arquivo o horário esperado, em UTC
       (STI-250--2026-04-12--00-03-23.mvol -> 2026-04-12 00:03:23 UTC);
    4. arredonda o horário do arquivo para o início do slot de 10 min (a
       chave); o horário exato fica junto, para medir o atraso.

    :param fs_mtime: horário de chegada no servidor (epoch; str ou float)
    :param fs_filepath: caminho "{sítio}/{alcance}/{nome}.mvol"
    :returns: ((estação, slot), (horário_do_arquivo, horário_chegada)), em UTC,
              ou None se a observação estiver malformada (o motivo vai
              para o log)
    """
    try:
        ldt_arrival_utc = datetime.datetime.fromtimestamp(float(fs_mtime),
                                                          tz=datetime.timezone.utc)

        lpth_file = pathlib.PurePosixPath(fs_filepath)
        ls_site = lpth_file.parent.parent.name
        ls_range = lpth_file.parent.name
        ls_station = f"{ls_site}-{ls_range}"

        # "STI-250--2026-04-12--00-03-23" -> ["2026-04-12", "00-03-23"]
        llst_date_and_time = lpth_file.stem.split("--")[1:3]
        ldt_file_time = datetime.datetime.strptime(
                          f"{llst_date_and_time[0]} {llst_date_and_time[1]}",
                          "%Y-%m-%d %H-%M-%S").replace(tzinfo=datetime.timezone.utc)

    except (ValueError, IndexError) as l_err:
        M_LOG.warning("observação ignorada (%s): mtime=%s path=%s",
                      l_err, fs_mtime, fs_filepath)
        return None

    return (ls_station, _round_down_to_slot(ldt_file_time)), (ldt_file_time, ldt_arrival_utc)

# ─────────────────────────────────────────────────────────────────────────────────────
def _load_dbase(fs_dbase_path: str, fdt_start_utc: datetime.datetime,
                fdt_end_utc: datetime.datetime) -> tuple[dict, datetime.datetime | None]:
    """
    lê do catalog.db (somente leitura) as observações da janela e o instante
    da observação mais nova.

    a consulta é pela coluna timestamp (horário do nome do arquivo, epoch
    UTC, gravado pelo 21.mvol): é o horário que decide a coluna e mede o
    atraso, então a janela do banco é exatamente a janela do painel, sem
    folga.

    :param fs_dbase_path: caminho do catalog.db
    :param fdt_start_utc: início da janela (inclusive), UTC com fuso
    :param fdt_end_utc: fim da janela (exclusive), UTC com fuso
    :returns: ({(estação, slot): (horário_do_arquivo, horário_chegada)}, última_atualização)
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    l_conn = dba.connect(fs_dbase_path)

    try:
        llst_rows = dba.fetch_observations(l_conn, fdt_start_utc.timestamp(),
                                           fdt_end_utc.timestamp())
        ldt_last_update = dba.fetch_last_update(l_conn)
    finally:
        l_conn.close()

    ldct_observations = {}
    for ls_filepath, lf_mtime in llst_rows:
        lt_parsed = _parse_observation(lf_mtime, ls_filepath)
        if lt_parsed is None:
            continue

        lt_key, lt_times = lt_parsed
        _keep_earliest_arrival(ldct_observations, lt_key, lt_times)

    return ldct_observations, ldt_last_update

# ─────────────────────────────────────────────────────────────────────────────────────
def _keep_earliest_arrival(fdct_observations: dict, ft_key: tuple, ft_times: tuple) -> None:
    """
    guarda a observação de um slot; se o slot já tem uma, fica a que chegou
    MAIS CEDO.

    dois arquivos no mesmo slot (ex.: radar reenviou, ou dois volumes no
    mesmo intervalo): o slot foi atendido pelo primeiro que chegou.  Decidir
    pela chegada, e não pela ordem das linhas, deixa o resultado igual em
    toda execução.

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}
    :param ft_key: (estação, slot)
    :param ft_times: (horário_do_arquivo, horário_chegada)
    """
    if ft_key in fdct_observations:
        _, ldt_kept_arrival = fdct_observations[ft_key]
        _, ldt_new_arrival = ft_times

        if ldt_kept_arrival <= ldt_new_arrival:
            return

    fdct_observations[ft_key] = ft_times

# ─────────────────────────────────────────────────────────────────────────────────────
def _list_stations(fdct_observations: dict) -> list:
    """
    decide quais estações entram no relatório.

    as estações de cfg.CLST_STATIONS entram sempre (mesmo sem nenhuma
    observação: 100% MISS).  Estações vistas no banco e ainda desconhecidas
    entram em seguida, em ordem alfabética.

    uma estação fora da lista vai para o log como aviso, com o número de
    slots em que apareceu: pode ser uma estação nova de verdade (basta
    incluí-la em CLST_STATIONS para o aviso parar) ou um caminho fora do
    padrão no banco (pasta com nome errado).

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}
    :returns: lista de estações
    """
    lset_known = set(cfg.CLST_STATIONS)
    lcnt_new = collections.Counter(ls_station for ls_station, _ in fdct_observations
                                   if ls_station not in lset_known)

    for ls_station, li_slot_count in sorted(lcnt_new.items()):
        M_LOG.warning("estação fora de CLST_STATIONS: %s (%d slots na janela) -- "
                      "estação nova ou caminho fora do padrão no catalog.db?",
                      ls_station, li_slot_count)

    return list(cfg.CLST_STATIONS) + sorted(lcnt_new)

# ─────────────────────────────────────────────────────────────────────────────────────
def _window_slots(fdt_start_utc: datetime.datetime,
                  fdt_end_utc: datetime.datetime) -> list:
    """
    lista os slots de 10 min da janela [início, fim), um por coluna do painel.

    anda de 10 em 10 min a partir do início e arredonda cada passo para o
    início do seu slot.  A janela tem horas inteiras, então são sempre
    horas x 6 slots.

    :param fdt_start_utc: início da janela (inclusive)
    :param fdt_end_utc: fim da janela (exclusive)
    :returns: lista de inícios de slot (UTC), do mais antigo ao mais novo
    """
    llst_slots = []
    ldt_current = fdt_start_utc

    while ldt_current < fdt_end_utc:
        llst_slots.append(_round_down_to_slot(ldt_current))
        ldt_current += datetime.timedelta(minutes=cfg.CI_SLOT_MINUTES)

    return llst_slots

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_slots(fdct_observations: dict, fs_station: str,
                   flst_slots: list, fdt_pending_start: datetime.datetime) -> list:
    """
    classifica todos os slots de 10 min de uma estação dentro da janela.

    carência: um slot sem observação que começou a partir de fdt_pending_start
    (fim da janela - 20 min) sai como FUTURE ("Aguardando"), não MISS -- o
    arquivo pode já ter chegado ao servidor sem que o 21.mvol (sync a cada
    10 min) o tenha gravado no banco.

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}
    :param fs_station: estação
    :param flst_slots: inícios de slot da janela (ver _window_slots)
    :param fdt_pending_start: início do período de carência
    :returns: lista de (timestamp, código_status), do slot mais antigo ao mais novo
    """
    llst_statuses = []
    li_received_count = 0

    for ldt_slot in flst_slots:
        lf_timestamp, li_status = classify_slot(fdct_observations, fs_station, ldt_slot)

        if li_status == cfg.CI_ST_MISS and ldt_slot >= fdt_pending_start:
            li_status = cfg.CI_ST_FUTURE

        if li_status in (cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL):
            li_received_count += 1

        llst_statuses.append((lf_timestamp, li_status))

    M_LOG.info("%d/%d registros válidos encontrados para %s.",
               li_received_count, len(llst_statuses), fs_station)

    return llst_statuses

# ─────────────────────────────────────────────────────────────────────────────────────
def build_station_status(fs_dbase_path: str,
                         fi_window_hours: int = cfg.CI_DEFAULT_WINDOW_HOURS) -> dict:
    """
    monta o status de recepção de todas as estações na janela pedida.

    fluxo:
    1. calcula a janela [agora - horas, agora) em UTC;
    2. lê do catalog.db as observações da janela e a última atualização;
    3. decide a lista de estações (conhecidas + novas vistas no banco);
    4. lista os slots da janela e classifica cada slot de cada estação.

    :param fs_dbase_path: catalog.db do 21.mvol (só lido, nunca alterado)
    :param fi_window_hours: janela, em horas
    :returns: {"generated_at": ISO UTC,
               "last_slot": ISO UTC (início do slot da última coluna) ou None,
               "source_last_update": ISO UTC ou None,
               "stations": {estação: [(timestamp, código_status), ...]}}
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    # um único "agora" para toda a rodada
    ldt_now_utc = datetime.datetime.now(datetime.timezone.utc)

    # a janela termina no minuto atual (segundos descartados)
    ldt_end_utc = ldt_now_utc.replace(second=0, microsecond=0)
    ldt_start_utc = ldt_end_utc - datetime.timedelta(hours=fi_window_hours)

    # o banco é lido a partir do início do PRIMEIRO slot (a janela pode
    # começar no meio de um)
    ldct_observations, ldt_last_update = _load_dbase(fs_dbase_path,
                                                     _round_down_to_slot(ldt_start_utc),
                                                     ldt_end_utc)

    llst_slots = _window_slots(ldt_start_utc, ldt_end_utc)
    ldt_pending_start = ldt_end_utc - datetime.timedelta(minutes=cfg.CI_PENDING_GRACE_MINUTES)

    ldct_stations = {}
    for ls_station in _list_stations(ldct_observations):
        ldct_stations[ls_station] = _station_slots(ldct_observations, ls_station,
                                                   llst_slots, ldt_pending_start)

    ls_last_update = None
    if ldt_last_update is not None:
        ls_last_update = ldt_last_update.isoformat()

    # janela de 0 h não tem slot nenhum
    ls_last_slot = None
    if llst_slots:
        ls_last_slot = llst_slots[-1].isoformat()

    return {"generated_at": ldt_now_utc.isoformat(),
            "last_slot": ls_last_slot,
            "source_last_update": ls_last_update,
            "stations": ldct_stations}

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

    # atômico: quem ler o JSON nunca pega um arquivo pela metade
    with fil.atomic_output(l_args.out) as lpth_tmp:
        with open(lpth_tmp, "w", encoding="utf-8") as l_file:
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
