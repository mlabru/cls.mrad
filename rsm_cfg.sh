# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_cfg.sh
# configuração compartilhada por rsm_run.sh e rsm_gui.sh.
#
# este arquivo é feito para ser importado com "source", nunca executado
# diretamente - por isso não declara seu próprio "set -e": herda as opções
# de shell do script que o importa.  Só define variáveis (e aplica a trava
# MET_ENV=test): o mkdir/cd/PYTHONPATH é a função rsm_setup (rsm_common.sh).
#
# todas as variáveis têm o prefixo RSM_ (exceto GI_LOG_MAX_SIZE, lida pelo
# met_common.sh).  As marcadas com ${X:-padrão} aceitam override pelo ambiente
# (é assim que o 21.mvol/tst_env aponta o monrad para o ambiente de teste).
#
# a única fonte de dados do monrad é o catalog.db do 21.mvol: não há servidor
# remoto nem acesso aos .mvol.
#

# 2026.out  mlabru  - RSM_VENV (padrão ~/.venv, o mesmo do 25.oflow e do
#                     27.nowcast): o numpy/matplotlib do ~/.local quebrava
#                     o rsmPNG.py (matplotlib compilado p/ NumPy 1.x)
#                   - banco como única fonte: RSM_REMOTE_* e
#                     RSM_LISTING_FILE saíram (sem ssh/find); RSM_DBASE_FILE
#                     aponta por padrão para o banco do mvol (antes um
#                     arquivo que ninguém gravava em produção); trava sem -r
#                   - normalização com 21.mvol/25.oflow/27.nowcast: GI_HORAS
#                     -> RSM_WINDOW_HOURS, RSM_TMP_FILE -> RSM_STATUS_JSON,
#                     RSM_OUT_FILE -> RSM_LISTING_FILE (nomes que dizem o
#                     que o arquivo é)
#                   - REMOTE_* -> RSM_REMOTE_*; setup movido para rsm_setup;
#                     trava via met_check_test_env (realpath -m)
#                   - ambiente de teste: override pelo ambiente e trava
#                     MET_ENV=test; RSM_LIB_DIR
#
# 2026.ago  mlabru  initial version (Linux/Bash)
#
# depends on: bash, met_common.sh
# shellcheck shell=bash

# < configuração >---------------------------------------------------------------------

# diretório do código (este arquivo, os scripts e apps/)
RSM_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# raiz dos dados e logs do monrad
RSM_PATH="${RSM_PATH:-/home/${USER}/Public/mrad}"

RSM_DATA="${RSM_PATH}/data"
RSM_LOGS="${RSM_PATH}/logs"

RSM_OUTPUT="${RSM_DATA}/output"
RSM_STATE="${RSM_DATA}/state"
RSM_TMP="${RSM_DATA}/temp"

# catalog.db do 21.mvol: ÚNICA fonte de dados do monrad (tabela
# vol_raw_observations, gravada SÓ pelo 21.mvol; o monrad apenas lê).  O
# padrão é o mesmo VOL_DBASE_FILE do vol_cfg.sh
RSM_DBASE_FILE="${RSM_DBASE_FILE:-/home/${USER}/Public/mvol/data/dbase/catalog.db}"

# JSON de status (saída do rsmStatus.py; entrada do rsmPNG.py e do rsmGUI.py)
RSM_STATUS_JSON="${RSM_TMP}/rsm_temp.json"
# PNG estático do monitor (saída do rsmPNG.py)
RSM_PNG_FILE="${RSM_OUTPUT}/rsm_out.png"

# lock de instância (impede duas execuções simultâneas de rsm_run.sh)
RSM_INSTANCE_LOCK="${RSM_STATE}/.rsm.lock"

# logs
RSM_LOG_APP="${RSM_LOGS}/rsm_monrad.log"
RSM_LOG_ERR="${RSM_LOGS}/rsm_monrad.err"

# janela de monitoramento, em horas
RSM_WINDOW_HOURS=24

# virtualenv com numpy, matplotlib e PyQt5 -- o mesmo ~/.venv do 25.oflow
# (OFL_VENV) e do 27.nowcast (NWC_VENV). Sem ele, usa o python3 do sistema
# (rsm_activate_venv, em rsm_common.sh)
RSM_VENV="${RSM_VENV:-${HOME:-/home/$(id -un)}/.venv}"

# limite de tamanho de cada log antes da rotação (10MB; lido pelo met_common.sh)
GI_LOG_MAX_SIZE=$((10 * 1024 * 1024))

# < trava do ambiente de teste >-------------------------------------------------------

# met_check_test_env (met_common.sh, symlink para 04.dvl/bash, comum aos
# projetos met)
source "${RSM_LIB_DIR}/met_common.sh"

# com MET_ENV=test, nada pode apontar para fora de MET_TST_ROOT
met_check_test_env "${RSM_PATH}" "${RSM_DBASE_FILE}" || exit 1

# < the end >--------------------------------------------------------------------------
