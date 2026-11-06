#!/usr/bin/env bash
#
# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_run.sh
# script cron-driven do monitor de recepção radar (monrad).
#
# workflow:
# - apps/rsmStatus.py: lê do catalog.db do 21.mvol (somente leitura) as
#   observações de recepção, classifica cada slot de 10 min de cada estação
#   e grava o JSON de status (RSM_STATUS_JSON);
# - apps/rsmPNG.py: desenha o PNG do monitor (RSM_PNG_FILE).
#
# o banco é a ÚNICA fonte de dados: o monrad não acessa os .mvol nem o
# servidor de origem (isso é papel do 21.mvol).
#
# lock de instância (flock no fd 200): se o cron disparar de novo antes do
# fim da rodada anterior, a nova sai sem fazer nada (rc 0).
#
# 2026.out  mlabru  - python3 do RSM_VENV (rsm_activate_venv), como o
#                     25.oflow e o 27.nowcast
#                   - banco como única fonte: saiu fetch_remote_listing (ssh
#                     + find nos .mvol do servidor); rsmStatus.py só com -d
#                   - normalização com 21.mvol/25.oflow/27.nowcast (template
#                     do vol_sync.sh): funções acquire_instance_lock,
#                     fetch_remote_listing, run_python_step e main;
#                     RSM_RUN_NO_MAIN; set -euo pipefail após o cabeçalho;
#                     nível [error] (era [erro]); HOST -> RSM_HOST
#                   - rsm_common.sh e rsm_setup; apps/ via ${RSM_LIB_DIR}
#
# 2026.set  mlabru  - find -printf '%P': caminho relativo a REMOTE_DIR
#
# 2026.jun  mlabru  - ssh -o ConnectTimeout combinado com timeout do sistema
#
# 2026.may  mlabru  - lock global de instância
#
# 2026.apr  mlabru  initial version (Linux/Bash)
#
# depends on: python3 (RSM_VENV), flock, timeout e o catalog.db do 21.mvol (RSM_DBASE_FILE)

set -euo pipefail

# < configuração >---------------------------------------------------------------------

# diretório deste script (o cron chama pelo caminho absoluto)
RSM_RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# variáveis de configuração e funções compartilhadas (log, rsm_setup)
source "${RSM_RUN_DIR}/rsm_cfg.sh"
source "${RSM_RUN_DIR}/rsm_common.sh"

# nome desta máquina (só para o log)
RSM_HOST="$(hostname)"

# tempo máximo de cada programa Python, em segundos
RSM_PYTHON_TIMEOUT_SECS=60

# -------------------------------------------------------------------------------------
# garante uma única execução por vez (flock não bloqueante no fd 200).
#
# retorno: 0 se obteve o lock; se outra instância já roda, encerra o script
#          com 0 (não é erro: o cron só disparou cedo demais)
#
acquire_instance_lock()
{
    exec 200>"${RSM_INSTANCE_LOCK}"

    if ! flock -n 200; then
        # logger
        log "[info]: Radar Station Monitor já em execução; saindo."
        # quit
        exit 0
    fi

} # acquire_instance_lock

# -------------------------------------------------------------------------------------
# roda um programa Python de apps/ com timeout, mandando stdout para
# RSM_LOG_APP e stderr para RSM_LOG_ERR.
#
# uso:     run_python_step <programa> [argumentos...]
#          ex.: run_python_step rsmPNG -i status.json -o saida.png
#
# retorno: 0 (sucesso), 124 (timeout) ou o código de saída do programa
#
run_python_step()
{
    local ls_program="$1"
    shift

    # return code
    local li_rc=0

    timeout "${RSM_PYTHON_TIMEOUT_SECS}" python3 "${RSM_LIB_DIR}/apps/${ls_program}.py" "$@" \
        >> "${RSM_LOG_APP}" 2>> "${RSM_LOG_ERR}" || li_rc=$?

    if [ "${li_rc}" -eq 124 ]; then
        # logger
        log "[error]: ${ls_program} excedeu o timeout (${RSM_PYTHON_TIMEOUT_SECS}s)"

    elif [ "${li_rc}" -ne 0 ]; then
        # logger
        log "[error]: ${ls_program} falhou (código ${li_rc})"
    fi

    return "${li_rc}"

} # run_python_step

# -------------------------------------------------------------------------------------
# monitor de recepção radar
# qualquer falha encerra com rc 1.
#
main()
{
    # prepara o ambiente (rsm_setup) e cria os diretórios
    rsm_setup || exit 1

    # antes do primeiro log: o log é gravado em RSM_LOGS
    mkdir -p "${RSM_DATA}" "${RSM_LOGS}" "${RSM_OUTPUT}" "${RSM_STATE}" "${RSM_TMP}"

    # logger
    log "-----------------------------------------------------------------"
    log "[info]: Iniciando Radar Station Monitor (host=${RSM_HOST})..."

    # obtém o lock de instância
    acquire_instance_lock

    # python3 do virtualenv (numpy/matplotlib do rsmPNG.py)
    rsm_activate_venv

    # classifica os slots a partir do banco (rsmStatus.py -> RSM_STATUS_JSON)
    run_python_step rsmStatus -d "${RSM_DBASE_FILE}" -w "${RSM_WINDOW_HOURS}" \
                              -s "${RSM_STATUS_JSON}" || exit 1

    # desenha o PNG (rsmPNG.py -> RSM_PNG_FILE)
    run_python_step rsmPNG -w "${RSM_WINDOW_HOURS}" -i "${RSM_STATUS_JSON}" \
                           -o "${RSM_PNG_FILE}" || exit 1

    # logger
    log "[info]: Radar Station Monitor finalizado."

} # main

# < main >-----------------------------------------------------------------------------

# permite carregar as funções acima sem executar o main (testes)
[ "${RSM_RUN_NO_MAIN:-false}" = true ] && return 0

main

# < the end >--------------------------------------------------------------------------
