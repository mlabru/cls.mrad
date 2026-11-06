# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_run_sh
testes do rsm_run.sh carregado com RSM_RUN_NO_MAIN=true (só as funções, sem
rodar o main), no padrão de test_ofl_run.py / test_vol_register.py

2026.out  mlabru  rsm_activate_venv (RSM_VENV, o ~/.venv do oflow/nowcast)
2026.out  mlabru  banco como única fonte: sem fetch_remote_listing
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

# raiz do projeto (onde está rsm_run.sh)
MPTH_ROOT = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")

# -------------------------------------------------------------------------------------
def _run_sourced(fpth_tmp: pathlib.Path, fs_body: str,
                 fs_lib_dir: str | None = None) -> subprocess.CompletedProcess:
    """
    carrega o rsm_run.sh sem executar o main e roda fs_body no mesmo shell.

    :param fpth_tmp: raiz temporária (RSM_PATH fica dentro dela)
    :param fs_body: comandos bash a executar depois do source
    :param fs_lib_dir: RSM_LIB_DIR alternativo (para trocar os programas Python)
    :returns: o processo concluído (returncode, stdout, stderr)
    """
    ldct_env = {ls: lv for ls, lv in os.environ.items()
                if not ls.startswith(("RSM_", "MET_"))}
    ldct_env.update({"RSM_PATH": str(fpth_tmp / "mrad"),
                     "RSM_RUN_NO_MAIN": "true"})

    ls_cmd = f'source "{MPTH_ROOT}/rsm_run.sh"; mkdir -p "$RSM_LOGS"; '
    if fs_lib_dir:
        ls_cmd += f'RSM_LIB_DIR="{fs_lib_dir}"; '

    return subprocess.run(["bash", "-c", ls_cmd + fs_body],
                          capture_output=True, text=True, env=ldct_env)

# -------------------------------------------------------------------------------------
def _fake_program(fpth_tmp: pathlib.Path, fs_name: str, fi_rc: int) -> str:
    """
    cria apps/<fs_name>.py falso que só sai com fi_rc.

    :returns: o diretório a usar como RSM_LIB_DIR
    """
    lpth_apps = fpth_tmp / "lib" / "apps"
    lpth_apps.mkdir(parents=True, exist_ok=True)
    (lpth_apps / f"{fs_name}.py").write_text(f"import sys\nsys.exit({fi_rc})\n",
                                             encoding="utf-8")
    return str(fpth_tmp / "lib")

# < testes >───────────────────────────────────────────────────────────────────────────

def test_no_main_carrega_as_funcoes_sem_executar(tmp_path):
    lproc = _run_sourced(tmp_path, "type -t acquire_instance_lock run_python_step main")

    assert 0 == lproc.returncode, lproc.stderr
    assert ["function"] * 3 == lproc.stdout.split()
    # o main não rodou: nenhum log de início
    assert "Iniciando" not in lproc.stderr


def test_run_python_step_sucesso(tmp_path):
    ls_lib = _fake_program(tmp_path, "fake", 0)

    lproc = _run_sourced(tmp_path, 'run_python_step fake; echo "rc=$?"', ls_lib)

    assert "rc=0" in lproc.stdout
    assert "[error]" not in lproc.stderr


def test_run_python_step_falha_loga_error_e_devolve_rc(tmp_path):
    ls_lib = _fake_program(tmp_path, "fake", 3)

    lproc = _run_sourced(tmp_path, 'rc=0; run_python_step fake || rc=$?; echo "rc=$rc"', ls_lib)

    assert "rc=3" in lproc.stdout
    assert "[error]: fake falhou (código 3)" in lproc.stderr

def test_script_nao_acessa_o_servidor_dos_mvol():
    """
    o banco é a única fonte: nada de ssh/find/rsync no rsm_run.sh
    """
    ls_code = [ls_line for ls_line in (MPTH_ROOT / "rsm_run.sh").read_text(encoding="utf-8").splitlines()
               if not ls_line.lstrip().startswith("#")]

    for ls_command in ("ssh ", "find ", "rsync "):
        assert not any(ls_command in ls_line for ls_line in ls_code), ls_command

def test_activate_venv_usa_o_python3_do_virtualenv(tmp_path):
    # virtualenv falso: o activate só põe um bin/python3 na frente do PATH
    lpth_bin = tmp_path / "venv" / "bin"
    lpth_bin.mkdir(parents=True)
    (lpth_bin / "python3").write_text("#!/bin/sh\n", encoding="utf-8")
    (lpth_bin / "python3").chmod(0o755)
    (lpth_bin / "activate").write_text(f'PATH="{lpth_bin}:$PATH"\n', encoding="utf-8")

    lproc = _run_sourced(tmp_path, f'RSM_VENV="{tmp_path / "venv"}"; rsm_activate_venv; '
                                   'command -v python3')

    assert 0 == lproc.returncode, lproc.stderr
    assert str(lpth_bin / "python3") == lproc.stdout.strip()
    assert f"python3={lpth_bin / 'python3'}" in lproc.stderr

def test_activate_venv_inexistente_avisa_e_segue(tmp_path):
    lproc = _run_sourced(tmp_path, f'RSM_VENV="{tmp_path / "nao_existe"}"; rsm_activate_venv; '
                                   'echo "rc=$?"')

    assert "rc=0" in lproc.stdout
    assert "[warn]: virtualenv inexistente" in lproc.stderr

def test_main_ativa_o_venv_antes_dos_programas():
    ls_text = (MPTH_ROOT / "rsm_run.sh").read_text(encoding="utf-8")

    assert ls_text.index("    rsm_activate_venv") < ls_text.index("    run_python_step rsmStatus")

# < the end >──────────────────────────────────────────────────────────────────────────
