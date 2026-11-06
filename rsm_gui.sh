#!/usr/bin/env bash
#
# Centro Logístico de Simulação Meteorológica
# Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo
#
# rsm_gui.sh
# abre o dashboard (apps/rsmGUI.py) apontado para o mesmo JSON de status que
# o rsm_run.sh mantém atualizado (RSM_STATUS_JSON).
#
# o próprio rsmGUI.py relê esse arquivo a cada 60 s / clique em "Atualizar";
# este script só acha o caminho certo e falha com uma mensagem clara se o
# rsm_run.sh ainda não tiver rodado nenhuma vez.
#
# 2026.out  mlabru  - python3 do RSM_VENV (rsm_activate_venv), como o
#                     25.oflow e o 27.nowcast
# 2026.out  mlabru  - normalização com 21.mvol/25.oflow/27.nowcast:
#                     require_status_file e main; set -euo pipefail após o
#                     cabeçalho; nível [error] (era [erro]); RSM_TMP_FILE ->
#                     RSM_STATUS_JSON
# 2026.out  mlabru  - rsm_common.sh e rsm_setup; apps/ via ${RSM_LIB_DIR}
# 2026.ago  mlabru  initial version (Linux/Bash)
#
# depends on: python3 (RSM_VENV), PyQt5 e um display (X11/Wayland)

set -euo pipefail

# < configuração >---------------------------------------------------------------------

# diretório deste script (para localizar rsm_cfg.sh de qualquer lugar)
RSM_GUI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# variáveis de configuração e funções compartilhadas (log, rsm_setup)
source "${RSM_GUI_DIR}/rsm_cfg.sh"
source "${RSM_GUI_DIR}/rsm_common.sh"

# -------------------------------------------------------------------------------------
# sem o JSON de status, o rsmGUI.py quebraria com FileNotFoundError: avisa
# o motivo e encerra o script com rc 1.
#
require_status_file()
{
    if [ -f "${RSM_STATUS_JSON}" ]; then
        return 0
    fi

    log "[error]: status ainda não coletado (${RSM_STATUS_JSON} não existe)."
    log "[error]: rode rsm_run.sh pelo menos uma vez antes de abrir o dashboard."
    exit 1

} # require_status_file

# -------------------------------------------------------------------------------------
# fluxo principal:
# 1. prepara o ambiente (rsm_setup) e o diretório de logs;
# 2. confere se o JSON de status existe;
# 3. ativa o virtualenv (rsm_activate_venv);
# 4. abre o dashboard, repassando argumentos extras (ex.: -i outro.json).
#
main()
{
    rsm_setup || exit 1

    # o log() grava em RSM_LOGS: precisa existir antes da primeira mensagem
    mkdir -p "${RSM_LOGS}"

    require_status_file

    rsm_activate_venv

    exec python3 "${RSM_LIB_DIR}/apps/rsmGUI.py" -i "${RSM_STATUS_JSON}" "$@"

} # main

# < main >-----------------------------------------------------------------------------

main "$@"

# < the end >--------------------------------------------------------------------------
