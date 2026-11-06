# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_dbase
testes unitários de rsm_dbase (leitura SOMENTE LEITURA do catalog.db)

2026.out  mlabru  banco como única fonte: fetch_last_update; os testes de
                  build_station_status foram para test_rsmStatus.py
2026.out  mlabru  work.rsm_* e build_station_status (refatoração)
2026.out  mlabru  rsm_dbase somente leitura: testes de upsert/prune
                  removidos; o banco não muda e não é criado
2026.set  mlabru  fullpath relativo a REMOTE_DIR; absoluto não é gravado
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import sqlite3

# pytest
import pytest

# locals
import mvol.vol_catalog as ct
import work.rsm_dbase as rsm_dbase

# < connect >──────────────────────────────────────────────────────────────────────────

def test_connect_nao_cria_o_banco(tmp_path):
    """
    connect() abre somente leitura: banco inexistente falha e não é criado
    """
    lpth = tmp_path / "catalog.db"

    with pytest.raises(sqlite3.OperationalError):
        rsm_dbase.connect(str(lpth))

    assert not lpth.exists()


def test_connect_nao_escreve(make_dbase):
    """
    a conexão é mode=ro: qualquer escrita falha
    """
    lpth = make_dbase([("A/250/x.mvol", 1000.0)])

    lconn = rsm_dbase.connect(str(lpth))

    with pytest.raises(sqlite3.OperationalError):
        lconn.execute(f"DELETE FROM {ct.CS_TABLE}")

    lconn.close()

# < fetch_observations >───────────────────────────────────────────────────────────────

def test_fetch_observations_filters_by_window(make_dbase):
    """
    fetch_observations só devolve linhas com mtime dentro de [start, end]
    """
    lpth = make_dbase([("A/250/before.mvol", 100.0),
                       ("A/250/inside.mvol", 500.0),
                       ("A/250/after.mvol", 900.0)])

    lconn = rsm_dbase.connect(str(lpth))
    llst = rsm_dbase.fetch_observations(lconn, 200.0, 800.0)
    lconn.close()

    assert llst == [("A/250/inside.mvol", 500.0)]


def test_fetch_observations_sem_tabela(tmp_path):
    """
    banco sem vol_raw_observations (o 21.mvol ainda não sincronizou): lista
    vazia, sem criar a tabela
    """
    lpth = tmp_path / "catalog.db"
    sqlite3.connect(str(lpth)).close()

    lconn = rsm_dbase.connect(str(lpth))
    assert [] == rsm_dbase.fetch_observations(lconn, 0.0, 1e12)
    lconn.close()

    lconn = sqlite3.connect(str(lpth))
    assert [] == lconn.execute("SELECT name FROM sqlite_master").fetchall()
    lconn.close()

# < fetch_last_update >────────────────────────────────────────────────────────────────

def test_fetch_last_update_devolve_o_maior_created_at(make_dbase):
    """
    a última atualização é o max(created_at), em UTC com fuso
    """
    lpth = make_dbase([("A/250/x.mvol", 1.0)], fs_created_at="2026-10-07T12:00:00+00:00")

    lconn = rsm_dbase.connect(str(lpth))
    ldt = rsm_dbase.fetch_last_update(lconn)
    lconn.close()

    assert ldt == datetime.datetime(2026, 10, 7, 12, 0, tzinfo=datetime.timezone.utc)


def test_fetch_last_update_sem_fuso_e_tratado_como_utc(make_dbase):
    """
    created_at sem fuso também é UTC
    """
    lpth = make_dbase([("A/250/x.mvol", 1.0)], fs_created_at="2026-10-07T12:00:00")

    lconn = rsm_dbase.connect(str(lpth))
    ldt = rsm_dbase.fetch_last_update(lconn)
    lconn.close()

    assert ldt.tzinfo == datetime.timezone.utc


def test_fetch_last_update_tabela_vazia_ou_sem_created_at(make_dbase, tmp_path):
    """
    sem nenhuma linha (ou created_at NULL): None
    """
    lpth = make_dbase([("A/250/x.mvol", 1.0)], fs_created_at="")

    lconn = rsm_dbase.connect(str(lpth))
    assert rsm_dbase.fetch_last_update(lconn) is None
    lconn.close()


def test_fetch_last_update_sem_tabela(tmp_path):
    """
    banco sem a tabela: None, sem erro
    """
    lpth = tmp_path / "catalog.db"
    sqlite3.connect(str(lpth)).close()

    lconn = rsm_dbase.connect(str(lpth))
    assert rsm_dbase.fetch_last_update(lconn) is None
    lconn.close()

# < the end >──────────────────────────────────────────────────────────────────────────
