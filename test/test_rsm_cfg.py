# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_cfg
testes do rsm_cfg.sh: padrões de produção, override pelo ambiente, trava
MET_ENV=test e o setup (rsm_setup do rsm_common.sh: mkdir + cd em
RSM_PATH, PYTHONPATH em apps/)

2026.out  mlabru  RSM_VENV (padrão ~/.venv); RSM_PATH padrão ~/Public/mrad
2026.out  mlabru  banco como única fonte: sem RSM_REMOTE_* (nem servidor nem
                  trava -r); RSM_DBASE_FILE padrão = banco do mvol
2026.out  mlabru  REMOTE_* -> RSM_REMOTE_*; o setup saiu do source do
                  rsm_cfg.sh (sem RSM_CFG_NO_SETUP) para rsm_setup; ".." não
                  escapa da raiz (met_check_test_env usa realpath -m)
2026.out  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import os
import pathlib
import shutil
import subprocess

# pytest
import pytest

# < helpers >──────────────────────────────────────────────────────────────────────────

# raiz do projeto (onde está rsm_cfg.sh)
MPTH_ROOT = pathlib.Path(__file__).resolve().parent.parent

# variáveis exibidas por _source
CT_VARS = ("RSM_PATH", "RSM_DBASE_FILE")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")

# -------------------------------------------------------------------------------------
def _source(fdct_env: dict, fb_setup: bool = False,
            fs_body: str | None = None) -> subprocess.CompletedProcess:
    """
    carrega o rsm_cfg.sh (mais rsm_common.sh + rsm_setup, se fb_setup) e
    imprime CT_VARS, com o ambiente limpo de RSM_*/MET_* herdados mais fdct_env
    """
    ldct_env = {ls: lv for ls, lv in os.environ.items()
                if not ls.startswith(("RSM_", "MET_"))}
    ldct_env.update(fdct_env)

    ls_cmd = f'source "{MPTH_ROOT}/rsm_cfg.sh"; '

    if fb_setup:
        ls_cmd += f'source "{MPTH_ROOT}/rsm_common.sh"; rsm_setup; '

    ls_body = fs_body or "; ".join(f'echo "${{{ls}}}"' for ls in CT_VARS)

    return subprocess.run(["bash", "-c", ls_cmd + ls_body],
                          capture_output=True, text=True, env=ldct_env)

# -------------------------------------------------------------------------------------
def _tst_env(fpth_root: pathlib.Path, **kwargs) -> dict:
    """
    ambiente de teste coerente (como o tst_env/env.sh), com overrides
    """
    ldct = {"MET_ENV": "test",
            "MET_TST_ROOT": str(fpth_root),
            "RSM_PATH": str(fpth_root / "mrad"),
            "RSM_DBASE_FILE": str(fpth_root / "mvol" / "data" / "dbase" / "catalog.db")}
    ldct.update(kwargs)

    return ldct

# < testes >───────────────────────────────────────────────────────────────────────────

def test_padroes_de_producao():
    lproc = _source({"USER": "fulano"})

    assert 0 == lproc.returncode, lproc.stderr
    # o banco padrão é o do 21.mvol (VOL_DBASE_FILE do vol_cfg.sh)
    assert ["/home/fulano/Public/mrad",
            "/home/fulano/Public/mvol/data/dbase/catalog.db"] == lproc.stdout.splitlines()

def test_venv_padrao_e_o_do_oflow_e_nowcast():
    # o mesmo ~/.venv do OFL_VENV (25.oflow) e do NWC_VENV (27.nowcast)
    lproc = _source({"USER": "fulano", "HOME": "/home/fulano"}, fs_body='echo "$RSM_VENV"')

    assert 0 == lproc.returncode, lproc.stderr
    assert "/home/fulano/.venv" == lproc.stdout.strip()

def test_venv_override_pelo_ambiente(tmp_path):
    lproc = _source({"USER": "fulano", "RSM_VENV": str(tmp_path / "venv")},
                    fs_body='echo "$RSM_VENV"')

    assert 0 == lproc.returncode, lproc.stderr
    assert str(tmp_path / "venv") == lproc.stdout.strip()

def test_override_pelo_ambiente(tmp_path):
    lproc = _source(_tst_env(tmp_path))

    assert 0 == lproc.returncode, lproc.stderr
    assert [str(tmp_path / "mrad"),
            str(tmp_path / "mvol" / "data" / "dbase" / "catalog.db")] == lproc.stdout.splitlines()

def test_sem_servidor_remoto():
    # o banco é a única fonte: nenhuma variável de servidor/listagem
    lproc = _source({"USER": "fulano"}, fs_body='echo "[${RSM_REMOTE_HOST:-}${RSM_REMOTE_DIR:-}]"')

    assert 0 == lproc.returncode, lproc.stderr
    assert "[]" == lproc.stdout.strip()

def test_trava_recusa_caminho_fora_da_raiz(tmp_path):
    ldct = _tst_env(tmp_path)
    # sem override, o banco padrão (/home/.../mvol) fica fora da raiz de teste
    del ldct["RSM_DBASE_FILE"]

    lproc = _source(ldct)

    assert 1 == lproc.returncode
    assert "fora de" in lproc.stderr

def test_trava_recusa_escape_por_dot_dot(tmp_path):
    lproc = _source(_tst_env(tmp_path / "tst", RSM_PATH=str(tmp_path / "tst" / ".." / "producao")))

    assert 1 == lproc.returncode
    assert "fora de" in lproc.stderr

def test_source_do_cfg_nao_muda_o_cwd(tmp_path):
    lproc = _source(_tst_env(tmp_path), fs_body="pwd")

    assert 0 == lproc.returncode, lproc.stderr
    assert str(tmp_path / "mrad") != lproc.stdout.strip()
    assert not (tmp_path / "mrad").exists()

def test_setup_cria_rsm_path_e_aponta_para_apps(tmp_path):
    lproc = _source(_tst_env(tmp_path), fb_setup=True, fs_body='pwd; echo "$PYTHONPATH"')

    assert 0 == lproc.returncode, lproc.stderr
    assert [str(tmp_path / "mrad"), str(MPTH_ROOT / "apps")] == lproc.stdout.splitlines()

# < the end >──────────────────────────────────────────────────────────────────────────
