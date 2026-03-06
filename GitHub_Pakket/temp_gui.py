import sys
import time
import os
import csv
import math
from collections import deque
from datetime import datetime

import serial
from serial.tools import list_ports

from PySide6.QtCore import QTimer, Qt, QEvent
from PySide6.QtGui import QIcon, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QGridLayout, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLineEdit
)

import pyqtgraph as pg


BAUD = 115200
SAMPLE_HZ = 5.0
WINDOW_SECONDS = 2 * 60
MAX_POINTS = int(WINDOW_SECONDS * SAMPLE_HZ)
MIN_Y_SPAN = 3.0
RECONNECT_INTERVAL_S = 2
RECONNECT_INTERVAL_MS = RECONNECT_INTERVAL_S * 1000

LINE_COLOR = "#16a34a"
APP_BG = "#ffffff"
CARD_BG = "#f3f4f6"
PLOT_BG = CARD_BG
BORDER = "#d1d5db"
TEXT = "#111827"
SUBTEXT = "#4b5563"
GRID = "#cbd5e1"
AXIS = "#6b7280"
WINDOWS_APP_ID = "schoolv2.temptestsoftware.temperatuurmonitor"


def resource_path(relative_path: str) -> str:
    # Ondersteunt zowel lokaal draaien als PyInstaller onefile (_MEIPASS).
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def set_windows_app_id():
    # Zorgt dat Windows taakbalk/startmenu de juiste app-identiteit en icon koppeling gebruikt.
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


def find_arduino_port():
    # Zoek eerst expliciet op bekende Arduino/USB-serial kenmerken,
    # en gebruik daarna een veilige fallback als er maar 1 COM-poort is.
    for p in list_ports.comports():
        desc = (p.description or "").lower()
        manu = (p.manufacturer or "").lower()
        if any(k in desc for k in ["arduino", "ch340", "usb serial", "usb-serial"]) or any(k in manu for k in ["arduino", "wch"]):
            return p.device
    ports = [p.device for p in list_ports.comports()]
    if len(ports) == 1:
        return ports[0]
    return None


class SensorPlot(QFrame):
    def __init__(self, short_name: str):
        super().__init__()
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.title = QLabel(short_name)
        self.title.setObjectName("cardTitle")

        self.value = QLabel("--.-°C")
        self.value.setObjectName("cardValue")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.value)
        layout.addLayout(header)

        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot)

        # Houd de plot compact zodat 4 kaarten goed binnen het venster passen.
        self.plot.setContentsMargins(0, 0, 0, 0)
        self.plot.getPlotItem().layout.setContentsMargins(0, 0, 0, 0)

        self.plot.setBackground(PLOT_BG)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.25)

        left = self.plot.getAxis("left")
        bottom = self.plot.getAxis("bottom")

        left.setTextPen(pg.mkPen(AXIS))
        bottom.setTextPen(pg.mkPen(AXIS))
        left.setPen(pg.mkPen(BORDER))
        bottom.setPen(pg.mkPen(BORDER))

        left.setWidth(30)
        bottom.setHeight(18)
        left.setStyle(tickTextOffset=4)
        bottom.setStyle(tickTextOffset=4)

        tick_font = pg.QtGui.QFont()
        tick_font.setPointSize(8)
        left.setTickFont(tick_font)
        bottom.setTickFont(tick_font)

        self.plot.getPlotItem().getViewBox().setBackgroundColor(PLOT_BG)

        # Teken hoofdcurve + subtiele glow voor betere leesbaarheid.
        glow = pg.mkColor(LINE_COLOR)
        glow.setAlpha(60)
        self.curve_glow = self.plot.plot(pen=pg.mkPen(glow, width=6))
        self.curve = self.plot.plot(pen=pg.mkPen(LINE_COLOR, width=2))

        self.plot.setXRange(-WINDOW_SECONDS, 0, padding=0)

        # As-hints worden als overlay geplaatst zodat er geen extra plotruimte verloren gaat.
        self.y_axis_hint = QLabel("°C", self.plot)
        self.x_axis_hint = QLabel("s", self.plot)
        for hint in (self.y_axis_hint, self.x_axis_hint):
            hint.setStyleSheet(f"color: {AXIS}; font-size: 9px; font-weight: 600; background: transparent;")
            hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            hint.adjustSize()

        self.plot.installEventFilter(self)
        self._position_axis_hints()

        self.t0 = time.time()
        self.x = deque(maxlen=MAX_POINTS)
        self.y = deque(maxlen=MAX_POINTS)
        self.break_on_next_point = False

    def _position_axis_hints(self):
        left_w = int(self.plot.getAxis("left").width())
        bottom_h = int(self.plot.getAxis("bottom").height())

        self.y_axis_hint.adjustSize()
        self.x_axis_hint.adjustSize()

        y_x = 2
        y_y = 0
        self.y_axis_hint.move(y_x, y_y)

        x_x = max(left_w + 2, self.plot.width() - self.x_axis_hint.width() - 4)
        x_y = max(0, self.plot.height() - bottom_h + 1)
        self.x_axis_hint.move(x_x, x_y)

    def eventFilter(self, obj, event):
        if obj is self.plot and event.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self._position_axis_hints)
        return super().eventFilter(obj, event)

    def add_point(self, temp_c: float):
        now = time.time()
        age = now - self.t0

        if self.break_on_next_point and len(self.x) > 0:
            # Voeg een lijn-onderbreking toe na reconnect, zodat meetgaten zichtbaar blijven.
            self.x.append(age - 1e-3)
            self.y.append(float("nan"))
            self.break_on_next_point = False

        self.x.append(age)
        self.y.append(temp_c)

        self.value.setText(f"{temp_c:0.1f}°C")

        # Plot met relatieve tijd: meest recente punt staat altijd op x=0.
        x0 = self.x[-1]
        x_rel = [xi - x0 for xi in self.x]
        y_list = list(self.y)

        self.curve_glow.setData(x_rel, y_list)
        self.curve.setData(x_rel, y_list)

        self.plot.setXRange(-WINDOW_SECONDS, 0, padding=0)

    def set_shared_y_range(self, ymin: float, ymax: float):
        self.plot.setYRange(ymin, ymax, padding=0)

    def mark_gap(self):
        self.break_on_next_point = True


class BrowseButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self._selected_text = ""

    def set_selected_text(self, text: str):
        self._selected_text = text
        if self._selected_text:
            self.setText(self._selected_text)
        else:
            self.setText("Bladeren")

    def enterEvent(self, event):
        self.setText("Bladeren")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._selected_text:
            self.setText(self._selected_text)
        else:
            self.setText("Bladeren")
        super().leaveEvent(event)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temperatuur Monitor")
        self.resize(460, 560)
        self.setObjectName("root")

        # Hoofdopbouw: statusrij, 2x2 grafieken, omgevingstemperatuurkaart en logknoppen.
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(2, 0, 2, 0)
        status_row.setSpacing(6)

        self.conn_dot = QFrame()
        self.conn_dot.setObjectName("connDot")
        self.conn_dot.setProperty("state", "searching")
        self.conn_dot.setFixedSize(10, 10)

        self.status = QLabel("Opstarten: Arduino zoeken...")
        self.status.setObjectName("status")

        status_row.addWidget(self.conn_dot)
        status_row.addWidget(self.status, 1)
        root.addLayout(status_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

        self.p1 = SensorPlot("Sensor 1")
        self.p2 = SensorPlot("Sensor 2")
        self.p3 = SensorPlot("Sensor 3")
        self.p4 = SensorPlot("Sensor 4")

        grid.addWidget(self.p1, 0, 0)
        grid.addWidget(self.p2, 0, 1)
        grid.addWidget(self.p3, 1, 0)
        grid.addWidget(self.p4, 1, 1)

        self.env_card = QFrame()
        self.env_card.setObjectName("card")
        root.addWidget(self.env_card)

        env_outer = QHBoxLayout(self.env_card)
        env_outer.setContentsMargins(8, 8, 8, 8)
        env_outer.setSpacing(0)
        env_outer.addStretch(1)

        env_controls = QHBoxLayout()
        env_controls.setSpacing(8)

        self.lbl_env = QLabel("Omgevingstemperatuur:")
        self.input_env_temp = QLineEdit()
        self.input_env_temp.setPlaceholderText("0.0")
        self.input_env_temp.setFixedWidth(80)
        self.input_env_temp.setMaxLength(8)
        env_validator = QDoubleValidator(-100.0, 1000.0, 2, self)
        env_validator.setNotation(QDoubleValidator.StandardNotation)
        self.input_env_temp.setValidator(env_validator)
        self.lbl_env_unit = QLabel("°C")
        self.btn_log_env_temp = QPushButton("Loggen")
        self.btn_log_env_temp.setObjectName("mainButton")
        self.btn_log_env_temp.setEnabled(False)

        env_controls.addWidget(self.lbl_env)
        env_controls.addWidget(self.input_env_temp)
        env_controls.addWidget(self.lbl_env_unit)
        env_controls.addWidget(self.btn_log_env_temp)
        env_outer.addLayout(env_controls)
        env_outer.addStretch(1)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        root.addLayout(controls)

        self.btn_browse = BrowseButton("Bladeren")
        self.btn_browse.setObjectName("mainButton")
        self.btn_toggle_log = QPushButton("Loggen starten")
        self.btn_toggle_log.setObjectName("logButton")
        self.btn_toggle_log.setProperty("mode", "start")
        self.btn_toggle_log.setEnabled(False)

        controls.addWidget(self.btn_browse)
        controls.addWidget(self.btn_toggle_log)

        self.ser = None
        self.connected_port = ""
        self.logging_enabled = False
        self.log_base_dir = ""
        self.current_log_folder = ""
        self.current_log_path = ""
        self.log_file = None
        self.log_writer = None
        self.retry_reason = "Arduino niet gevonden."
        self.retry_state = "searching"
        self.retry_seconds_left = RECONNECT_INTERVAL_S

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(1000)
        self.reconnect_timer.timeout.connect(self._reconnect_tick)

        self.btn_browse.clicked.connect(self.choose_log_path)
        self.btn_toggle_log.clicked.connect(self.toggle_logging)
        self.btn_log_env_temp.clicked.connect(self.log_environment_temperature)

        self.connect_serial(show_retry_message=True)

        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / SAMPLE_HZ))
        self.timer.timeout.connect(self.poll_serial)
        self.timer.start()

    def _refresh_status_style(self):
        self.conn_dot.style().unpolish(self.conn_dot)
        self.conn_dot.style().polish(self.conn_dot)

    def _set_connection_state(self, state: str, text: str):
        self.conn_dot.setProperty("state", state)
        self._refresh_status_style()
        self.status.setText(text)

    def _start_reconnect_loop(self, reason: str, state: str):
        self.retry_reason = reason
        self.retry_state = state
        self.retry_seconds_left = RECONNECT_INTERVAL_S
        self._set_connection_state(
            state,
            f"{reason} Opnieuw proberen over {self.retry_seconds_left}s..."
        )
        if not self.reconnect_timer.isActive():
            self.reconnect_timer.start()

    def _stop_reconnect_loop(self):
        if self.reconnect_timer.isActive():
            self.reconnect_timer.stop()
        self.retry_seconds_left = RECONNECT_INTERVAL_S

    def _reconnect_tick(self):
        if self.ser and self.ser.is_open:
            self._stop_reconnect_loop()
            return

        self.retry_seconds_left -= 1
        if self.retry_seconds_left <= 0:
            if self.connect_serial(show_retry_message=False):
                return
            self.retry_seconds_left = RECONNECT_INTERVAL_S

        self._set_connection_state(
            self.retry_state,
            f"{self.retry_reason} Opnieuw proberen over {self.retry_seconds_left}s..."
        )

    def _update_log_button_state(self):
        can_start = bool(self.log_base_dir and self.ser and self.ser.is_open and not self.logging_enabled)
        can_stop = bool(self.logging_enabled)
        self.btn_toggle_log.setEnabled(can_start or can_stop)
        self.btn_log_env_temp.setEnabled(bool(self.log_base_dir))

    def _ensure_session_folder(self):
        # Beide logknoppen delen dezelfde sessiemap; de map wordt pas aangemaakt bij eerste schrijfactie.
        if self.current_log_folder:
            return self.current_log_folder
        if not self.log_base_dir:
            return ""
        self.current_log_folder = self._make_session_folder()
        return self.current_log_folder

    def _get_env_log_path(self):
        if not self.current_log_folder:
            return ""
        return os.path.join(self.current_log_folder, "omgevingstemperatuur.csv")

    def log_environment_temperature(self):
        if not self.log_base_dir:
            self.status.setText("Kies eerst een logmap voor omgevingstemperatuur")
            return

        raw = self.input_env_temp.text().strip().replace(",", ".")
        if not raw:
            self.status.setText("Vul een omgevingstemperatuur in")
            return

        try:
            env_temp = float(raw)
        except ValueError:
            self.status.setText("Omgevingstemperatuur moet een getal zijn")
            return

        try:
            self._ensure_session_folder()
        except Exception as e:
            self.status.setText(f"Kan logmap niet maken: {e}")
            return

        env_log_path = self._get_env_log_path()
        if not env_log_path:
            self.status.setText("Geen logmap beschikbaar voor omgevingstemperatuur")
            return

        try:
            is_new_file = not os.path.exists(env_log_path) or os.path.getsize(env_log_path) == 0
            with open(env_log_path, "a", newline="", encoding="utf-8") as env_file:
                writer = csv.writer(env_file)
                if is_new_file:
                    writer.writerow(["timestamp", "omgevingstemp"])
                ts = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                writer.writerow([ts, f"{env_temp:.2f}"])

            self.input_env_temp.clear()
            self.status.setText(f"Omgevingstemperatuur gelogd: {env_temp:.2f}°C")
        except Exception as e:
            self.status.setText(f"Schrijffout omgevingstemperatuur: {e}")

    def _close_serial(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.connected_port = ""

    def _handle_disconnect(self, reason: str):
        self._close_serial()

        for p in (self.p1, self.p2, self.p3, self.p4):
            p.mark_gap()

        if self.logging_enabled:
            self.stop_logging(status_text=f"{reason} - logging gestopt")

        self._start_reconnect_loop(reason, "retrying")
        self._update_log_button_state()

    def choose_log_path(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        folder = QFileDialog.getExistingDirectory(
            self,
            "Kies loglocatie",
            default_dir
        )
        if not folder:
            return

        self.log_base_dir = folder
        short_text = self.log_base_dir[:25]
        self.btn_browse.set_selected_text(short_text)
        self._update_log_button_state()
        self.status.setText(f"Loglocatie gekozen: {self.log_base_dir}")

    def _make_session_folder(self):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder = os.path.join(self.log_base_dir, f"Temperatuur_meting_{ts}")
        os.makedirs(folder, exist_ok=False)
        return folder

    def start_logging(self):
        # Start sensorlogging in de gedeelde sessiemap en maak een nieuw CSV-bestand voor sensordata.
        if not self.log_base_dir:
            return False
        if not (self.ser and self.ser.is_open):
            self.status.setText("Niet verbonden met Arduino: logging niet gestart")
            return False

        try:
            folder = self._ensure_session_folder()
            if not folder:
                self.status.setText("Geen logmap beschikbaar")
                return False
            self.current_log_path = os.path.join(self.current_log_folder, "metingen.csv")

            self.log_file = open(self.current_log_path, "w", newline="", encoding="utf-8")
            self.log_writer = csv.writer(self.log_file)
            self.log_writer.writerow(["timestamp", "sensor1", "sensor2", "sensor3", "sensor4"])
            self.log_file.flush()

            self.logging_enabled = True
            self.btn_toggle_log.setText("Loggen stoppen")
            self.btn_toggle_log.setProperty("mode", "stop")
            self.btn_toggle_log.style().unpolish(self.btn_toggle_log)
            self.btn_toggle_log.style().polish(self.btn_toggle_log)
            self.btn_browse.setEnabled(False)
            self.status.setText(f"Logging actief: {self.current_log_folder}")
            return True
        except Exception as e:
            self.logging_enabled = False
            self.log_file = None
            self.log_writer = None
            self.current_log_folder = ""
            self.current_log_path = ""
            self.status.setText(f"Kan logbestand niet openen: {e}")
            return False

    def stop_logging(self, status_text: str = "Logging gestopt"):
        # Sluit de actieve sensorsessie; volgende logactie maakt weer een nieuwe sessiemap.
        self.logging_enabled = False
        self.log_writer = None
        try:
            if self.log_file:
                self.log_file.close()
        except Exception:
            pass
        self.log_file = None
        self.current_log_folder = ""
        self.current_log_path = ""

        self.btn_toggle_log.setText("Loggen starten")
        self.btn_toggle_log.setProperty("mode", "start")
        self.btn_toggle_log.style().unpolish(self.btn_toggle_log)
        self.btn_toggle_log.style().polish(self.btn_toggle_log)
        self.btn_browse.setEnabled(True)
        self._update_log_button_state()
        self.status.setText(status_text)

    def toggle_logging(self):
        if self.logging_enabled:
            self.stop_logging()
        else:
            self.start_logging()

    def connect_serial(self, show_retry_message: bool = True):
        # Verbind met de Arduino en schakel over naar automatische reconnect bij fouten.
        if self.ser and self.ser.is_open:
            return True

        port = find_arduino_port()
        if not port:
            self.retry_reason = "Arduino niet gevonden."
            self.retry_state = "searching"
            if show_retry_message:
                self._start_reconnect_loop(self.retry_reason, self.retry_state)
            self._update_log_button_state()
            return False

        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            self.connected_port = port
            self._set_connection_state("connected", f"Verbonden: {port} @ {BAUD}")
            self._update_log_button_state()
            self._stop_reconnect_loop()
            return True
        except Exception as e:
            self._close_serial()
            self.retry_reason = f"Kan {port} niet openen ({e})."
            self.retry_state = "searching"
            if show_retry_message:
                self._start_reconnect_loop(self.retry_reason, self.retry_state)
            self._update_log_button_state()
            return False

    def _update_shared_y_axis(self):
        # Gebruik 1 gedeelde y-schaal zodat alle vier sensorgrafieken direct vergelijkbaar blijven.
        ys = []
        for p in (self.p1, self.p2, self.p3, self.p4):
            if len(p.y) > 0:
                ys.extend([v for v in p.y if not math.isnan(v)])

        if len(ys) < 5:
            return

        ymin = min(ys)
        ymax = max(ys)

        margin = max(0.3, 0.15 * (ymax - ymin))
        if ymin == ymax:
            ymin -= 0.5
            ymax += 0.5
        else:
            ymin -= margin
            ymax += margin

        span = ymax - ymin
        if span < MIN_Y_SPAN:
            center = (ymin + ymax) / 2.0
            half = MIN_Y_SPAN / 2.0
            ymin = center - half
            ymax = center + half

        for p in (self.p1, self.p2, self.p3, self.p4):
            p.set_shared_y_range(ymin, ymax)

    def poll_serial(self):
        # Lees seriele data in, update grafieken en schrijf sensordata weg als logging actief is.
        if not self.ser:
            return

        if not self.ser.is_open:
            self._handle_disconnect("Arduino verbinding verbroken.")
            return

        try:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line.startswith("T,"):
                return

            parts = line.split(",")
            if len(parts) != 5:
                return

            temps = []
            for v in parts[1:]:
                try:
                    temps.append(float(v))
                except:
                    temps.append(None)

            if temps[0] is not None: self.p1.add_point(temps[0])
            if temps[1] is not None: self.p2.add_point(temps[1])
            if temps[2] is not None: self.p3.add_point(temps[2])
            if temps[3] is not None: self.p4.add_point(temps[3])

            if self.logging_enabled and self.log_writer and self.log_file:
                try:
                    ts = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    row = [ts, parts[1], parts[2], parts[3], parts[4]]
                    self.log_writer.writerow(row)
                    self.log_file.flush()
                except Exception as e:
                    self.stop_logging()
                    self.status.setText(f"Schrijffout, logging gestopt: {e}")

            self._update_shared_y_axis()

        except (serial.SerialException, OSError):
            self._handle_disconnect("Arduino losgekoppeld of COM-fout.")
        except Exception:
            pass

    def closeEvent(self, event):
        self.stop_logging()
        self._stop_reconnect_loop()
        self._close_serial()
        super().closeEvent(event)


def apply_style(app: QApplication):
    # Centrale stylesheet voor consistente kaart- en knopstijl in de hele GUI.
    app.setStyleSheet(f"""
    QWidget#root {{
        background: {APP_BG};
    }}
    QLabel {{
        color: {TEXT};
        font-size: 12px;
    }}
    QLabel#status {{
        color: {SUBTEXT};
        font-size: 10px;
        padding: 0px 2px;
    }}
    QFrame#connDot {{
        border-radius: 5px;
        border: 1px solid #9ca3af;
        background: #9ca3af;
    }}
    QFrame#connDot[state="connected"] {{
        border: 1px solid #16a34a;
        background: #16a34a;
    }}
    QFrame#connDot[state="searching"] {{
        border: 1px solid #f59e0b;
        background: #f59e0b;
    }}
    QFrame#connDot[state="retrying"] {{
        border: 1px solid #ef4444;
        background: #ef4444;
    }}
    QFrame#card {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QLabel#cardTitle {{
        color: {SUBTEXT};
        font-size: 12px;
    }}
    QLabel#cardValue {{
        color: {TEXT};
        font-size: 18px;
        font-weight: 600;
    }}
    QPushButton#mainButton {{
        background: #e5e7eb;
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 8px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#mainButton:hover {{
        background: #dbe1e8;
    }}
    QPushButton#mainButton:disabled {{
        color: #9ca3af;
        background: #f3f4f6;
    }}
    QPushButton#logButton {{
        color: #ffffff;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 8px 14px;
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton#logButton[mode="start"] {{
        background: #16a34a;
    }}
    QPushButton#logButton[mode="start"]:hover {{
        background: #15803d;
    }}
    QPushButton#logButton[mode="stop"] {{
        background: #dc2626;
    }}
    QPushButton#logButton[mode="stop"]:hover {{
        background: #b91c1c;
    }}
    QPushButton#logButton:disabled {{
        color: #d1d5db;
        background: #9ca3af;
    }}
    """)
    pg.setConfigOptions(antialias=True)


if __name__ == "__main__":
    set_windows_app_id()
    app = QApplication(sys.argv)
    logo_path = resource_path("Logo.ico")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))
    apply_style(app)
    w = MainWindow()
    if os.path.exists(logo_path):
        w.setWindowIcon(QIcon(logo_path))
    w.show()
    sys.exit(app.exec())