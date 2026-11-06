# -*- coding: utf-8 -*-
"""
Centro Logístico de Simulação Meteorológica
Copyright (c) 1995-2026, Instituto de Controle do Espaço Aéreo

rsmGUI
dashboard PyQt5 do monitor de recepção radar.  Mostra a mesma figura do
rsmPNG.py (rsm_figure.build_figure) e a atualiza a cada 60 s relendo o JSON
de status que o rsm_run.sh mantém em disco.

uso:
    python rsmGUI.py [-i STATUS.json]

2026.out  mlabru  guia de manutenção: _regen -> _reload_status, _tick ->
                  _update_clock (o nome diz o que o método faz); janela
                  padrão vem do rsm_config
2026.out  mlabru  banco como única fonte: lê o documento novo (stations +
                  source_last_update) e desenha o aviso de fonte parada
2026.out  mlabru  refatoração para legibilidade: args_parse -> arg_parse;
                  _build_ui dividido em _build_header/_build_controls/
                  _build_canvas; atributos declarados no __init__; recorte da
                  janela via rsm_figure.cap_window; log INFO em UTC
2025.nov  mlabru  initial version (Linux/Python)
"""
# < imports >──────────────────────────────────────────────────────────────────────────

# python library
import argparse
import datetime
import json
import logging
import sys
import time

# matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# PyQt
from PyQt5 import QtCore, QtGui, QtWidgets

# locals
import work.rsm_config as cfg
import work.rsm_figure as fg

# < constants >────────────────────────────────────────────────────────────────────────

# JSON de status padrão (o mesmo RSM_STATUS_JSON do rsm_cfg.sh, relativo a RSM_PATH)
CS_DEFAULT_STATUS_JSON = "data/temp/rsm_temp.json"

# limites do spin box, em horas (o valor inicial é cfg.CI_DEFAULT_WINDOW_HOURS)
CI_MIN_WINDOW_HOURS = 1
CI_MAX_WINDOW_HOURS = 72

# intervalos dos timers, em milissegundos
CI_REFRESH_INTERVAL_MS = 60_000
CI_CLOCK_INTERVAL_MS = 1_000

# resolução do PNG exportado
CI_PNG_DPI = 150

# < logging >──────────────────────────────────────────────────────────────────────────

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.INFO)

# < Dashboard >────────────────────────────────────────────────────────────────────────

class Dashboard(QtWidgets.QMainWindow):
    """
    janela principal do monitor.

    atributos públicos (lidos pelos testes):
    - n_hours: janela exibida, em horas (pode ser menor que a pedida);
    - total_slots: número de slots exibidos;
    - data: status por estação, já recortado para a janela;
    - ref_time: instante de referência da última leitura;
    - alert: aviso de fonte parada (rsm_figure.source_alert), ou None.
    """

    # ---------------------------------------------------------------------------------
    def __init__(self, fs_json_path: str = CS_DEFAULT_STATUS_JSON):
        """
        cria a janela, lê os dados e liga o auto-refresh.

        :param fs_json_path: JSON de status gerado por rsmStatus.py
        """
        super().__init__()

        self._json_path = fs_json_path

        # estado dos dados (preenchido por _reload_status)
        self.n_hours = cfg.CI_DEFAULT_WINDOW_HOURS
        self.total_slots = 0
        self.data = {}
        self.ref_time = datetime.datetime.now()
        self.alert = None

        # widgets (criados por _build_ui)
        self._clock = None
        self._clock_timer = None
        self._spin = None
        self._fig = None
        self._canvas = None

        self._reload_status()
        self._build_ui()

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(CI_REFRESH_INTERVAL_MS)

    # ---------------------------------------------------------------------------------
    def _apply_dark_theme(self) -> None:
        """
        aplica o tema escuro (paleta Qt + fundo da janela).
        """
        l_palette = QtGui.QPalette()
        l_palette.setColor(QtGui.QPalette.Window,     QtGui.QColor(cfg.CS_BG_DARK))
        l_palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(cfg.CS_TEXT_MAIN))
        l_palette.setColor(QtGui.QPalette.Base,       QtGui.QColor(cfg.CS_BG_PANEL))
        l_palette.setColor(QtGui.QPalette.Text,       QtGui.QColor(cfg.CS_TEXT_MAIN))
        l_palette.setColor(QtGui.QPalette.Button,     QtGui.QColor(cfg.CS_BG_CARD))
        l_palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(cfg.CS_TEXT_MAIN))

        self.setPalette(l_palette)
        self.setStyleSheet(f"QMainWindow,QWidget{{background:{cfg.CS_BG_DARK};}}")

    # ---------------------------------------------------------------------------------
    @staticmethod
    def _btn_style(fs_color: str) -> str:
        """
        stylesheet de botão "contorno" na cor dada.

        :param fs_color: cor do texto e da borda (#RRGGBB)
        :returns: stylesheet Qt
        """
        return (f"QPushButton{{background:transparent;color:{fs_color};"
                f"border:1px solid {fs_color};border-radius:4px;"
                f"padding:5px 14px;font-family:'Courier New';font-size:11px;}}"
                f"QPushButton:hover{{background:{fs_color}22;}}"
                f"QPushButton:pressed{{background:{fs_color}44;}}")

    # ---------------------------------------------------------------------------------
    @staticmethod
    def _spin_style() -> str:
        """
        stylesheet do spin box da janela.

        :returns: stylesheet Qt
        """
        return (f"QSpinBox{{background:{cfg.CS_BG_CARD};color:{cfg.CS_TEXT_MAIN};"
                f"border:1px solid {cfg.CS_GRAY};border-radius:4px;"
                f"padding:4px 8px;font-family:'Courier New';}}")

    # ---------------------------------------------------------------------------------
    def _build_ui(self) -> None:
        """
        monta a janela: cabeçalho, controles, canvas e barra de status.
        """
        self.setWindowTitle("Monitor de Recepção Radar")
        self.setMinimumSize(1400, 860)
        self._apply_dark_theme()

        l_central_widget = QtWidgets.QWidget()
        self.setCentralWidget(l_central_widget)

        l_main_layout = QtWidgets.QVBoxLayout(l_central_widget)
        l_main_layout.setContentsMargins(14, 14, 14, 14)
        l_main_layout.setSpacing(10)

        l_main_layout.addLayout(self._build_header())
        l_main_layout.addLayout(self._build_controls())
        l_main_layout.addWidget(self._build_canvas())

        self.statusBar().setStyleSheet(f"color:{cfg.CS_TEXT_SUB};"
                                       f"background:{cfg.CS_BG_PANEL};")

    # ---------------------------------------------------------------------------------
    def _build_header(self) -> QtWidgets.QHBoxLayout:
        """
        cabeçalho: título à esquerda, relógio (atualizado a cada 1 s) à direita.

        :returns: layout do cabeçalho
        """
        l_title = QtWidgets.QLabel(">>  MONITOR DE RECEPCAO RADAR")
        l_title.setFont(QtGui.QFont("Courier New", 14, QtGui.QFont.Bold))
        l_title.setStyleSheet(f"color: {cfg.CS_ACCENT};")

        self._clock = QtWidgets.QLabel()
        self._clock.setFont(QtGui.QFont("Courier New", 10))
        self._clock.setStyleSheet(f"color: {cfg.CS_TEXT_SUB};")
        self._update_clock()

        self._clock_timer = QtCore.QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(CI_CLOCK_INTERVAL_MS)

        l_header = QtWidgets.QHBoxLayout()
        l_header.addWidget(l_title)
        l_header.addStretch()
        l_header.addWidget(self._clock)

        return l_header

    # ---------------------------------------------------------------------------------
    def _build_controls(self) -> QtWidgets.QHBoxLayout:
        """
        linha de controles: "Janela:" [spin] | [Atualizar] [Exportar PNG].

        :returns: layout dos controles
        """
        l_window_label = QtWidgets.QLabel("Janela:")
        l_window_label.setStyleSheet(f"color:{cfg.CS_TEXT_SUB};")

        self._spin = QtWidgets.QSpinBox()
        self._spin.setRange(CI_MIN_WINDOW_HOURS, CI_MAX_WINDOW_HOURS)
        self._spin.setValue(cfg.CI_DEFAULT_WINDOW_HOURS)
        self._spin.setSuffix(" h")
        self._spin.setStyleSheet(self._spin_style())

        l_refresh_button = QtWidgets.QPushButton("↺  Atualizar")
        l_refresh_button.setStyleSheet(self._btn_style(cfg.CS_ACCENT))
        l_refresh_button.clicked.connect(self._refresh)

        l_export_button = QtWidgets.QPushButton("⬇  Exportar PNG")
        l_export_button.setStyleSheet(self._btn_style(cfg.CS_C_OK))
        l_export_button.clicked.connect(self._export)

        l_controls = QtWidgets.QHBoxLayout()
        l_controls.addWidget(l_window_label)
        l_controls.addWidget(self._spin)
        l_controls.addWidget(self._hline_spacer())
        l_controls.addWidget(l_refresh_button)
        l_controls.addWidget(l_export_button)

        return l_controls

    # ---------------------------------------------------------------------------------
    def _build_canvas(self) -> FigureCanvas:
        """
        canvas matplotlib com a figura inicial.

        :returns: o canvas (ocupa todo o espaço livre)
        """
        self._fig = fg.build_figure(self.data, self.ref_time,
                                    self.total_slots, self.n_hours, self.alert)

        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Expanding)
        return self._canvas

    # ---------------------------------------------------------------------------------
    def _export(self) -> None:
        """
        pergunta onde salvar e exporta a figura atual como PNG.

        se o usuário cancelar o diálogo, nada é feito.
        """
        ls_suggested_name = f"radar_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"

        ls_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salvar PNG",
                                                           ls_suggested_name,
                                                           "Imagens PNG (*.png)")
        if not ls_path:
            return

        self._fig.savefig(ls_path, dpi=CI_PNG_DPI, bbox_inches="tight",
                          facecolor=cfg.CS_BG_DARK, edgecolor="none")

        self.statusBar().showMessage(f"Exportado → {ls_path}", 8000)

    # ---------------------------------------------------------------------------------
    @staticmethod
    def _hline_spacer() -> QtWidgets.QFrame:
        """
        espaçador horizontal de 8 px entre o spin box e os botões.

        :returns: frame vazio de largura fixa
        """
        l_frame = QtWidgets.QFrame()
        l_frame.setFixedWidth(8)

        return l_frame

    # ---------------------------------------------------------------------------------
    def _refresh(self) -> None:
        """
        relê o JSON com a janela do spin box e redesenha a figura.

        chamado pelo botão "Atualizar" e pelo timer de 60 s.
        """
        self.n_hours = self._spin.value()
        self._reload_status()

        # troca a figura do canvas pela nova
        self._fig.clear()
        self._fig = fg.build_figure(self.data, self.ref_time,
                                    self.total_slots, self.n_hours, self.alert)
        self._canvas.figure = self._fig
        self._fig.set_canvas(self._canvas)
        self._canvas.draw()

        self.statusBar().showMessage(f"Atualizado em {datetime.datetime.now():%H:%M:%S}", 5000)

    # ---------------------------------------------------------------------------------
    def _reload_status(self) -> None:
        """
        lê o JSON de status e recorta para a janela pedida (self.n_hours).

        o arquivo guarda a janela com que rsmStatus.py rodou; se o spin pedir
        mais do que isso, n_hours é reduzido ao disponível, para o título da
        figura bater com o grid desenhado.  Também atualiza o aviso de fonte
        parada (self.alert).
        """
        with open(self._json_path, "r", encoding="utf-8") as l_file:
            ldct_document = json.load(l_file)

        ldct_status = fg.stations_from_document(ldct_document)
        self.data, self.total_slots, self.n_hours = fg.cap_window(ldct_status, self.n_hours)
        self.alert = fg.source_alert(ldct_document, datetime.datetime.now(datetime.timezone.utc))
        self.ref_time = datetime.datetime.now()

    # ---------------------------------------------------------------------------------
    def _update_clock(self) -> None:
        """
        atualiza o relógio do cabeçalho (hora local).
        """
        self._clock.setText(datetime.datetime.now().strftime("BRT  %Y-%m-%d  %H:%M:%S"))

# ─────────────────────────────────────────────────────────────────────────────────────
def arg_parse(flst_argv: list | None = None) -> argparse.Namespace:
    """
    lê os argumentos de linha de comando.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: namespace com inp
    """
    l_parser = argparse.ArgumentParser(description="Monitor de Recepção Radar")

    l_parser.add_argument("-i", "--inp", help="JSON de status (gerado por rsmStatus.py).",
                                         type=str, default=CS_DEFAULT_STATUS_JSON)

    return l_parser.parse_args(flst_argv)

# ─────────────────────────────────────────────────────────────────────────────────────
def main(flst_argv: list | None = None) -> int:
    """
    programa principal: abre o dashboard e roda o loop de eventos do Qt.

    :param flst_argv: argumentos (None = sys.argv[1:])
    :returns: código de saída do Qt
    """
    l_args = arg_parse(flst_argv)

    l_app = QtWidgets.QApplication(sys.argv)
    l_app.setApplicationName("Radar Monitor")

    l_main_window = Dashboard(l_args.inp)
    l_main_window.show()

    return l_app.exec_()

# ─────────────────────────────────────────────────────────────────────────────────────
# this is the bootstrap process

if "__main__" == __name__:
    # log em UTC, como os demais projetos met
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(datefmt="%Y/%m/%d %H:%M:%S",
                        format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.INFO)

    sys.exit(main())

# < the end >──────────────────────────────────────────────────────────────────────────
