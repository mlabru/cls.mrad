# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

conftest
fixtures e configuração compartilhada dos testes

2026.nov  mlabru  make_dbase preenche timestamp (do nome do arquivo, como o
                  mvol): o monrad passou a consultar por essa coluna
2026.nov  mlabru  sem a fixture qapp e o QT_QPA_PLATFORM (a GUI PyQt foi
                  removida)
2026.out  mlabru  fixture make_dbase: catalog.db de teste no formato do 21.mvol
                  (o banco é a única fonte do monrad)
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import sqlite3

# matplotlib sem backend interativo
import matplotlib
matplotlib.use("Agg")

# pytest
import pytest

# < helpers >──────────────────────────────────────────────────────────────────────────

def name_timestamp(fs_fullpath: str) -> int | None:
    """
    epoch UTC do horário escrito no nome do arquivo, como o 21.mvol grava na
    coluna timestamp (volDBWriter.name_timestamp)

    ex.: "Cangucu/250/STI-250--2026-04-12--00-03-23.mvol" -> epoch de
    2026-04-12 00:03:23 UTC; nome fora do padrão -> None (o mvol grava NULL)
    """
    try:
        ls_date, ls_time = fs_fullpath.rsplit("/", 1)[-1].rsplit(".", 1)[0].split("--")[1:3]
        ldt_file_time = datetime.datetime.strptime(f"{ls_date} {ls_time}", "%Y-%m-%d %H-%M-%S")

    except ValueError:
        return None

    return int(ldt_file_time.replace(tzinfo=datetime.timezone.utc).timestamp())

# < fixtures >─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def make_dbase(tmp_path):
    """
    cria um catalog.db de teste como o 21.mvol (vol_sync.sh) o grava.

    uso: lpth = make_dbase([(fullpath, mtime), ...], fs_created_at=None)
    fs_created_at None = agora (UTC); "" = coluna vazia (NULL)
    timestamp: extraído do nome do arquivo, como o mvol faz (name_timestamp)

    :returns: função que cria o banco e devolve o seu caminho
    """
    # locals (import tardio: precisa do pythonpath do pytest.ini)
    import mvol.vol_catalog as ct

    def _make(flst_rows: list, fs_created_at: str | None = None):
        if fs_created_at is None:
            fs_created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        l_created_at = fs_created_at or None

        lpth_dbase = tmp_path / "catalog.db"
        l_conn = sqlite3.connect(str(lpth_dbase))
        l_conn.execute(ct.CS_CREATE_TABLE)
        l_conn.execute(ct.CS_CREATE_INDEX)
        l_conn.executemany(f"INSERT INTO {ct.CS_TABLE} "
                           "(fullpath, mtime, timestamp, source, created_at) "
                           "VALUES (?, ?, ?, 'mvol', ?)",
                           [(ls_path, lf_mtime, name_timestamp(ls_path), l_created_at)
                            for ls_path, lf_mtime in flst_rows])
        l_conn.commit()
        l_conn.close()

        return lpth_dbase

    return _make

# < the end >──────────────────────────────────────────────────────────────────────────
