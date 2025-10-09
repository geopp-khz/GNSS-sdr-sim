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
		"""实时生成 GNSS 信号并发送到 Pluto"""
		def run():
			try:
				# 导入生成器模块
				sys.path.append(os.path.join(os.path.dirname(__file__)))
				import main as gnss_main
				import orbit
				import datetime
				
				# 解析起始时间
				dt_start = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
				dt_end = dt_start + datetime.timedelta(seconds=duration_s)
				
				# 加载卫星
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
						
						# 加载卫星数据
						loaded_sats, _ = constellation.loadSats([(constellation, rinex_path)])
						sats.update(loaded_sats)
					except Exception as e:
						print(f"加载 {system} 失败: {e}")
						continue
				
				if not sats:
					raise RuntimeError("未成功加载任何卫星数据")
				
				# 位置函数
				if is_static:
					# 静态位置
					user_pos = orbit.wgslla2xyz(static_lat, static_lon, static_alt)
					pos_vel_func = gnss_main.simplePathInterpolation([(dt_start, user_pos)])
				else:
					# 轨迹插值
					track_points = self._parse_gpgga(gpgga_path)
					if not track_points:
						raise RuntimeError("轨迹文件为空或解析失败")
					
					# 转换为 ECEF 坐标
					pos_vel_points = []
					for ts, lat, lon, alt in track_points:
						pos = orbit.wgslla2xyz(lat, lon, alt)
						pos_vel_points.append((ts, pos))
					
					pos_vel_func = gnss_main.simplePathInterpolation(pos_vel_points)
				
				self.started.emit()
				
				# 实时生成循环
				current_time = dt_start
				fs = self._tx.sample_rate
				dt_step = datetime.timedelta(seconds=chunk / fs)
				start = time.time()
				count = 0
				
				while not self._stop.is_set() and current_time < dt_end:
					# 获取当前位置
					user_pos, user_vel = pos_vel_func(current_time)
					
					# 生成当前时刻的帧数据
					frame_data, results = gnss_main.generateFrame(
						user_pos, user_vel, sats, current_time, powerFactor=1.0
					)
					
					# 简化的 IQ 生成（实际应调用完整的调制链路）
					# 这里用正弦波占位，实际应包含 PRN 码、导航数据、多普勒等
					t = np.arange(chunk) / fs
					iq = np.zeros(chunk, dtype=np.complex64)
					
					for sat_name, sat_data in results.items():
						# 简化的载波生成
						freq = 1575.42e6 + sat_data['shift']  # L1 + 多普勒
						phase = 2 * np.pi * freq * t
						# 这里应加入 PRN 码和导航数据调制
						carrier = np.exp(1j * phase) * np.sqrt(sat_data['power'] / 100.0)
						iq += carrier
					
					# 归一化并发送
					iq = iq / np.max(np.abs(iq)) if np.max(np.abs(iq)) > 0 else iq
					self._last_chunk = iq
					self._tx.tx(iq)
					
					count += chunk
					current_time += dt_step
					
					# 统计速率
					if count >= fs:
						elapsed = time.time() - start
						if elapsed > 0:
							self.stats.emit(count / elapsed)
						start = time.time()
						count = 0
					
					# 控制发送速率
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
		self.setWindowTitle("Pluto GNSS 发射控制台")
		self.resize(1200, 800)
		self.setMinimumSize(1000, 700)

		self.streamer = PlutoStreamer()
		self._apply_style()
		self._build_ui()
		self._wire()

	def _apply_style(self):
		"""应用新拟态风格样式"""
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

		# 标题区域
		title_layout = QtWidgets.QHBoxLayout()
		title_label = QtWidgets.QLabel("🛰️ Pluto GNSS 发射控制台")
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

		# 主要内容区域 - 使用网格布局
		main_layout = QtWidgets.QHBoxLayout()
		
		# 左侧控制面板
		left_panel = QtWidgets.QVBoxLayout()
		left_panel.setSpacing(15)

		# Device settings
		dev_group = QtWidgets.QGroupBox("📡 Pluto 设备配置")
		dev_form = QtWidgets.QFormLayout(dev_group)
		dev_form.setSpacing(12)
		self.uri_edit = QtWidgets.QLineEdit("ip:192.168.2.1")
		self.fs_edit = QtWidgets.QLineEdit("2600000")
		self.fc_edit = QtWidgets.QLineEdit("1575420000")
		self.gain_edit = QtWidgets.QLineEdit("-20")
		self.bw_edit = QtWidgets.QLineEdit("")
		dev_form.addRow("🌐 设备 URI", self.uri_edit)
		dev_form.addRow("📊 采样率 (Hz)", self.fs_edit)
		dev_form.addRow("📡 载频 (Hz)", self.fc_edit)
		dev_form.addRow("⚡ 发射衰减 (dB)", self.gain_edit)
		dev_form.addRow("📶 射频带宽 (Hz)", self.bw_edit)
		left_panel.addWidget(dev_group)

		# Source settings
		src_group = QtWidgets.QGroupBox("🎯 信号源配置")
		src_v = QtWidgets.QVBoxLayout(src_group)
		src_v.setSpacing(15)
		
		# 模式选择
		mode_layout = QtWidgets.QHBoxLayout()
		mode_layout.addWidget(QtWidgets.QLabel("📋 信号源模式:"))
		self.mode_combo = QtWidgets.QComboBox()
		self.mode_combo.addItems(["📁 SIGMF 文件", "🌐 TCP 流", "🛰️ 导航生成器"])
		self.mode_combo.setMinimumWidth(200)
		mode_layout.addWidget(self.mode_combo)
		mode_layout.addStretch()
		src_v.addLayout(mode_layout)

		# SIGMF
		sigmf_form = QtWidgets.QFormLayout()
		sigmf_form.setSpacing(10)
		self.sigmf_path = QtWidgets.QLineEdit("data/OutputIQ.sigmf-data")
		self.sigmf_browse = QtWidgets.QPushButton("📁 浏览")
		self.sigmf_browse.setMaximumWidth(100)
		row = QtWidgets.QHBoxLayout()
		row.addWidget(self.sigmf_path)
		row.addWidget(self.sigmf_browse)
		sigmf_form.addRow("📄 .sigmf-data 路径", row)
		self.sigmf_repeat = QtWidgets.QCheckBox("🔄 循环播放")
		self.sigmf_repeat.setChecked(True)
		sigmf_form.addRow(self.sigmf_repeat)
		src_v.addLayout(sigmf_form)

		# TCP
		tcp_form = QtWidgets.QFormLayout()
		self.tcp_host = QtWidgets.QLineEdit("127.0.0.1")
		self.tcp_port = QtWidgets.QLineEdit("57001")
		self.tcp_dtype = QtWidgets.QComboBox()
		self.tcp_dtype.addItems(["int8", "float32"])
		tcp_form.addRow("🌐 主机地址", self.tcp_host)
		tcp_form.addRow("🔌 端口号", self.tcp_port)
		tcp_form.addRow("📊 数据类型", self.tcp_dtype)
		src_v.addLayout(tcp_form)

		left_panel.addWidget(src_group)

		# 生成器（RINEX 选择、时间/位置）
		gen_group = QtWidgets.QGroupBox("🛰️ 导航生成器设置")
		gen_form = QtWidgets.QFormLayout(gen_group)
		self.gen_gps = QtWidgets.QLineEdit("")
		self.gen_gln = QtWidgets.QLineEdit("")
		self.gen_gal = QtWidgets.QLineEdit("")
		self.gen_bds = QtWidgets.QLineEdit("")
		self.gen_nav_browse_btns = []
		for label, line in [("🛰️ GPS RINEX", self.gen_gps), ("🌍 GLONASS RINEX", self.gen_gln), ("🇪🇺 Galileo RINEX", self.gen_gal), ("🇨🇳 BeiDou RINEX", self.gen_bds)]:
			row = QtWidgets.QHBoxLayout()
			btn = QtWidgets.QPushButton("📁 浏览")
			btn.setMaximumWidth(80)
			self.gen_nav_browse_btns.append((btn, line))
			row.addWidget(line)
			row.addWidget(btn)
			gen_form.addRow(label, row)
		# 一键导入星历
		self.auto_nav_btn = QtWidgets.QPushButton("🔍 一键导入星历(扫描 data/)")
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
		# 模式：静态/轨迹
		self.gen_mode_static = QtWidgets.QRadioButton("📍 静态位置")
		self.gen_mode_track = QtWidgets.QRadioButton("🛣️ 轨迹($GPGGA)")
		self.gen_mode_static.setChecked(True)
		mode_row = QtWidgets.QHBoxLayout()
		mode_row.addWidget(self.gen_mode_static)
		mode_row.addWidget(self.gen_mode_track)
		# 轨迹(GPGGA)
		self.gen_gpgga = QtWidgets.QLineEdit("")
		gpgga_row = QtWidgets.QHBoxLayout()
		self.gen_gpgga_btn = QtWidgets.QPushButton("📁 浏览")
		self.gen_gpgga_btn.setMaximumWidth(80)
		gpgga_row.addWidget(self.gen_gpgga)
		gpgga_row.addWidget(self.gen_gpgga_btn)
		gen_form.addRow("⏰ 起始时间(YYYY-MM-DD HH:MM:SS)", self.gen_start_time)
		gen_form.addRow("⏱️ 持续时长(秒)", self.gen_duration_s)
		gen_form.addRow("🌍 纬度(度)", self.gen_lat)
		gen_form.addRow("🌐 经度(度)", self.gen_lon)
		gen_form.addRow("⛰️ 高度(米)", self.gen_alt)
		gen_form.addRow("🎯 位置模式", mode_row)
		gen_form.addRow("📄 轨迹文件($GPGGA)", gpgga_row)
		left_panel.addWidget(gen_group)

		# 控制按钮区域
		ctrl_group = QtWidgets.QGroupBox("🎮 发射控制")
		ctrl_layout = QtWidgets.QVBoxLayout(ctrl_group)
		ctrl_layout.setSpacing(15)
		
		# 分块设置
		chunk_layout = QtWidgets.QHBoxLayout()
		chunk_layout.addWidget(QtWidgets.QLabel("📦 分块大小:"))
		self.chunk_edit = QtWidgets.QLineEdit("16384")
		self.chunk_edit.setMaximumWidth(120)
		chunk_layout.addWidget(self.chunk_edit)
		chunk_layout.addStretch()
		ctrl_layout.addLayout(chunk_layout)
		
		# 按钮行
		btn_row = QtWidgets.QHBoxLayout()
		btn_row.setSpacing(10)
		self.probe_btn = QtWidgets.QPushButton("🔍 探测")
		self.start_btn = QtWidgets.QPushButton("🚀 开始发射")
		self.stop_btn = QtWidgets.QPushButton("⏹️ 停止")
		self.stop_btn.setEnabled(False)
		
		# 按钮样式
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
		
		# 将左侧面板添加到主布局
		left_widget = QtWidgets.QWidget()
		left_widget.setLayout(left_panel)
		left_widget.setMaximumWidth(450)
		main_layout.addWidget(left_widget)

		# 右侧频谱区域
		right_panel = QtWidgets.QVBoxLayout()
		right_panel.setSpacing(15)
		
		# Spectrum/Waterfall
		plot_group = QtWidgets.QGroupBox("📊 频谱预览（最近缓冲）")
		plot_v = QtWidgets.QVBoxLayout(plot_group)
		plot_v.setSpacing(10)
		self.plot = pg.PlotWidget()
		self.plot.setBackground('w')
		self.curve = self.plot.plot(np.zeros(1024), pen=pg.mkPen(color='#3498db', width=2))
		self.plot.setLabel("left", "dBFS", color='#2c3e50', size='12pt')
		self.plot.setLabel("bottom", "频率 Bin", color='#2c3e50', size='12pt')
		self.plot.showGrid(x=True, y=True, alpha=0.3)
		plot_v.addWidget(self.plot)
		right_panel.addWidget(plot_group)
		
		# 状态栏
		status_group = QtWidgets.QGroupBox("📈 系统状态")
		status_layout = QtWidgets.QVBoxLayout(status_group)
		self.status = QtWidgets.QLabel("💤 空闲")
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
		
		# 将右侧面板添加到主布局
		right_widget = QtWidgets.QWidget()
		right_widget.setLayout(right_panel)
		main_layout.addWidget(right_widget)
		
		# 将主布局添加到总布局
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
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 RINEX 导航文件", os.getcwd(), "RINEX (*.rnx *.24* *.n *.g *.l *.q);;所有文件 (*.*)")
		if path:
			line_edit.setText(path)

	def _choose_gpgga(self):
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 $GPGGA 轨迹文件", os.getcwd(), "NMEA (*.nmea *.log *.txt);;所有文件 (*.*)")
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
			if mode == "SIGMF 文件":
				data_path = self.sigmf_path.text().strip()
				if not os.path.isfile(data_path):
					raise RuntimeError(".sigmf-data not found")
				self.streamer.start_sigmf(data_path, None, self.sigmf_repeat.isChecked(), chunk)
			elif mode == "TCP 流":
				host = self.tcp_host.text().strip()
				port = int(self.tcp_port.text())
				dtype = self.tcp_dtype.currentText()
				self.streamer.start_tcp(host, port, dtype, chunk)
			else:
				# 导航生成器实时生成
				rinex_files = {
					"GPS": self.gen_gps.text().strip(),
					"GLONASS": self.gen_gln.text().strip(),
					"Galileo": self.gen_gal.text().strip(),
					"BeiDou": self.gen_bds.text().strip()
				}
				
				# 过滤空文件
				rinex_files = {k: v for k, v in rinex_files.items() if v and os.path.isfile(v)}
				if not rinex_files:
					raise RuntimeError("请至少选择一个有效的 RINEX 文件")
				
				start_time = self.gen_start_time.text().strip()
				if not start_time:
					start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
				
				duration_s = int(self.gen_duration_s.text().strip())
				is_static = self.gen_mode_static.isChecked()
				
				if is_static:
					# 静态模式
					lat = float(self.gen_lat.text().strip())
					lon = float(self.gen_lon.text().strip())
					alt = float(self.gen_alt.text().strip())
					self.streamer.start_generator(
						rinex_files, start_time, duration_s,
						lat, lon, alt, "", True, chunk
					)
				else:
					# 轨迹模式
					gpgga_path = self.gen_gpgga.text().strip()
					if not gpgga_path or not os.path.isfile(gpgga_path):
						raise RuntimeError("请选择有效的 GPGGA 轨迹文件")
					
					# 验证轨迹文件
					track_points = self._parse_gpgga(gpgga_path)
					if not track_points:
						raise RuntimeError("轨迹文件解析失败或为空")
					
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
			self.status.setText("🚀 发射中")
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
			self.status.setText("💤 空闲")
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
		QtWidgets.QMessageBox.critical(self, "错误", msg)
		self.status.setText(f"错误: {msg}")

	def _on_stats(self, rate: float):
		self.status.setText(f"🚀 发射中 ~{rate/1e6:.2f} MS/s")
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
		"""扫描 data/ 目录，为各星座自动填入一个最近的 RINEX 文件。"""
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
			QtWidgets.QMessageBox.warning(self, "提示", "未在 data/ 下找到可用 RINEX 文件。")
		else:
			msg = [f"{k}: {v}" for k, v in found.items()]
			QtWidgets.QMessageBox.information(self, "已导入星历", "\n".join(msg))

	def _parse_gpgga(self, path: str):
		"""
		简易 $GPGGA 解析：返回 [(datetime, lat, lon, alt), ...]
		支持格式: $GPGGA,hhmmss.sss,lat,NS,lon,EW,fix,nsat,hdop,alt,M,geoid,M,age,ref*cs
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
		# 检查 DLL 是否在当前目录或 PATH 中（Windows）
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
		msg.append(f"配置: 采样率 {fs} Hz, 载频 {fc} Hz, 衰减 {attn} dB")
		if missing:
			msg.append("缺少 DLL: " + ", ".join(missing))
		else:
			msg.append("已找到 DLL（当前目录或 PATH）")

		# Try to open Pluto
		try:
			if adi is None:
				raise RuntimeError("未安装 pyadi-iio")
			d = adi.Pluto(uri)
			msg.append(f"已连接: fs={d.sample_rate}, 载频={d.tx_lo}, 带宽={getattr(d, 'tx_rf_bandwidth', 'n/a')}")
		except Exception as e:
			msg.append(f"连接失败: {e}")
		QtWidgets.QMessageBox.information(self, "探测结果", "\n".join(msg))


def main():
	# Deps already checked above
	app = QtWidgets.QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
