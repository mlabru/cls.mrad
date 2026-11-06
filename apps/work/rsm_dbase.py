# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_dbase
leitura, SOMENTE LEITURA, das observações de recepção radar
(vol_raw_observations) no catalog.db compartilhado com o 21.mvol.

quem escreve na tabela é só o 21.mvol (vol_sync.sh grava tudo o que lista no
servidor antes de apagar os arquivos de lá).  O monrad só monitora e informa:
não cria o banco, não cria tabela, não grava e não apaga nada.  A
interpretação de cada linha (sítio, alcance, slot esperado, offset UTC) é
feita por quem lê (rsmStatus._parse_observation).

2026.out  mlabru  guia de manutenção: docstring de fetch_observations citava
                  o find do rsm_run.sh, que não existe mais
2026.out  mlabru  fetch_last_update (max(created_at)): o banco é a única fonte
                  do monrad e é o que permite avisar quando o mvol parou
2026.out  mlabru  refatoração para legibilidade: docstrings com :returns:,
                  tipo de retorno; movido para apps/work/
2026.out  mlabru  somente leitura: upsert/prune e a criação de schema saíram
                  (a poda apagava o único histórico de recepção do 21.mvol)
2026.set  mlabru  fullpath relativo a REMOTE_DIR
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import logging
import sqlite3
import urllib.parse

# locals
import mvol.vol_catalog as ct

# < constants >────────────────────────────────────────────────────────────────────────

# segundos que a conexão espera se o 21.mvol estiver escrevendo no banco
CI_BUSY_TIMEOUT_SECONDS = 10

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────────────
def connect(fs_dbase_path: str) -> sqlite3.Connection:
    """
    abre o catalog.db em modo SOMENTE LEITURA.

    usa a URI "file:...?mode=ro" do sqlite: se o arquivo não existir, a
    abertura falha (em vez de criar um banco vazio) e qualquer tentativa de
    escrita na conexão também falha.

    :param fs_dbase_path: caminho do catalog.db
    :returns: conexão sqlite3 somente leitura (o chamador deve fechá-la)
    :raises sqlite3.OperationalError: banco inexistente ou ilegível
    """
    ls_uri = f"file:{urllib.parse.quote(fs_dbase_path)}?mode=ro"

    return sqlite3.connect(ls_uri, uri=True, timeout=CI_BUSY_TIMEOUT_SECONDS)

# ─────────────────────────────────────────────────────────────────────────────────────
def fetch_observations(fconn: sqlite3.Connection, ff_start_epoch: float,
                       ff_end_epoch: float) -> list[tuple[str, float]]:
    """
    lê as observações brutas com mtime dentro da janela [início, fim].

    o mtime é o epoch bruto do servidor (sem conversão de fuso), como o
    "find -printf %T@" do vol_sync.sh (21.mvol) o listou.  A conversão para
    UTC fica com quem lê (rsmStatus._parse_observation).

    :param fconn: conexão aberta por connect()
    :param ff_start_epoch: início da janela (epoch, inclusive)
    :param ff_end_epoch: fim da janela (epoch, inclusive)
    :returns: lista de (fullpath, mtime); lista vazia se a tabela ainda não
              existe (o 21.mvol a cria na primeira sincronização)
    """
    ls_query = f"SELECT fullpath, mtime FROM {ct.CS_TABLE} WHERE mtime >= ? AND mtime <= ?"

    try:
        return fconn.execute(ls_query, (ff_start_epoch, ff_end_epoch)).fetchall()

    except sqlite3.OperationalError as l_err:
        M_LOG.warning("observações indisponíveis no catalog.db: %s", l_err)
        return []

# ─────────────────────────────────────────────────────────────────────────────────────
def fetch_last_update(fconn: sqlite3.Connection) -> datetime.datetime | None:
    """
    devolve o instante da observação mais nova registrada pelo 21.mvol.

    usa max(created_at): o mvol preenche created_at (ISO, UTC) na primeira vez
    que vê cada arquivo.  Se esse instante ficar velho, ou o mvol parou ou
    nenhuma estação está enviando -- o banco sozinho não distingue os dois.

    :param fconn: conexão aberta por connect()
    :returns: instante UTC (com fuso), ou None se a tabela não existe, está
              vazia ou não tem created_at preenchido
    """
    ls_query = f"SELECT max(created_at) FROM {ct.CS_TABLE}"

    try:
        ls_last_update = fconn.execute(ls_query).fetchone()[0]

    except sqlite3.OperationalError as l_err:
        M_LOG.warning("última atualização indisponível no catalog.db: %s", l_err)
        return None

    if ls_last_update is None:
        return None

    ldt_last_update = datetime.datetime.fromisoformat(ls_last_update)

    # o mvol grava com "+00:00"; um valor sem fuso também é UTC
    if ldt_last_update.tzinfo is None:
        ldt_last_update = ldt_last_update.replace(tzinfo=datetime.timezone.utc)

    return ldt_last_update

# < the end >──────────────────────────────────────────────────────────────────────────
