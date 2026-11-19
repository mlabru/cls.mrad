# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_cfg.sh
# configuração do rsm_run.sh (e de quem precisar dos mesmos caminhos).
#
# este arquivo é feito para ser importado com "source", nunca executado
# diretamente - por isso não declara seu próprio "set -e": herda as opções
# de shell do script que o importa.  Só define variáveis (e aplica a trava
# CLS_ENV=test): o mkdir/cd/PYTHONPATH é a função rsm_setup (rsm_common.sh).
#
# todas as variáveis têm o prefixo RSM_ (exceto GI_LOG_MAX_SIZE, lida pelo
# cls_common.sh).  As marcadas com ${X:-padrão} aceitam override pelo ambiente
# (é assim que o cls.test aponta o monrad para o ambiente de teste).
#
# a única fonte de dados do monrad é o catalog.db do 21.mvol: não há servidor
# remoto nem acesso aos .mvol.
#

# 2026.nov  mlabru  RSM_MVOL_SYNC_OK_FILE: heartbeat do vol_sync.sh do 21.mvol
#                   (só lido), para distinguir mvol parado de radares mudos;
#                   entra na trava de teste
#
# 2026.nov  mlabru  alarme: RSM_RUN_OK_FILE (heartbeat do rsm_run.sh) e
#                   RSM_CHECK_MAX_AGE_MIN, lidos pelo rsm_check.sh
#
# 2026.nov  mlabru  cls_setup_pythonpath: pacote Python comum (cls_common)
#                   por CLS_PYLIB, no lugar dos symlinks apps/{dbase,radar,util}
#
# 2026.nov  mlabru  CLS_LIB obrigatória (passo 2): sai o symlink cls_common.sh
#                   da raiz do repo; sem cls.env/CLS_LIB, erro explícito
#
# 2026.nov  mlabru  - banco/CAPPIs compartilhados: sem sobreposição própria,
#                     vêm de CLS_DBASE_FILE/CLS_CAPPI_DIR (cls.env, sob
#                     CLS_ROOT) antes do padrão antigo
#
# 2026.nov  mlabru  - cls.env (CLS_ENV_FILE, padrão ~/.config/cls/cls.env)
#                     carregado antes dos padrões; cls_common.sh vem de
#                     CLS_LIB, com o symlink ao lado do script como reserva
#                   - prefixo met -> cls (cls_log, cls_check_test_env,
#                     CLS_ENV, CLS_TST_ROOT)
#
# 2026.nov  mlabru  - comentários sem o rsm_gui.sh/rsmGUI.py/PyQt5 (removidos)
#                   - met_common.sh -> cls_common.sh (o arquivo saiu de
#                     04.dvl/bash para o repo cls.common); o source do
#                     arquivo antigo, inexistente, derrubava o rsm_run.sh
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
#                     trava via cls_check_test_env (realpath -m)
#                   - ambiente de teste: override pelo ambiente e trava
#                     CLS_ENV=test; RSM_LIB_DIR
#
# 2026.ago  mlabru  initial version (Linux/Bash)
#
# depends on: bash, cls_common.sh
# shellcheck shell=bash

# < configuração >---------------------------------------------------------------------

# diretório do código (este arquivo, os scripts e apps/)
RSM_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ambiente da instalação (cls.env: CLS_LIB e sobreposições), carregado
# antes dos padrões abaixo; "set -a" exporta para os programas Python.
# Precedência: ambiente do processo > cls.env > padrões deste arquivo (ver
# cls.common/etc/cls.env.example)
CLS_ENV_FILE="${CLS_ENV_FILE:-${HOME:-}/.config/cls/cls.env}"
if [ -r "${CLS_ENV_FILE}" ]; then set -a; source "${CLS_ENV_FILE}"; set +a; fi

# raiz dos dados e logs do monrad
RSM_PATH="${RSM_PATH:-/home/${USER}/Public/mrad}"

RSM_DATA="${RSM_PATH}/data"
RSM_LOGS="${RSM_PATH}/logs"

RSM_OUTPUT="${RSM_DATA}/output"
RSM_STATE="${RSM_DATA}/state"
RSM_TMP="${RSM_DATA}/temp"

# catalog.db do 21.mvol: ÚNICA fonte de dados do monrad (tabela
# vol_raw_observations, gravada SÓ pelo 21.mvol; o monrad apenas lê).  O
# padrão é o mesmo VOL_DBASE_FILE do vol_cfg.sh.  Ordem: RSM_DBASE_FILE >
# CLS_DBASE_FILE (cls.env, raiz CLS_ROOT) > padrão
RSM_DBASE_FILE="${RSM_DBASE_FILE:-${CLS_DBASE_FILE:-/home/${USER}/Public/mvol/data/dbase/catalog.db}}"

# heartbeat do vol_sync.sh do 21.mvol (o VOL_SYNC_OK_FILE do vol_cfg.sh), só
# lido: com ele o monrad distingue "mvol parado" de "radares mudos".  Vem do
# VOL_PATH do mvol (cls.env ou ambiente; o cls.test o exporta), como o padrão
# do vol_cfg.sh.  Ausente ou ilegível: a fonte é julgada só pelo banco
RSM_MVOL_SYNC_OK_FILE="${RSM_MVOL_SYNC_OK_FILE:-${VOL_PATH:-/home/${USER}/Public/mvol}/data/state/vol_sync.ok}"

# JSON de status (saída do rsmStatus.py; entrada do rsmPNG.py)
RSM_STATUS_JSON="${RSM_TMP}/rsm_temp.json"
# PNG estático do monitor (saída do rsmPNG.py)
RSM_PNG_FILE="${RSM_OUTPUT}/rsm_out.png"

# lock de instância (impede duas execuções simultâneas de rsm_run.sh)
RSM_INSTANCE_LOCK="${RSM_STATE}/.rsm.lock"

# heartbeat: último sucesso do rsm_run.sh (cls_heartbeat), conferido pelo
# rsm_check.sh -- descobre um cron parado ou que só falha (PNG congelado)
RSM_RUN_OK_FILE="${RSM_STATE}/rsm_run.ok"

# idade máxima, em minutos, do heartbeat e do JSON de status antes do alarme
# (rsm_check.sh); 30 = três rodadas perdidas de um cron */10
RSM_CHECK_MAX_AGE_MIN="${RSM_CHECK_MAX_AGE_MIN:-30}"

# logs
RSM_LOG_APP="${RSM_LOGS}/rsm_monrad.log"
RSM_LOG_ERR="${RSM_LOGS}/rsm_monrad.err"

# janela de monitoramento, em horas
RSM_WINDOW_HOURS=24

# virtualenv com numpy e matplotlib -- o mesmo ~/.venv do 25.oflow
# (OFL_VENV) e do 27.nowcast (NWC_VENV). Sem ele, usa o python3 do sistema
# (rsm_activate_venv, em rsm_common.sh)
RSM_VENV="${RSM_VENV:-${HOME:-/home/$(id -un)}/.venv}"

# limite de tamanho de cada log antes da rotação (10MB; lido pelo cls_common.sh)
GI_LOG_MAX_SIZE=$((10 * 1024 * 1024))

# < trava do ambiente de teste >-------------------------------------------------------

# cls_check_test_env (cls_common.sh, de CLS_LIB, do cls.env;
# comum aos projetos cls)
# CLS_LIB (cls.env) é obrigatória: sem ela não há cls_common.sh -- falha
# aqui, com a causa, em vez de num "command not found" mais adiante
if [ ! -r "${CLS_LIB:-}/cls_common.sh" ]; then
    echo "[error]: CLS_LIB='${CLS_LIB:-}' sem cls_common.sh; defina-a no cls.env (${CLS_ENV_FILE:-~/.config/cls/cls.env})" >&2
    exit 1
fi
source "${CLS_LIB}/cls_common.sh"

# com CLS_ENV=test, nada pode apontar para fora de CLS_TST_ROOT
cls_check_test_env "${RSM_PATH}" "${RSM_DBASE_FILE}" "${RSM_MVOL_SYNC_OK_FILE}" || exit 1

# < pacote Python comum >--------------------------------------------------------------

# cls_common (dbase, radar, util; CLS_PYLIB no cls.env) no PYTHONPATH,
# exportado para todo programa Python chamado daqui (cls_common.sh)
cls_setup_pythonpath || exit 1

# < the end >--------------------------------------------------------------------------
