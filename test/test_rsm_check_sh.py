# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_check_sh
testes do rsm_check.sh (verificação externa: heartbeat do rsm_run.sh +
recepção pelo rsmCheck.py), executado de verdade num RSM_PATH temporário,
no padrão de test_vol_check.py / test_ofl_check.py

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

# pytest
import pytest

# locals
import work.rsm_config as cfg

# < helpers >──────────────────────────────────────────────────────────────────────────

# raiz do projeto (onde está rsm_check.sh)
MPTH_ROOT = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")


def _write_heartbeat(fpth_root: pathlib.Path, fi_age_minutes: int) -> None:
    """
    grava o heartbeat do rsm_run.sh (formato do cls_heartbeat) com a idade pedida
    """
    li_epoch = int(time.time()) - fi_age_minutes * 60
    lpth = fpth_root / "mrad" / "data" / "state" / "rsm_run.ok"
    lpth.parent.mkdir(parents=True, exist_ok=True)
    lpth.write_text(f"{li_epoch} 2026-11-19T00:00:00Z\n", encoding="utf-8")


def _write_status(fpth_root: pathlib.Path, fi_status: int = cfg.CI_ST_OK) -> None:
    """
    grava o JSON de status (RSM_STATUS_JSON) recém-gerado, todas as estações
    com fi_status em todos os slots
    """
    ls_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ldct_doc = {"generated_at": ls_now, "last_slot": ls_now, "source_last_update": ls_now,
                "stations": {ls_station: [[li, fi_status] for li in range(144)]
                             for ls_station in cfg.CLST_STATIONS}}

    lpth = fpth_root / "mrad" / "data" / "temp" / "rsm_temp.json"
    lpth.parent.mkdir(parents=True, exist_ok=True)
    lpth.write_text(json.dumps(ldct_doc), encoding="utf-8")


def _run_check(fpth_root: pathlib.Path, fs_venv: str | None = None) -> subprocess.CompletedProcess:
    """
    roda o rsm_check.sh com RSM_PATH em fpth_root/mrad e o python3 desta suíte
    (ou o RSM_VENV pedido)
    """
    ldct_env = {ls: lv for ls, lv in os.environ.items() if not ls.startswith("RSM_")}
    ldct_env.update({"RSM_PATH": str(fpth_root / "mrad"),
                     "RSM_VENV": fs_venv or sys.prefix})

    return subprocess.run(["bash", str(MPTH_ROOT / "rsm_check.sh")],
                          capture_output=True, text=True, env=ldct_env)

# < testes >───────────────────────────────────────────────────────────────────────────

def test_all_fine_is_ok(tmp_path):
    _write_heartbeat(tmp_path, 5)
    _write_status(tmp_path)

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 0, lproc.stdout + lproc.stderr
    assert lproc.stdout.startswith("OK: rsm_run ok há 5 min | recepção OK: ")
    assert len(lproc.stdout.strip().splitlines()) == 1


def test_old_heartbeat_is_critical(tmp_path):
    _write_heartbeat(tmp_path, 31)
    _write_status(tmp_path)

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 2
    assert lproc.stdout.startswith("CRITICAL: rsm_run sem sucesso há 31 min")


def test_missing_heartbeat_is_unknown(tmp_path):
    _write_status(tmp_path)

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 3
    assert lproc.stdout.startswith("UNKNOWN: rsm_run sem heartbeat")


def test_reception_warning_wins_over_ok_heartbeat(tmp_path):
    """
    1 perdido a cada 5 slots em todas as estações: WARNING da recepção
    """
    _write_heartbeat(tmp_path, 0)
    _write_status(tmp_path)
    lpth = tmp_path / "mrad" / "data" / "temp" / "rsm_temp.json"
    ldct_doc = json.loads(lpth.read_text(encoding="utf-8"))
    for llst_slots in ldct_doc["stations"].values():
        for li_index in range(0, len(llst_slots), 5):
            llst_slots[li_index][1] = cfg.CI_ST_MISS
    lpth.write_text(json.dumps(ldct_doc), encoding="utf-8")

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 1
    assert lproc.stdout.startswith("WARNING: ")


def test_reception_critical_wins_over_unknown_heartbeat(tmp_path):
    _write_status(tmp_path, cfg.CI_ST_MISS)

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 2
    assert "recepção CRITICAL: sem recepção" in lproc.stdout


def test_missing_status_json_is_unknown(tmp_path):
    _write_heartbeat(tmp_path, 0)

    lproc = _run_check(tmp_path)

    assert lproc.returncode == 3
    assert "recepção UNKNOWN: JSON de status ilegível" in lproc.stdout


def test_broken_python_is_unknown_not_warning(tmp_path):
    """
    um python3 que quebra sai com 1 -- não pode passar por WARNING
    """
    _write_heartbeat(tmp_path, 0)
    _write_status(tmp_path)
    lpth_bin = tmp_path / "venv" / "bin"
    lpth_bin.mkdir(parents=True)
    (lpth_bin / "python3").write_text("#!/bin/sh\necho 'ModuleNotFoundError: x' >&2\nexit 1\n",
                                      encoding="utf-8")
    (lpth_bin / "python3").chmod(0o755)

    lproc = _run_check(tmp_path, str(tmp_path / "venv"))

    assert lproc.returncode == 3
    assert lproc.stdout.startswith("UNKNOWN: ")
    assert "ModuleNotFoundError" in lproc.stdout


def test_check_does_not_touch_the_app_log(tmp_path):
    _write_heartbeat(tmp_path, 0)
    _write_status(tmp_path)

    _run_check(tmp_path)

    assert not (tmp_path / "mrad" / "logs").exists()

# < the end >──────────────────────────────────────────────────────────────────────────
