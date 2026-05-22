import sys
import os
import json
import socket
import threading
import time
import datetime
from typing import Optional

import numpy as np

try:
	import adi
except ImportError:
	adi = None

try:
	from PySide6 import QtWidgets, QtCore
	import pyqtgraph as pg
except ImportError:
	QtWidgets = None
	QtCore = None
	pg = None

# Early exit if GUI deps are missing to avoid AttributeError on class definitions
if QtWidgets is None or QtCore is None or pg is None:
	print("ERROR: PySide6 and pyqtgraph are required. Install with: pip install PySide6 pyqtgraph", file=sys.stderr)
	sys.exit(1)


class PlutoStreamer(QtCore.QObject):
	started = QtCore.Signal()
	stopped = QtCore.Signal()
	error = QtCore.Signal(str)
	stats = QtCore.Signal(float)  # samples/sec

	def __init__(self):
		super().__init__()
		self._tx = None
		self._stop = threading.Event()
		self._thread: Optional[threading.Thread] = None
		self._last_chunk: Optional[np.ndarray] = None

	def configure(self, uri: str, fs: int, fc: int, attn_db: float, bw: Optional[int] = None):
		if adi is None:
			raise RuntimeError("pyadi-iio not installed")
		tx = adi.Pluto(uri)
		tx.sample_rate = int(fs)
		tx.tx_lo = int(fc)
		try:
			tx.tx_hardwaregain = float(attn_db)
		except Exception:
			pass
		if bw is not None:
			try:
				tx.tx_rf_bandwidth = int(bw)
			except Exception:
				pass
		self._tx = tx

	def start_sigmf(self, data_path: str, meta_path: Optional[str], repeat: bool, chunk: int):
		def run():
			try:
				data = self._load_sigmf_data(data_path)
				N = data.size
				if N == 0:
					raise RuntimeError("Empty .sigmf-data")
				self.started.emit()
				idx = 0
				start = time.time()
				count = 0
				while not self._stop.is_set():
					end = min(idx + chunk, N)
					buf = data[idx:end]
					if buf.size < chunk and repeat:
						need = chunk - buf.size
						wrap = data[0:min(need, N)]
						buf = np.concatenate([buf, wrap])
					self._last_chunk = buf
					self._tx.tx(buf)
					count += buf.size
					idx += chunk
					if idx >= N:
						if repeat:
							idx = 0
						else:
							break
					if count >= self._tx.sample_rate:
						elapsed = time.time() - start
						if elapsed > 0:
							self.stats.emit(count / elapsed)
						start = time.time()
						count = 0
			except Exception as e:
				self.error.emit(str(e))
			finally:
				self._mute_and_close()
				self.stopped.emit()

		self._launch(run)

	def start_tcp(self, host: str, port: int, dtype: str, chunk: int):
		def run():
			try:
				s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
				s.connect((host, port))
				self.started.emit()
				bytes_per_sample = 2 if dtype == "int8" else 8
				buf_bytes = chunk * bytes_per_sample
				start = time.time()
				count = 0
				while not self._stop.is_set():
					b = self._recv_all(s, buf_bytes)
					if not b:
						break
					arr = np.frombuffer(b, dtype=np.int8 if dtype == "int8" else np.float32)
					I = arr[0::2]
					Q = arr[1::2]
					if dtype == "int8":
						c = (I.astype(np.float32) / 127.0 + 1j * (Q.astype(np.float32) / 127.0)).astype(np.complex64)
					else:
						c = (I.astype(np.float32) + 1j * Q.astype(np.float32)).astype(np.complex64)
					self._last_chunk = c
					self._tx.tx(c)
					count += c.size
					if count >= self._tx.sample_rate:
						elapsed = time.time() - start
						if elapsed > 0:
							self.stats.emit(count / elapsed)
						start = time.time()
						count = 0
			except Exception as e:
				self.error.emit(str(e))
			finally:
				self._mute_and_close()
				self.stopped.emit()

		self._launch(run)

	def start_generator(self, rinex_files: dict, start_time: str, duration_s: int, 
					   static_lat: float, static_lon: float, static_alt: float,
					   gpgga_path: str, is_static: bool, chunk: int):
		"""Generate GNSS signals in real time and send them to Pluto."""
		def run():
			try:
				# Import generator modules
				sys.path.append(os.path.join(os.path.dirname(__file__)))
				import main as gnss_main
				import orbit
				import datetime
				
				# Parse the start time
				dt_start = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
				dt_end = dt_start + datetime.timedelta(seconds=duration_s)
				
				# Load satellites
				sats = {}
				for system, rinex_path in rinex_files.items():
					if not rinex_path or not os.path.isfile(rinex_path):
						continue
					try:
						if system == "GPS":
							import GPS
							constellation = GPS.getConstelation()
						elif system == "GLONASS":
							import Glonass
							constellation = Glonass.getConstelation()
						elif system == "Galileo":
							import Galileo
							constellation = Galileo.getConstelation()
						elif system == "BeiDou":
							import BeiDou
							constellation = BeiDou.getConstelation()
						else:
							continue
						
						# Load satellite data
						loaded_sats, _ = constellation.loadSats([(constellation, rinex_path)])
						sats.update(loaded_sats)
					except Exception as e:
						print(f"Failed to load {system}: {e}")
						continue
					
				if not sats:
					raise RuntimeError("No satellite data was loaded successfully")
				
				# Position function
				if is_static:
					# Static position
					user_pos = orbit.wgslla2xyz(static_lat, static_lon, static_alt)
					pos_vel_func = gnss_main.simplePathInterpolation([(dt_start, user_pos)])
				else:
					# Track interpolation
					track_points = self._parse_gpgga(gpgga_path)
					if not track_points:
						raise RuntimeError("Track file is empty or could not be parsed")
					
					# Convert to ECEF coordinates
					pos_vel_points = []
					for ts, lat, lon, alt in track_points:
						pos = orbit.wgslla2xyz(lat, lon, alt)
						pos_vel_points.append((ts, pos))
					
					pos_vel_func = gnss_main.simplePathInterpolation(pos_vel_points)
				
				self.started.emit()
				
				# Real-time generation loop
				current_time = dt_start
				fs = self._tx.sample_rate
				dt_step = datetime.timedelta(seconds=chunk / fs)
				start = time.time()
				count = 0
				
				while not self._stop.is_set() and current_time < dt_end:
					# Get the current position
					user_pos, user_vel = pos_vel_func(current_time)
					
					# Generate frame data for the current time
					frame_data, results = gnss_main.generateFrame(
						user_pos, user_vel, sats, current_time, powerFactor=1.0
					)
					
					# Simplified IQ generation (the full modulation chain should be used here)
					# This uses a sine wave as a placeholder; it should include PRN codes,
					# navigation data, Doppler, and related effects in the real implementation
					t = np.arange(chunk) / fs
					iq = np.zeros(chunk, dtype=np.complex64)
					
					for sat_name, sat_data in results.items():
						# Simplified carrier generation
						freq = 1575.42e6 + sat_data['shift']  # L1 + Doppler
						phase = 2 * np.pi * freq * t
						# PRN code and navigation data modulation should be added here
						carrier = np.exp(1j * phase) * np.sqrt(sat_data['power'] / 100.0)
						iq += carrier
					
					# Normalize and transmit
					iq = iq / np.max(np.abs(iq)) if np.max(np.abs(iq)) > 0 else iq
					self._last_chunk = iq
					self._tx.tx(iq)
					
					count += chunk
					current_time += dt_step
					
					# Update throughput statistics
					if count >= fs:
						elapsed = time.time() - start
						if elapsed > 0:
							self.stats.emit(count / elapsed)
						start = time.time()
						count = 0
					
					# Control the transmit rate
					time.sleep(chunk / fs)
				
			except Exception as e:
				self.error.emit(str(e))
			finally:
				self._mute_and_close()
				self.stopped.emit()
		
		self._launch(run)

	def stop(self):
		self._stop.set()
		if self._thread and self._thread.is_alive():
			self._thread.join(timeout=2.0)

	def get_last_chunk(self) -> Optional[np.ndarray]:
		return self._last_chunk

	def _launch(self, target):
		self._stop.clear()
		self._thread = threading.Thread(target=target, daemon=True)
		self._thread.start()

	def _mute_and_close(self):
		try:
			if self._tx is not None:
				self._tx.tx(np.zeros(16384, dtype=np.complex64))
				time.sleep(0.05)
				self._tx.tx_destroy_buffer()
		except Exception:
			pass

	def _recv_all(self, s: socket.socket, n: int) -> bytes:
		buf = bytearray()
		while len(buf) < n and not self._stop.is_set():
			chunk = s.recv(n - len(buf))
			if not chunk:
				break
			buf.extend(chunk)
		return bytes(buf)

	def _load_sigmf_data(self, data_path: str) -> np.ndarray:
		raw = np.fromfile(data_path, dtype=np.int8)
		if raw.size % 2 != 0:
			raw = raw[:-1]
		I = raw[0::2]
		Q = raw[1::2]
		return (I.astype(np.float32) / 127.0 + 1j * (Q.astype(np.float32) / 127.0)).astype(np.complex64)


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Pluto GNSS Transmission Console")
		self.resize(1200, 800)
		self.setMinimumSize(1000, 700)

		self.streamer = PlutoStreamer()
		self._apply_style()
		self._build_ui()
		self._wire()

	def _apply_style(self):
		"""Apply the neumorphic visual style."""
		self.setStyleSheet("""
			QMainWindow {
				background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
					stop:0 #f0f2f5, stop:1 #e8ecf0);
			}
			
			QGroupBox {
				font-weight: bold;
				font-size: 14px;
				color: #2c3e50;
				border: 2px solid #d1d9e6;
				border-radius: 15px;
				margin-top: 10px;
				padding-top: 15px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
			}
			
			QGroupBox::title {
				subcontrol-origin: margin;
				left: 20px;
				padding: 0 10px 0 10px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
			}
			
			QLineEdit {
				border: 2px solid #d1d9e6;
				border-radius: 10px;
				padding: 8px 12px;
				font-size: 13px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
				selection-background-color: #3498db;
			}
			
			QLineEdit:focus {
				border: 2px solid #3498db;
				background: #ffffff;
			}
			
			QPushButton {
				border: none;
				border-radius: 12px;
				padding: 10px 20px;
				font-weight: bold;
				font-size: 13px;
				color: white;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #3498db, stop:1 #2980b9);
			}
			
			QPushButton:hover {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #5dade2, stop:1 #3498db);
			}
			
			QPushButton:pressed {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #2980b9, stop:1 #1f618d);
			}
			
			QPushButton:disabled {
				background: #bdc3c7;
				color: #7f8c8d;
			}
			
			QComboBox {
				border: 2px solid #d1d9e6;
				border-radius: 10px;
				padding: 8px 12px;
				font-size: 13px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
			}
			
			QComboBox:focus {
				border: 2px solid #3498db;
			}
			
			QComboBox::drop-down {
				border: none;
				width: 20px;
			}
			
			QComboBox::down-arrow {
				image: none;
				border-left: 5px solid transparent;
				border-right: 5px solid transparent;
				border-top: 5px solid #7f8c8d;
				margin-right: 5px;
			}
			
			QCheckBox {
				font-size: 13px;
				color: #2c3e50;
			}
			
			QCheckBox::indicator {
				width: 18px;
				height: 18px;
				border: 2px solid #d1d9e6;
				border-radius: 4px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
			}
			
			QCheckBox::indicator:checked {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #3498db, stop:1 #2980b9);
				border: 2px solid #3498db;
			}
			
			QRadioButton {
				font-size: 13px;
				color: #2c3e50;
			}
			
			QRadioButton::indicator {
				width: 18px;
				height: 18px;
				border: 2px solid #d1d9e6;
				border-radius: 9px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ffffff, stop:1 #f8f9fa);
			}
			
			QRadioButton::indicator:checked {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #3498db, stop:1 #2980b9);
				border: 2px solid #3498db;
			}
			
			QLabel {
				color: #2c3e50;
				font-size: 13px;
			}
			
			QFormLayout {
				spacing: 8px;
			}
			
			QFormLayout QLabel {
				font-weight: 500;
				color: #34495e;
			}
		""")

	def _build_ui(self):
		central = QtWidgets.QWidget()
		self.setCentralWidget(central)
		layout = QtWidgets.QVBoxLayout(central)
		layout.setSpacing(20)
		layout.setContentsMargins(20, 20, 20, 20)

		# Title area
		title_layout = QtWidgets.QHBoxLayout()
		title_label = QtWidgets.QLabel("🛰️ Pluto GNSS Transmission Console")
		title_label.setStyleSheet("""
			QLabel {
				font-size: 24px;
				font-weight: bold;
				color: #2c3e50;
				padding: 10px;
			}
		""")
		title_layout.addWidget(title_label)
		title_layout.addStretch()
		layout.addLayout(title_layout)

		# Main content area using a grid layout
		main_layout = QtWidgets.QHBoxLayout()
		
		# Left control panel
		left_panel = QtWidgets.QVBoxLayout()
		left_panel.setSpacing(15)

		# Device settings
		dev_group = QtWidgets.QGroupBox("📡 Pluto Device Settings")
		dev_form = QtWidgets.QFormLayout(dev_group)
		dev_form.setSpacing(12)
		self.uri_edit = QtWidgets.QLineEdit("ip:192.168.2.1")
		self.fs_edit = QtWidgets.QLineEdit("2600000")
		self.fc_edit = QtWidgets.QLineEdit("1575420000")
		self.gain_edit = QtWidgets.QLineEdit("-20")
		self.bw_edit = QtWidgets.QLineEdit("")
		dev_form.addRow("🌐 Device URI", self.uri_edit)
		dev_form.addRow("📊 Sample Rate (Hz)", self.fs_edit)
		dev_form.addRow("📡 Center Frequency (Hz)", self.fc_edit)
		dev_form.addRow("⚡ TX Attenuation (dB)", self.gain_edit)
		dev_form.addRow("📶 RF Bandwidth (Hz)", self.bw_edit)
		left_panel.addWidget(dev_group)

		# Source settings
		src_group = QtWidgets.QGroupBox("🎯 Signal Source Settings")
		src_v = QtWidgets.QVBoxLayout(src_group)
		src_v.setSpacing(15)
		
		# Mode selection
		mode_layout = QtWidgets.QHBoxLayout()
		mode_layout.addWidget(QtWidgets.QLabel("📋 Source Mode:"))
		self.mode_combo = QtWidgets.QComboBox()
		self.mode_combo.addItems(["📁 SIGMF File", "🌐 TCP Stream", "🛰️ Navigation Generator"])
		self.mode_combo.setMinimumWidth(200)
		mode_layout.addWidget(self.mode_combo)
		mode_layout.addStretch()
		src_v.addLayout(mode_layout)

		# SIGMF
		sigmf_form = QtWidgets.QFormLayout()
		sigmf_form.setSpacing(10)
		self.sigmf_path = QtWidgets.QLineEdit("data/OutputIQ.sigmf-data")
		self.sigmf_browse = QtWidgets.QPushButton("📁 Browse")
		self.sigmf_browse.setMaximumWidth(100)
		row = QtWidgets.QHBoxLayout()
		row.addWidget(self.sigmf_path)
		row.addWidget(self.sigmf_browse)
		sigmf_form.addRow("📄 .sigmf-data Path", row)
		self.sigmf_repeat = QtWidgets.QCheckBox("🔄 Loop Playback")
		self.sigmf_repeat.setChecked(True)
		sigmf_form.addRow(self.sigmf_repeat)
		src_v.addLayout(sigmf_form)

		# TCP
		tcp_form = QtWidgets.QFormLayout()
		self.tcp_host = QtWidgets.QLineEdit("127.0.0.1")
		self.tcp_port = QtWidgets.QLineEdit("57001")
		self.tcp_dtype = QtWidgets.QComboBox()
		self.tcp_dtype.addItems(["int8", "float32"])
		tcp_form.addRow("🌐 Host Address", self.tcp_host)
		tcp_form.addRow("🔌 Port", self.tcp_port)
		tcp_form.addRow("📊 Data Type", self.tcp_dtype)
		src_v.addLayout(tcp_form)

		left_panel.addWidget(src_group)

		# Generator settings (RINEX selection, time, and position)
		gen_group = QtWidgets.QGroupBox("🛰️ Navigation Generator Settings")
		gen_form = QtWidgets.QFormLayout(gen_group)
		self.gen_gps = QtWidgets.QLineEdit("")
		self.gen_gln = QtWidgets.QLineEdit("")
		self.gen_gal = QtWidgets.QLineEdit("")
		self.gen_bds = QtWidgets.QLineEdit("")
		self.gen_nav_browse_btns = []
		for label, line in [("🛰️ GPS RINEX", self.gen_gps), ("🌍 GLONASS RINEX", self.gen_gln), ("🇪🇺 Galileo RINEX", self.gen_gal), ("🇨🇳 BeiDou RINEX", self.gen_bds)]:
			row = QtWidgets.QHBoxLayout()
			btn = QtWidgets.QPushButton("📁 Browse")
			btn.setMaximumWidth(80)
			self.gen_nav_browse_btns.append((btn, line))
			row.addWidget(line)
			row.addWidget(btn)
			gen_form.addRow(label, row)
		# One-click ephemeris import
		self.auto_nav_btn = QtWidgets.QPushButton("🔍 Auto-import Ephemeris (scan data/)")
		self.auto_nav_btn.setStyleSheet("""
			QPushButton {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #27ae60, stop:1 #229954);
			}
			QPushButton:hover {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #2ecc71, stop:1 #27ae60);
			}
		""")
		gen_form.addRow(self.auto_nav_btn)
		self.gen_start_time = QtWidgets.QLineEdit("")
		self.gen_duration_s = QtWidgets.QLineEdit("600")
		self.gen_lat = QtWidgets.QLineEdit("")
		self.gen_lon = QtWidgets.QLineEdit("")
		self.gen_alt = QtWidgets.QLineEdit("")
		# Mode: static or track-based
		self.gen_mode_static = QtWidgets.QRadioButton("📍 Static Position")
		self.gen_mode_track = QtWidgets.QRadioButton("🛣️ Track ($GPGGA)")
		self.gen_mode_static.setChecked(True)
		mode_row = QtWidgets.QHBoxLayout()
		mode_row.addWidget(self.gen_mode_static)
		mode_row.addWidget(self.gen_mode_track)
		# Track input (GPGGA)
		self.gen_gpgga = QtWidgets.QLineEdit("")
		gpgga_row = QtWidgets.QHBoxLayout()
		self.gen_gpgga_btn = QtWidgets.QPushButton("📁 Browse")
		self.gen_gpgga_btn.setMaximumWidth(80)
		gpgga_row.addWidget(self.gen_gpgga)
		gpgga_row.addWidget(self.gen_gpgga_btn)
		gen_form.addRow("⏰ Start Time (YYYY-MM-DD HH:MM:SS)", self.gen_start_time)
		gen_form.addRow("⏱️ Duration (s)", self.gen_duration_s)
		gen_form.addRow("🌍 Latitude (deg)", self.gen_lat)
		gen_form.addRow("🌐 Longitude (deg)", self.gen_lon)
		gen_form.addRow("⛰️ Altitude (m)", self.gen_alt)
		gen_form.addRow("🎯 Position Mode", mode_row)
		gen_form.addRow("📄 Track File ($GPGGA)", gpgga_row)
		left_panel.addWidget(gen_group)

		# Control button area
		ctrl_group = QtWidgets.QGroupBox("🎮 Transmission Control")
		ctrl_layout = QtWidgets.QVBoxLayout(ctrl_group)
		ctrl_layout.setSpacing(15)
		
		# Chunk size settings
		chunk_layout = QtWidgets.QHBoxLayout()
		chunk_layout.addWidget(QtWidgets.QLabel("📦 Chunk Size:"))
		self.chunk_edit = QtWidgets.QLineEdit("16384")
		self.chunk_edit.setMaximumWidth(120)
		chunk_layout.addWidget(self.chunk_edit)
		chunk_layout.addStretch()
		ctrl_layout.addLayout(chunk_layout)
		
		# Button row
		btn_row = QtWidgets.QHBoxLayout()
		btn_row.setSpacing(10)
		self.probe_btn = QtWidgets.QPushButton("🔍 Probe")
		self.start_btn = QtWidgets.QPushButton("🚀 Start Transmission")
		self.stop_btn = QtWidgets.QPushButton("⏹️ Stop")
		self.stop_btn.setEnabled(False)
		
		# Button styling
		self.start_btn.setStyleSheet("""
			QPushButton {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #e74c3c, stop:1 #c0392b);
				font-size: 14px;
				padding: 12px 24px;
			}
			QPushButton:hover {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ec7063, stop:1 #e74c3c);
			}
		""")
		
		self.stop_btn.setStyleSheet("""
			QPushButton {
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #95a5a6, stop:1 #7f8c8d);
				font-size: 14px;
				padding: 12px 24px;
			}
		""")
		
		btn_row.addWidget(self.probe_btn)
		btn_row.addWidget(self.start_btn)
		btn_row.addWidget(self.stop_btn)
		ctrl_layout.addLayout(btn_row)
		
		left_panel.addWidget(ctrl_group)
		
		# Add the left panel to the main layout
		left_widget = QtWidgets.QWidget()
		left_widget.setLayout(left_panel)
		left_widget.setMaximumWidth(450)
		main_layout.addWidget(left_widget)

		# Right-side spectrum area
		right_panel = QtWidgets.QVBoxLayout()
		right_panel.setSpacing(15)
		
		# Spectrum/Waterfall
		plot_group = QtWidgets.QGroupBox("📊 Spectrum Preview (Latest Buffer)")
		plot_v = QtWidgets.QVBoxLayout(plot_group)
		plot_v.setSpacing(10)
		self.plot = pg.PlotWidget()
		self.plot.setBackground('w')
		self.curve = self.plot.plot(np.zeros(1024), pen=pg.mkPen(color='#3498db', width=2))
		self.plot.setLabel("left", "dBFS", color='#2c3e50', size='12pt')
		self.plot.setLabel("bottom", "Frequency Bin", color='#2c3e50', size='12pt')
		self.plot.showGrid(x=True, y=True, alpha=0.3)
		plot_v.addWidget(self.plot)
		right_panel.addWidget(plot_group)
		
		# Status area
		status_group = QtWidgets.QGroupBox("📈 System Status")
		status_layout = QtWidgets.QVBoxLayout(status_group)
		self.status = QtWidgets.QLabel("💤 Idle")
		self.status.setStyleSheet("""
			QLabel {
				font-size: 14px;
				font-weight: bold;
				color: #2c3e50;
				padding: 10px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #ecf0f1, stop:1 #bdc3c7);
				border-radius: 8px;
			}
		""")
		status_layout.addWidget(self.status)
		right_panel.addWidget(status_group)
		
		# Add the right panel to the main layout
		right_widget = QtWidgets.QWidget()
		right_widget.setLayout(right_panel)
		main_layout.addWidget(right_widget)
		
		# Add the main layout to the root layout
		layout.addLayout(main_layout)

	def _wire(self):
		self.sigmf_browse.clicked.connect(self._choose_sigmf)
		self.start_btn.clicked.connect(self._start)
		self.stop_btn.clicked.connect(self._stop)
		self.probe_btn.clicked.connect(self._probe)
		for btn, line in self.gen_nav_browse_btns:
			btn.clicked.connect(lambda _, le=line: self._choose_rinex(le))
		self.gen_gpgga_btn.clicked.connect(self._choose_gpgga)
		self.auto_nav_btn.clicked.connect(self._auto_import_ephemeris)
		self.streamer.started.connect(lambda: self._set_running(True))
		self.streamer.stopped.connect(lambda: self._set_running(False))
		self.streamer.error.connect(self._on_error)
		self.streamer.stats.connect(self._on_stats)

		self.timer = QtCore.QTimer(self)
		self.timer.timeout.connect(self._refresh_plot)
		self.timer.start(200)

	def closeEvent(self, e):
		try:
			self._stop()
		except Exception:
			pass
		e.accept()

	def _choose_sigmf(self):
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select .sigmf-data", os.getcwd(), "SigMF data (*.sigmf-data);;All files (*.*)")
		if path:
			self.sigmf_path.setText(path)

	def _choose_rinex(self, line_edit: QtWidgets.QLineEdit):
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select RINEX Navigation File", os.getcwd(), "RINEX (*.rnx *.24* *.n *.g *.l *.q);;All files (*.*)")
		if path:
			line_edit.setText(path)

	def _choose_gpgga(self):
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select $GPGGA Track File", os.getcwd(), "NMEA (*.nmea *.log *.txt);;All files (*.*)")
		if path:
			self.gen_gpgga.setText(path)

	def _start(self):
		try:
			uri = self.uri_edit.text().strip()
			fs = int(self.fs_edit.text())
			fc = int(self.fc_edit.text())
			attn = float(self.gain_edit.text())
			bw_txt = self.bw_edit.text().strip()
			bw = int(bw_txt) if bw_txt else None
			self.streamer.configure(uri, fs, fc, attn, bw)

			chunk = int(self.chunk_edit.text())
			mode = self.mode_combo.currentText()
			if mode == "📁 SIGMF File":
				data_path = self.sigmf_path.text().strip()
				if not os.path.isfile(data_path):
					raise RuntimeError(".sigmf-data not found")
				self.streamer.start_sigmf(data_path, None, self.sigmf_repeat.isChecked(), chunk)
			elif mode == "🌐 TCP Stream":
				host = self.tcp_host.text().strip()
				port = int(self.tcp_port.text())
				dtype = self.tcp_dtype.currentText()
				self.streamer.start_tcp(host, port, dtype, chunk)
			else:
				# Generate navigation data in real time
				rinex_files = {
					"GPS": self.gen_gps.text().strip(),
					"GLONASS": self.gen_gln.text().strip(),
					"Galileo": self.gen_gal.text().strip(),
					"BeiDou": self.gen_bds.text().strip()
				}
				
				# Filter out empty file entries
				rinex_files = {k: v for k, v in rinex_files.items() if v and os.path.isfile(v)}
				if not rinex_files:
					raise RuntimeError("Please select at least one valid RINEX file")
				
				start_time = self.gen_start_time.text().strip()
				if not start_time:
					start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
				
				duration_s = int(self.gen_duration_s.text().strip())
				is_static = self.gen_mode_static.isChecked()
				
				if is_static:
					# Static mode
					lat = float(self.gen_lat.text().strip())
					lon = float(self.gen_lon.text().strip())
					alt = float(self.gen_alt.text().strip())
					self.streamer.start_generator(
						rinex_files, start_time, duration_s,
						lat, lon, alt, "", True, chunk
					)
				else:
					# Track mode
					gpgga_path = self.gen_gpgga.text().strip()
					if not gpgga_path or not os.path.isfile(gpgga_path):
						raise RuntimeError("Please select a valid GPGGA track file")
					
					# Validate the track file
					track_points = self._parse_gpgga(gpgga_path)
					if not track_points:
						raise RuntimeError("Track file could not be parsed or is empty")
					
					self.streamer.start_generator(
						rinex_files, start_time, duration_s,
						0, 0, 0, gpgga_path, False, chunk
					)
		except Exception as e:
			self._on_error(str(e))

	def _stop(self):
		self.streamer.stop()

	def _set_running(self, running: bool):
		self.start_btn.setEnabled(not running)
		self.stop_btn.setEnabled(running)
		if running:
			self.status.setText("🚀 Transmitting")
			self.status.setStyleSheet("""
				QLabel {
					font-size: 14px;
					font-weight: bold;
					color: white;
					padding: 10px;
					background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
						stop:0 #e74c3c, stop:1 #c0392b);
					border-radius: 8px;
				}
			""")
		else:
			self.status.setText("💤 Idle")
			self.status.setStyleSheet("""
				QLabel {
					font-size: 14px;
					font-weight: bold;
					color: #2c3e50;
					padding: 10px;
					background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
						stop:0 #ecf0f1, stop:1 #bdc3c7);
					border-radius: 8px;
				}
			""")

	def _on_error(self, msg: str):
		QtWidgets.QMessageBox.critical(self, "Error", msg)
		self.status.setText(f"Error: {msg}")

	def _on_stats(self, rate: float):
		self.status.setText(f"🚀 Transmitting ~{rate/1e6:.2f} MS/s")
		self.status.setStyleSheet("""
			QLabel {
				font-size: 14px;
				font-weight: bold;
				color: white;
				padding: 10px;
				background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
					stop:0 #27ae60, stop:1 #229954);
				border-radius: 8px;
			}
		""")

	def _refresh_plot(self):
		buf = self.streamer.get_last_chunk()
		if buf is None or buf.size == 0:
			return
		N = min(buf.size, 16384)
		win = np.hanning(N).astype(np.float32)
		fft = np.fft.fftshift(np.fft.fft(buf[:N] * win))
		psd = 20 * np.log10(1e-12 + np.abs(fft) / N)
		self.curve.setData(psd)

	def _auto_import_ephemeris(self):
		"""Scan the data/ directory and auto-fill the most recent RINEX file for each constellation."""
		base = os.path.abspath(os.path.join(os.getcwd(), 'data'))
		candidates = {
			'GPS': ['.24n', '.n'],
			'Glonass': ['.24g', '.g', '.rnx'],
			'Galileo': ['.24l', '.l', '.rnx'],
			'BeiDou': ['.24f', '.q', '.rnx'],
		}
		found = {}
		for system, exts in candidates.items():
			dirpath = os.path.join(base, system)
			if not os.path.isdir(dirpath):
				continue
			best = None
			best_mtime = -1
			for fname in os.listdir(dirpath):
				lf = fname.lower()
				if any(lf.endswith(ext) for ext in exts):
					full = os.path.join(dirpath, fname)
					mt = os.path.getmtime(full)
					if mt > best_mtime:
						best_mtime = mt
						best = full
			if best:
				found[system] = best
		if 'GPS' in found:
			self.gen_gps.setText(found['GPS'])
		if 'Glonass' in found:
			self.gen_gln.setText(found['Glonass'])
		if 'Galileo' in found:
			self.gen_gal.setText(found['Galileo'])
		if 'BeiDou' in found:
			self.gen_bds.setText(found['BeiDou'])
		if not found:
			QtWidgets.QMessageBox.warning(self, "Notice", "No usable RINEX files found under data/.")
		else:
			msg = [f"{k}: {v}" for k, v in found.items()]
			QtWidgets.QMessageBox.information(self, "Ephemeris Imported", "\n".join(msg))

	def _parse_gpgga(self, path: str):
		"""
		Simple $GPGGA parser: returns [(datetime, lat, lon, alt), ...]
		Supported format: $GPGGA,hhmmss.sss,lat,NS,lon,EW,fix,nsat,hdop,alt,M,geoid,M,age,ref*cs
		"""
		from datetime import datetime
		def nmea_latlon_to_deg(val: str, hemi: str, is_lat: bool) -> float:
			if not val:
				return 0.0
			# lat: ddmm.mmmm, lon: dddmm.mmmm
			dot = val.find('.')
			if dot < 0:
				dot = len(val)
			dm_len = 2 if is_lat else 3
			deg = float(val[:dot-dm_len]) if (dot-dm_len)>0 else 0.0
			minu = float(val[dot-dm_len:]) if (dot-dm_len)>=0 else 0.0
			res = deg + minu/60.0
			if (hemi in ('S','W')):
				res = -res
			return res
		pts = []
		with open(path, 'r', encoding='utf-8', errors='ignore') as f:
			for line in f:
				if '$GPGGA' not in line:
					continue
				parts = line.strip().split(',')
				if len(parts) < 10:
					continue
				time_utc = parts[1]
				lat = parts[2]; ns = parts[3]
				lon = parts[4]; ew = parts[5]
				alt = parts[9]
				# hhmmss(.sss)
				try:
					h = int(time_utc[0:2] or '0'); m = int(time_utc[2:4] or '0'); s = float(time_utc[4:] or '0')
					ts = datetime.utcnow().replace(hour=h, minute=m, second=int(s), microsecond=int((s%1)*1e6))
				except Exception:
					ts = datetime.utcnow()
				try:
					plat = nmea_latlon_to_deg(lat, ns, True)
					plon = nmea_latlon_to_deg(lon, ew, False)
					palt = float(alt) if alt else 0.0
				except Exception:
					continue
				pts.append((ts, plat, plon, palt))
		return pts

	def _probe(self):
		# Check whether the DLLs are in the current directory or on PATH (Windows)
		missing = []
		for dll in ["libiio.dll", "libad9361.dll"]:
			found = False
			# current dir
			if os.path.isfile(os.path.join(os.getcwd(), dll)):
				found = True
			# PATH dirs
			if not found:
				for p in os.getenv("PATH", "").split(os.pathsep):
					if os.path.isfile(os.path.join(p, dll)):
						found = True
						break
			if not found:
				missing.append(dll)

		uri = self.uri_edit.text().strip()
		fs = self.fs_edit.text().strip()
		fc = self.fc_edit.text().strip()
		attn = self.gain_edit.text().strip()

		msg = []
		msg.append(f"URI: {uri}")
		msg.append(f"Configuration: sample rate {fs} Hz, center frequency {fc} Hz, attenuation {attn} dB")
		if missing:
			msg.append("Missing DLLs: " + ", ".join(missing))
		else:
			msg.append("DLLs found (current directory or PATH)")

		# Try to open Pluto
		try:
			if adi is None:
				raise RuntimeError("pyadi-iio is not installed")
			d = adi.Pluto(uri)
			msg.append(f"Connected: fs={d.sample_rate}, center frequency={d.tx_lo}, bandwidth={getattr(d, 'tx_rf_bandwidth', 'n/a')}")
		except Exception as e:
			msg.append(f"Connection failed: {e}")
		QtWidgets.QMessageBox.information(self, "Probe Results", "\n".join(msg))


def main():
	# Deps already checked above
	app = QtWidgets.QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
