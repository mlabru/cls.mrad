# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_common.sh
# funções compartilhadas por rsm_run.sh e rsm_gui.sh.
#
# este arquivo é feito para ser importado com "source", nunca executado
# diretamente - por isso não declara seu próprio "set -e": herda as opções
# de shell do script que o importa.  Só define funções: nada roda no source.
#
# pré-requisito: rsm_cfg.sh já importado (ele define RSM_LOG_APP,
# RSM_LOG_ERR, RSM_PATH, RSM_LIB_DIR e GI_LOG_MAX_SIZE e importa o
# met_common.sh, de onde vêm met_log e check_log_size).
#
# 2026.out  mlabru  - rsm_activate_venv: python3 do RSM_VENV (~/.venv, o
#                     mesmo do 25.oflow e do 27.nowcast)
#                   - refatoração para legibilidade: o source repetido do
#                     met_common.sh saiu (o rsm_cfg.sh já o importa)
#                   - log() sobre met_log (UTC, rotação); rsm_setup
#
# 2026.ago  mlabru  initial version (Linux/Bash)
#
# depends on: rsm_cfg.sh (importado antes)
# shellcheck shell=bash

# -------------------------------------------------------------------------------------
# grava uma mensagem com timestamp UTC em RSM_LOG_APP (rotacionando antes, se
# passou do limite) e a ecoa em stderr.
#
# uso: log "[info]: mensagem"    (níveis: [info], [warn], [error])
#
log()
{
    met_log "${RSM_LOG_APP}" "${RSM_LOG_ERR}" "$@"

} # log

# -------------------------------------------------------------------------------------
# prepara o ambiente comum dos scripts:
# 1. cria RSM_PATH (numa máquina nova ele ainda não existe);
# 2. entra em RSM_PATH (caminhos relativos passam a valer a partir dali);
# 3. aponta o PYTHONPATH para apps/ do código (RSM_LIB_DIR).
#
# retorno: 1 se não conseguir entrar em RSM_PATH
#
rsm_setup()
{
    mkdir -p "${RSM_PATH}"
    cd "${RSM_PATH}" || return 1

    export PYTHONPATH="${RSM_LIB_DIR}/apps"

} # rsm_setup

# -------------------------------------------------------------------------------------
# ativa o virtualenv RSM_VENV (numpy, matplotlib, PyQt5), se existir; senão
# avisa e segue com o python3 do sistema.  Loga o python3 efetivo -- sob o
# cron ele pode ser diferente do da sessão interativa.
#
# pré-requisito: RSM_LOGS já existe (o log() grava lá)
#
rsm_activate_venv()
{
    if [ -f "${RSM_VENV}/bin/activate" ]; then
        # shellcheck source=/dev/null
        source "${RSM_VENV}/bin/activate"
    else
        log "[warn]: virtualenv inexistente (${RSM_VENV}); usando python3 do sistema."
    fi

    log "[info]: python3=$(command -v python3 || echo 'ausente')"

} # rsm_activate_venv

# < the end >--------------------------------------------------------------------------
