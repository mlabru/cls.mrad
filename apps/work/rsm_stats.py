# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_stats
leitura do JSON de status e as contas sobre ele (o que conta na estatística,
percentuais, estação muda, fonte parada).

é a regra ÚNICA dessas contas: o PNG (rsm_figure), o alarme (rsmCheck.py) e
o relatório de disponibilidade (rsmReport.py) a usam, então painel, alarme e
relatório nunca discordam.  Não importa o matplotlib (nem o numpy): o alarme
roda mesmo que a pilha gráfica do virtualenv esteja quebrada -- foi assim
que o PNG congelou em 2026-10.

2026.nov  mlabru  initial version (Linux/Python): saiu do rsm_figure
                  (_count_statuses, _station_order, stations_from_document,
                  a decisão de source_alert) para o alarme e o relatório
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import collections
import datetime

# locals
import work.rsm_config as cfg

# < constants >────────────────────────────────────────────────────────────────────────

# status que não julgam o radar e por isso ficam fora de toda estatística:
# FUTURE (slot ainda não venceu), NOSRC (o 21.mvol parou antes de registrá-lo)
# e MAINT (estação em manutenção)
CSET_UNJUDGED_STATUSES = frozenset((cfg.CI_ST_FUTURE, cfg.CI_ST_NOSRC, cfg.CI_ST_MAINT))

# status de arquivo recebido (no prazo ou atrasado)
CSET_RECEIVED_STATUSES = frozenset((cfg.CI_ST_OK, cfg.CI_ST_DS, cfg.CI_ST_DL))

# ─────────────────────────────────────────────────────────────────────────────────────
def stations_from_document(fdct_document: dict) -> dict:
    """
    extrai o status por estação do documento gravado por rsmStatus.py.

    aceita também o formato antigo (o próprio dicionário de estações, sem a
    chave "stations"), para não quebrar com um JSON gravado antes da
    atualização -- o rsm_run.sh o regrava no ciclo seguinte.

    :param fdct_document: conteúdo do JSON de status
    :returns: {estação: [(timestamp, código_status), ...]}
    """
    if "stations" not in fdct_document:
        return fdct_document

    return fdct_document["stations"]

# ─────────────────────────────────────────────────────────────────────────────────────
def station_order(fdct_data: dict) -> list:
    """
    define a ordem de exibição das estações.

    primeiro as estações conhecidas, na ordem de cfg.CLST_STATIONS; depois
    qualquer outra presente nos dados (ex.: estação nova, descoberta pelo
    rsmStatus.py), em ordem alfabética.

    :param fdct_data: status por estação
    :returns: lista com os nomes das estações, na ordem de exibição
    """
    llst_known = [ls_station for ls_station in cfg.CLST_STATIONS
                  if ls_station in fdct_data]

    llst_new = sorted(ls_station for ls_station in fdct_data
                      if ls_station not in cfg.CLST_STATIONS)

    return llst_known + llst_new

# ─────────────────────────────────────────────────────────────────────────────────────
def count_statuses(flst_slots: list) -> collections.defaultdict:
    """
    conta quantos slots há de cada status, ignorando FUTURE, NOSRC e MAINT.

    FUTURE (slot que ainda não venceu), NOSRC (sem fonte: o mvol parou) e
    MAINT (estação em manutenção) não são sucesso nem falha do radar, por isso
    não entram em nenhuma estatística (CSET_UNJUDGED_STATUSES).

    :param flst_slots: lista de (timestamp, código_status)
    :returns: dicionário {código_status: quantidade} (0 para códigos ausentes)
    """
    ldct_counts = collections.defaultdict(int)

    for _, li_status in flst_slots:
        if li_status in CSET_UNJUDGED_STATUSES:
            continue
        ldct_counts[li_status] += 1

    return ldct_counts

# ─────────────────────────────────────────────────────────────────────────────────────
def percent(fi_part: int, fi_total: int) -> float:
    """
    calcula fi_part / fi_total em %, com 0% quando não há nada julgado.

    :param fi_part: quantidade
    :param fi_total: total
    :returns: percentual 0..100 (0.0 se fi_total for 0)
    """
    if fi_total == 0:
        return 0.0

    return fi_part / fi_total * 100

# ─────────────────────────────────────────────────────────────────────────────────────
def trailing_miss_count(flst_slots: list) -> int:
    """
    conta os slots "perdido" seguidos no fim da estação (os mais recentes).

    os status fora das estatísticas (Aguardando, Sem fonte, Manutenção) são
    pulados, sem interromper a contagem: os últimos slots costumam estar
    "Aguardando", e o que importa é o que já foi julgado antes deles.

    :param flst_slots: lista de (timestamp, código_status), do mais antigo ao mais novo
    :returns: número de MISS seguidos no fim (0 se o último julgado não é MISS)
    """
    li_count = 0

    for _, li_status in reversed(flst_slots):
        if li_status in CSET_UNJUDGED_STATUSES:
            continue

        if li_status != cfg.CI_ST_MISS:
            break

        li_count += 1

    return li_count

# ─────────────────────────────────────────────────────────────────────────────────────
def document_time(fdct_document: dict, fs_key: str) -> datetime.datetime | None:
    """
    lê um instante ISO UTC do documento de status.

    :param fdct_document: conteúdo do JSON de status
    :param fs_key: chave do instante ("last_slot", "generated_at", "source_last_update")
    :returns: o instante (com fuso), ou None se a chave falta ou está vazia
              (JSON de formato antigo, ou banco sem observação)
    """
    ls_value = fdct_document.get(fs_key)

    if ls_value is None:
        return None

    return datetime.datetime.fromisoformat(ls_value)

# ─────────────────────────────────────────────────────────────────────────────────────
def is_source_stale(fdt_last_update: datetime.datetime | None,
                    fdt_now_utc: datetime.datetime) -> bool:
    """
    diz se a fonte (o catalog.db do 21.mvol) está parada.

    parada = nenhuma observação nova há mais de cfg.CI_SOURCE_STALE_MINUTES,
    ou nenhuma observação nunca.  O banco sozinho não diz se a culpa é do
    mvol ou de todas as estações mudas ao mesmo tempo.

    :param fdt_last_update: max(created_at) do banco (source_last_update), ou None
    :param fdt_now_utc: instante atual, UTC, com fuso
    :returns: True se a fonte está parada
    """
    if fdt_last_update is None:
        return True

    ldt_stale_limit = fdt_now_utc - datetime.timedelta(minutes=cfg.CI_SOURCE_STALE_MINUTES)

    return fdt_last_update < ldt_stale_limit

# < the end >──────────────────────────────────────────────────────────────────────────
