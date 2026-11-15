# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsm_files
gravação atômica dos arquivos de saída do monrad (JSON de status e PNG).

quem lê o JSON ou o PNG (o rsmPNG.py, um servidor web, um navegador) pode
abri-los a qualquer momento.  Gravando direto no arquivo final, uma leitura
no meio da gravação pega um arquivo truncado.  Aqui o conteúdo vai primeiro
para um arquivo temporário NO MESMO diretório e só então é trocado pelo final
com os.replace (atômico no mesmo sistema de arquivos): quem lê vê o arquivo
antigo inteiro ou o novo inteiro, nunca um pedaço.

2026.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import contextlib
import os
import pathlib

# ─────────────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def atomic_output(fpth_out: str | os.PathLike):
    """
    dá um caminho temporário para gravar e, no fim do bloco, o troca pelo final.

    o temporário fica no mesmo diretório do final (os.replace só é atômico
    dentro do mesmo sistema de arquivos), é oculto, leva o pid (duas execuções
    manuais não se atropelam) e mantém a extensão do final (o savefig do
    matplotlib escolhe o formato por ela).  É criado com open() normal, então
    as permissões seguem o umask, como o arquivo final sempre teve.

    se o bloco falhar, o temporário é apagado e o arquivo final fica intacto.

    uso:
        with atomic_output("saida.json") as lpth_tmp:
            lpth_tmp.write_text(...)

    :param fpth_out: caminho do arquivo final
    :returns: (via yield) caminho temporário onde gravar
    """
    lpth_out = pathlib.Path(fpth_out)
    lpth_tmp = lpth_out.with_name(f".{lpth_out.stem}.{os.getpid()}.tmp{lpth_out.suffix}")

    try:
        yield lpth_tmp
        os.replace(lpth_tmp, lpth_out)

    finally:
        # depois do replace o temporário não existe mais; aqui só sobra em caso de erro
        lpth_tmp.unlink(missing_ok=True)

# < the end >──────────────────────────────────────────────────────────────────────────
