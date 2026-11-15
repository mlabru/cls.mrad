# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

test_rsm_files
testes unitários de rsm_files (gravação atômica)

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import os

# pytest
import pytest

# locals
import work.rsm_files as fil

# < atomic_output >────────────────────────────────────────────────────────────────────

def test_atomic_output_replaces_final_file_and_leaves_no_temp(tmp_path):
    """
    o conteúdo novo substitui o antigo e nenhum temporário sobra
    """
    lpth_out = tmp_path / "status.json"
    lpth_out.write_text("antigo", encoding="utf-8")

    with fil.atomic_output(lpth_out) as lpth_tmp:
        # durante a gravação o final ainda é o antigo, inteiro
        lpth_tmp.write_text("novo", encoding="utf-8")
        assert lpth_out.read_text(encoding="utf-8") == "antigo"
        assert lpth_tmp.parent == lpth_out.parent
        assert lpth_tmp.suffix == ".json"

    assert lpth_out.read_text(encoding="utf-8") == "novo"
    assert os.listdir(tmp_path) == ["status.json"]


def test_atomic_output_failure_keeps_old_file_and_removes_temp(tmp_path):
    """
    erro no meio da gravação: o arquivo final fica intacto e o temporário some
    """
    lpth_out = tmp_path / "rsm_out.png"
    lpth_out.write_bytes(b"antigo")

    with pytest.raises(RuntimeError):
        with fil.atomic_output(lpth_out) as lpth_tmp:
            lpth_tmp.write_bytes(b"pela metade")
            raise RuntimeError("falha simulada")

    assert lpth_out.read_bytes() == b"antigo"
    assert os.listdir(tmp_path) == ["rsm_out.png"]


def test_atomic_output_creates_new_file_with_umask_permissions(tmp_path):
    """
    arquivo que ainda não existe é criado, com as permissões do umask (o
    servidor web que exibe o PNG continua podendo lê-lo)
    """
    lpth_out = tmp_path / "novo.json"
    li_old_umask = os.umask(0o022)

    try:
        with fil.atomic_output(lpth_out) as lpth_tmp:
            lpth_tmp.write_text("{}", encoding="utf-8")
    finally:
        os.umask(li_old_umask)

    assert lpth_out.read_text(encoding="utf-8") == "{}"
    assert lpth_out.stat().st_mode & 0o777 == 0o644

# < the end >──────────────────────────────────────────────────────────────────────────
