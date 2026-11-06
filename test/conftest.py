# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

conftest
fixtures e configuração compartilhada dos testes

2026.out  mlabru  fixture make_dbase: catalog.db de teste no formato do 21.mvol
                  (o banco é a única fonte do monrad)
2026.ago  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import os
import sqlite3
import sys

# roda Qt sem display (CI / headless)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# matplotlib sem backend interativo
import matplotlib
matplotlib.use("Agg")

# pytest
import pytest

# < fixtures >─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    """
    QApplication único, compartilhado por toda a sessão de testes
    """
    # PyQt
    from PyQt5 import QtWidgets

    # reaproveita instância existente, se houver
    l_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    yield l_app

@pytest.fixture
def make_dbase(tmp_path):
    """
    cria um catalog.db de teste como o 21.mvol (vol_sync.sh) o grava.

    uso: lpth = make_dbase([(fullpath, mtime), ...], fs_created_at=None)
    fs_created_at None = agora (UTC); "" = coluna vazia (NULL)

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
        l_conn.executemany(f"INSERT INTO {ct.CS_TABLE} (fullpath, mtime, source, created_at) "
                           "VALUES (?, ?, 'mvol', ?)",
                           [(ls_path, lf_mtime, l_created_at) for ls_path, lf_mtime in flst_rows])
        l_conn.commit()
        l_conn.close()

        return lpth_dbase

    return _make

# < the end >──────────────────────────────────────────────────────────────────────────
