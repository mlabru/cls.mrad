#!/usr/bin/env bash
#
# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_check.sh
# verificação EXTERNA do monrad para monitoramento, em duas partes:
# 1. o próprio monrad: idade do heartbeat que o rsm_run.sh grava ao fim de
#    cada execução bem sucedida (cls_heartbeat).  Pega um cron parado ou que
#    só falha -- o PNG congelado, que ninguém vê se não olhar o painel;
# 2. a recepção: apps/rsmCheck.py lê o JSON de status e alarma fonte parada,
#    estação muda e estação com perdas demais (regras no rsmCheck.py).
#
# o resultado é o pior dos dois (CRITICAL > UNKNOWN > WARNING > OK), numa
# linha no formato dos plugins do Nagios, como o vol_check.sh do 21.mvol e o
# ofl_check.sh do 25.oflow:
#   0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN
#
# não toca o log da aplicação nem o JSON: só lê.
#
# uso: rsm_check.sh
#   ex.: */10 * * * * bash <RSM_ROOT>/rsm_check.sh > /dev/null || <notificar>
#
# 2026.nov  mlabru  initial version (Linux/Bash)
#
# depends on: bash, coreutils, python3, rsm_cfg.sh (cls.env; cls_common.sh: cls_check_heartbeat)

set -euo pipefail

# < configuração >---------------------------------------------------------------------

# diretório deste script (para localizar rsm_cfg.sh)
RSM_CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# variáveis de configuração (e cls.env/cls_common.sh).  Só o rsm_cfg.sh: o
# rsm_common.sh não é necessário e o log da aplicação não é tocado
# shellcheck source=rsm_cfg.sh
source "${RSM_CHECK_DIR}/rsm_cfg.sh"

# códigos de saída (plugins do Nagios)
readonly CI_EXIT_OK=0
readonly CI_EXIT_WARNING=1
readonly CI_EXIT_CRITICAL=2
readonly CI_EXIT_UNKNOWN=3

# -------------------------------------------------------------------------------------
# gravidade de um código, para escolher o pior: CRITICAL vence UNKNOWN (um
# monrad parado é pior do que um que nunca rodou), que vence WARNING
#
# uso: severity <código>
#
severity()
{
    case "$1" in
        "${CI_EXIT_OK}")       echo 0 ;;
        "${CI_EXIT_WARNING}")  echo 1 ;;
        "${CI_EXIT_CRITICAL}") echo 3 ;;
        *)                     echo 2 ;;
    esac

} # severity

# -------------------------------------------------------------------------------------
# rótulo do código de saída
#
# uso: exit_label <código>
#
exit_label()
{
    case "$1" in
        "${CI_EXIT_OK}")       echo "OK" ;;
        "${CI_EXIT_WARNING}")  echo "WARNING" ;;
        "${CI_EXIT_CRITICAL}") echo "CRITICAL" ;;
        *)                     echo "UNKNOWN" ;;
    esac

} # exit_label

# -------------------------------------------------------------------------------------
# python3 do RSM_VENV, se existir (o mesmo do rsm_run.sh); senão o do sistema.
# O rsmCheck.py só usa a biblioteca padrão: roda mesmo com o matplotlib quebrado
#
python_bin()
{
    if [ -x "${RSM_VENV}/bin/python3" ]; then
        echo "${RSM_VENV}/bin/python3"
    else
        echo "python3"
    fi

} # python_bin

# -------------------------------------------------------------------------------------
# fluxo principal:
#   1. confere o heartbeat do rsm_run.sh (cls_check_heartbeat);
#   2. confere a recepção pelo JSON de status (rsmCheck.py);
#   3. escreve uma linha e sai com o pior código.
#
main()
{
    local li_run_rc=0 li_reception_rc=0 li_worst
    local ls_run_msg ls_reception_msg

    ls_run_msg="$(cls_check_heartbeat rsm_run "${RSM_RUN_OK_FILE}" "${RSM_CHECK_MAX_AGE_MIN}")" || \
        li_run_rc=$?

    ls_reception_msg="$("$(python_bin)" "${RSM_LIB_DIR}/apps/rsmCheck.py" \
                            -i "${RSM_STATUS_JSON}" --max-age "${RSM_CHECK_MAX_AGE_MIN}" \
                            2>&1 | tail -n 1)" || li_reception_rc=$?

    # tail -n 1: um traceback vira só a última linha (o pipefail mantém o
    # código do python3).  Só vale o código de uma linha que começa com o
    # rótulo dele: um python3 que quebrou (ex.: num import) sai com 1, que
    # não pode passar por WARNING -- vira UNKNOWN
    if (( li_reception_rc > CI_EXIT_UNKNOWN )) || \
       [[ "${ls_reception_msg}" != "$(exit_label "${li_reception_rc}"):"* ]]; then
        li_reception_rc="${CI_EXIT_UNKNOWN}"
    fi

    li_worst="${li_run_rc}"
    if [ "$(severity "${li_reception_rc}")" -gt "$(severity "${li_worst}")" ]; then
        li_worst="${li_reception_rc}"
    fi

    echo "$(exit_label "${li_worst}"): ${ls_run_msg} | recepção ${ls_reception_msg}"

    exit "${li_worst}"

} # main

# < main >-----------------------------------------------------------------------------

# permite carregar as funções acima sem executar o main (testes)
[ "${RSM_CHECK_NO_MAIN:-false}" = true ] && return 0

main

# < the end >--------------------------------------------------------------------------
