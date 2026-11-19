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

2026.nov  mlabru  núcleo classify_period(início, fim, agora), também usado
                  pelo rsmReport.py (disponibilidade de um período); carência
                  de 40 min (cfg.CI_PENDING_GRACE_MINUTES, medida no banco)
2026.nov  mlabru  aviso no log de relógio do radar adiantado
                  (_warn_clock_ahead): mediana do atraso negativa esconde o
                  atraso real, já que chegada antecipada conta como no prazo
2026.nov  mlabru  limiares de atraso por alcance (_delay_limits,
                  cfg.CDCT_DELAY_LIMITS_BY_RANGE): 250 km = 10/20 min,
                  400 km = 3/10 min; outro alcance, o padrão 9/20
2026.nov  mlabru  estação em manutenção (cfg.CLST_STATIONS_MAINTENANCE): slot
                  sem arquivo sai CI_ST_MAINT, não MISS/FUTURE/NOSRC
2026.nov  mlabru  status "sem fonte" (CI_ST_NOSRC): slot sem observação só é
                  MISS se o mvol registrou algo depois do prazo do slot
                  (max(created_at) >= início + carência); senão é FUTURE
                  com a fonte em dia, ou NOSRC com ela parada (antes: MISS,
                  e uma parada do mvol era cobrada dos radares)
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
import statistics
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
def _delay_limits(fs_station: str) -> tuple[int, int]:
    """
    devolve os limiares de atraso da estação, conforme o seu alcance.

    ex.: "Cangucu-250" -> cfg.CDCT_DELAY_LIMITS_BY_RANGE["250"]; um alcance fora
    da tabela (estação nova) usa os limites padrão.

    :param fs_station: estação, no formato "{sítio}-{alcance}"
    :returns: (máximo no prazo, máximo atraso pequeno), em segundos
    """
    ls_range = fs_station.rsplit("-", 1)[-1]
    lt_default = (cfg.CI_ON_TIME_MAX_SECONDS, cfg.CI_SMALL_DELAY_MAX_SECONDS)

    return cfg.CDCT_DELAY_LIMITS_BY_RANGE.get(ls_range, lt_default)

# ─────────────────────────────────────────────────────────────────────────────────────
def classify_slot(fdct_observations: dict, fs_station: str,
                  fdt_slot: datetime.datetime) -> tuple[float, int]:
    """
    classifica um único slot de uma estação.

    regras (atraso = chegada no servidor - horário gravado no nome do arquivo;
    NÃO o início do slot: um arquivo das 12:08 que chega às 12:10 atrasou
    2 min, não 10).  Os limites dependem do alcance (_delay_limits; 250 km:
    10/20 min, 400 km: 3/10 min, outro: 9/20 min):
    - arquivo não recebido        -> MISS
    - até o 1º limite (inclusive) -> OK, inclusive atraso negativo (o relógio
                                     do radar está adiantado em relação ao do
                                     servidor, mas o arquivo chegou)
    - até o 2º limite (inclusive) -> DS (atraso pequeno)
    - acima do 2º limite          -> DL (atraso grande)

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
    li_on_time_max, li_small_delay_max = _delay_limits(fs_station)

    if lf_delay_seconds <= li_on_time_max:
        li_status = cfg.CI_ST_OK
    elif lf_delay_seconds <= li_small_delay_max:
        li_status = cfg.CI_ST_DS
    else:
        li_status = cfg.CI_ST_DL

    return ldt_arrival.timestamp(), li_status

# ─────────────────────────────────────────────────────────────────────────────────────
def round_down_to_slot(fdt_time: datetime.datetime) -> datetime.datetime:
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

    return (ls_station, round_down_to_slot(ldt_file_time)), (ldt_file_time, ldt_arrival_utc)

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
    ldct_new_slot_counts = collections.Counter(ls_station for ls_station, _ in fdct_observations
                                   if ls_station not in lset_known)

    for ls_station, li_slot_count in sorted(ldct_new_slot_counts.items()):
        M_LOG.warning("estação fora de CLST_STATIONS: %s (%d slots na janela) -- "
                      "estação nova ou caminho fora do padrão no catalog.db?",
                      ls_station, li_slot_count)

    return list(cfg.CLST_STATIONS) + sorted(ldct_new_slot_counts)

# ─────────────────────────────────────────────────────────────────────────────────────
def _warn_clock_ahead(fdct_observations: dict) -> None:
    """
    avisa no log as estações cujo relógio parece adiantado.

    chegada antes do horário do nome do arquivo conta como "no prazo" (o
    arquivo chegou), mas esconde o atraso real.  Se a MEDIANA do atraso
    (chegada - horário do arquivo) de uma estação fica abaixo de
    -cfg.CI_CLOCK_AHEAD_WARN_SECONDS, o relógio do radar está adiantado em
    PELO MENOS esse valor (mais a duração da varredura e da transmissão).

    só avalia estações com cfg.CI_CLOCK_AHEAD_MIN_FILES arquivos na janela ou
    mais.  Não muda nenhum status: é um aviso para quem cuida do radar.

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}
    """
    ldct_delays = collections.defaultdict(list)

    for (ls_station, _), (ldt_file_time, ldt_arrival) in fdct_observations.items():
        ldct_delays[ls_station].append((ldt_arrival - ldt_file_time).total_seconds())

    for ls_station, llst_delays in sorted(ldct_delays.items()):
        if len(llst_delays) < cfg.CI_CLOCK_AHEAD_MIN_FILES:
            continue

        lf_median = statistics.median(llst_delays)

        if lf_median >= -cfg.CI_CLOCK_AHEAD_WARN_SECONDS:
            continue

        M_LOG.warning("relógio do radar adiantado: %s -- arquivos chegam %.0f s ANTES do "
                      "horário do nome (mediana de %d arquivos); atrasos reais de até "
                      "esse valor aparecem como no prazo", ls_station, -lf_median,
                      len(llst_delays))

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
        llst_slots.append(round_down_to_slot(ldt_current))
        ldt_current += datetime.timedelta(minutes=cfg.CI_SLOT_MINUTES)

    return llst_slots

# ─────────────────────────────────────────────────────────────────────────────────────
def _unseen_status(fdt_slot: datetime.datetime,
                   fdt_judged_until: datetime.datetime | None,
                   fb_source_fresh: bool, fb_maintenance: bool = False) -> int:
    """
    decide o status de um slot SEM observação no banco.

    o monrad só vê o que o 21.mvol registrou.  Um arquivo do slot deveria estar
    no banco até CI_PENDING_GRACE_MINUTES depois do início do slot; só se o
    mvol registrou alguma coisa depois disso (fdt_judged_until) a ausência é
    culpa do radar.

    regras:
    - estação em manutenção                     -> MAINT ("Manutenção")
    - prazo do slot já coberto pelo mvol        -> MISS
    - não coberto, fonte em dia (mvol rodando)  -> FUTURE ("Aguardando")
    - não coberto, fonte parada ou banco vazio  -> NOSRC ("Sem fonte")

    :param fdt_slot: início do slot (UTC)
    :param fdt_judged_until: até quando o mvol cobriu (min(max(created_at),
                             agora)), ou None se o banco não tem registro
    :param fb_source_fresh: True se o mvol registrou algo nos últimos
                            CI_SOURCE_STALE_MINUTES
    :param fb_maintenance: True se a estação está em cfg.CLST_STATIONS_MAINTENANCE
    :returns: código de status (CI_ST_MAINT, CI_ST_MISS, CI_ST_FUTURE ou CI_ST_NOSRC)
    """
    # desligada de propósito: a ausência não é falha, seja qual for a fonte
    if fb_maintenance:
        return cfg.CI_ST_MAINT

    ldt_deadline = fdt_slot + datetime.timedelta(minutes=cfg.CI_PENDING_GRACE_MINUTES)

    if fdt_judged_until is not None and ldt_deadline <= fdt_judged_until:
        return cfg.CI_ST_MISS

    if fb_source_fresh:
        return cfg.CI_ST_FUTURE

    return cfg.CI_ST_NOSRC

# ─────────────────────────────────────────────────────────────────────────────────────
def _station_slots(fdct_observations: dict, fs_station: str, flst_slots: list,
                   fdt_judged_until: datetime.datetime | None,
                   fb_source_fresh: bool, fb_use_maintenance: bool = True) -> list:
    """
    classifica todos os slots de 10 min de uma estação dentro da janela.

    slot com observação: classify_slot (pelo atraso).  Slot sem observação:
    _unseen_status (MAINT se a estação está em manutenção; senão MISS, FUTURE
    ou NOSRC, conforme o mvol já o cobriu).

    :param fdct_observations: {(estação, slot): (horário_do_arquivo, horário_chegada)}
    :param fs_station: estação
    :param flst_slots: inícios de slot da janela (ver _window_slots)
    :param fdt_judged_until: até quando o mvol cobriu (ver _unseen_status)
    :param fb_source_fresh: fonte em dia (ver _unseen_status)
    :param fb_use_maintenance: False ignora cfg.CLST_STATIONS_MAINTENANCE (a
                               lista vale para AGORA, não para um período passado)
    :returns: lista de (timestamp, código_status), do slot mais antigo ao mais novo
    """
    llst_statuses = []
    li_received_count = 0
    lb_maintenance = fb_use_maintenance and fs_station in cfg.CLST_STATIONS_MAINTENANCE

    for ldt_slot in flst_slots:
        lf_timestamp, li_status = classify_slot(fdct_observations, fs_station, ldt_slot)

        if li_status == cfg.CI_ST_MISS:
            li_status = _unseen_status(ldt_slot, fdt_judged_until, fb_source_fresh,
                                       lb_maintenance)
        else:
            li_received_count += 1

        llst_statuses.append((lf_timestamp, li_status))

    M_LOG.info("%d/%d registros válidos encontrados para %s%s.",
               li_received_count, len(llst_statuses), fs_station,
               " (em manutenção)" if lb_maintenance else "")

    return llst_statuses

# ─────────────────────────────────────────────────────────────────────────────────────
def _source_coverage(fdt_last_update: datetime.datetime | None,
                     fdt_now_utc: datetime.datetime) -> tuple[datetime.datetime | None, bool]:
    """
    diz até quando o 21.mvol cobriu o tempo e se ele está em dia.

    a cobertura é o max(created_at), limitado a "agora": um relógio do mvol
    adiantado não pode dar como vencido um slot que ainda não venceu.

    :param fdt_last_update: max(created_at) do banco, ou None (sem registro)
    :param fdt_now_utc: instante atual, UTC
    :returns: (cobertura ou None, True se houve registro nos últimos
              CI_SOURCE_STALE_MINUTES)
    """
    if fdt_last_update is None:
        return None, False

    ldt_stale_limit = fdt_now_utc - datetime.timedelta(minutes=cfg.CI_SOURCE_STALE_MINUTES)

    return min(fdt_last_update, fdt_now_utc), fdt_last_update >= ldt_stale_limit

# ─────────────────────────────────────────────────────────────────────────────────────
def classify_period(fs_dbase_path: str, fdt_start_utc: datetime.datetime,
                    fdt_end_utc: datetime.datetime, fdt_now_utc: datetime.datetime,
                    fb_use_maintenance: bool = True) -> tuple[dict, list, datetime.datetime | None]:
    """
    classifica todos os slots de todas as estações num período [início, fim).

    é o núcleo comum do painel (build_station_status: as últimas N horas) e do
    relatório de disponibilidade (rsmReport.py: um mês, por exemplo).

    fluxo:
    1. lê do catalog.db as observações do período e a última atualização;
    2. avisa no log as estações com relógio adiantado (_warn_clock_ahead) e
       decide a lista de estações (conhecidas + novas vistas no banco);
    3. calcula até quando o mvol cobriu o tempo (_source_coverage);
    4. lista os slots do período e classifica cada slot de cada estação.

    :param fs_dbase_path: catalog.db do 21.mvol (só lido, nunca alterado)
    :param fdt_start_utc: início do período (inclusive), UTC com fuso
    :param fdt_end_utc: fim do período (exclusive), UTC com fuso
    :param fdt_now_utc: instante atual, UTC (decide o que já venceu)
    :param fb_use_maintenance: False ignora cfg.CLST_STATIONS_MAINTENANCE
    :returns: ({estação: [(timestamp, código_status), ...]}, inícios de slot,
               max(created_at) ou None)
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    # o banco é lido a partir do início do PRIMEIRO slot (o período pode
    # começar no meio de um)
    ldct_observations, ldt_last_update = _load_dbase(fs_dbase_path,
                                                     round_down_to_slot(fdt_start_utc),
                                                     fdt_end_utc)

    _warn_clock_ahead(ldct_observations)

    llst_slots = _window_slots(fdt_start_utc, fdt_end_utc)
    ldt_judged_until, lb_source_fresh = _source_coverage(ldt_last_update, fdt_now_utc)

    ldct_stations = {}
    for ls_station in _list_stations(ldct_observations):
        ldct_stations[ls_station] = _station_slots(ldct_observations, ls_station, llst_slots,
                                                   ldt_judged_until, lb_source_fresh,
                                                   fb_use_maintenance)

    return ldct_stations, llst_slots, ldt_last_update

# ─────────────────────────────────────────────────────────────────────────────────────
def build_station_status(fs_dbase_path: str,
                         fi_window_hours: int = cfg.CI_DEFAULT_WINDOW_HOURS) -> dict:
    """
    monta o status de recepção de todas as estações na janela pedida.

    fluxo:
    1. calcula a janela [agora - horas, agora) em UTC;
    2. classifica a janela (classify_period);
    3. monta o documento do JSON de status.

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

    ldct_stations, llst_slots, ldt_last_update = classify_period(fs_dbase_path, ldt_start_utc,
                                                                 ldt_end_utc, ldt_now_utc)

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
    # log em UTC, como os demais projetos cls
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(datefmt="%Y/%m/%d %H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.INFO)

    sys.exit(main())

# < the end >──────────────────────────────────────────────────────────────────────────
