import argparse
import json
import os
import sys
import time
from typing import Optional, Tuple

import numpy as np

try:
	import adi  # pyadi-iio
except ImportError:
	adi = None


def read_sigmf_meta(meta_path: str) -> Tuple[Optional[float], Optional[float]]:
	"""
	Read SIGMF .sigmf-meta and return (center_freq_hz, sample_rate_hz) if available.
	"""
	try:
		with open(meta_path, "r", encoding="utf-8") as f:
			meta = json.load(f)
			global_meta = meta.get("global", {})
			# SigMF names
			center_freq = global_meta.get("core:frequency")
			sample_rate = global_meta.get("core:sample_rate")
			# Some generators use alternative keys
			if center_freq is None:
				center_freq = global_meta.get("core:freq") or global_meta.get("frequency")
			if sample_rate is None:
				sample_rate = global_meta.get("core:sample_rate_hz") or global_meta.get("sample_rate")
			return (
				float(center_freq) if center_freq is not None else None,
				float(sample_rate) if sample_rate is not None else None,
			)
	except Exception:
		return (None, None)


def load_sigmf_data(data_path: str, dtype: str = "int8") -> np.ndarray:
	"""
	Load interleaved IQ from .sigmf-data file.
	Supported dtype: int8 (default) or float32.
	Returns complex64 numpy array normalized to [-1, 1] range for float path.
	"""
	if dtype not in ("int8", "float32"):
		raise ValueError("dtype must be 'int8' or 'float32'")

	raw = np.fromfile(data_path, dtype=np.int8 if dtype == "int8" else np.float32)
	if raw.size % 2 != 0:
		raw = raw[:-1]
	I = raw[0::2]
	Q = raw[1::2]
	if dtype == "int8":
		# Convert to complex float normalized
		scale = 127.0
		return (I.astype(np.float32) / scale + 1j * (Q.astype(np.float32) / scale)).astype(np.complex64)
	else:
		return (I.astype(np.float32) + 1j * Q.astype(np.float32)).astype(np.complex64)


def chunked_stream(tx, data: np.ndarray, samplerate: float, repeat: bool, buf_len: int = 1 << 14):
	"""
	Stream complex64 data to PlutoSDR in chunks. Optionally loop.
	"""
	# Ensure contiguous complex64
	data = np.ascontiguousarray(data.astype(np.complex64))
	N = data.size
	if N == 0:
		raise ValueError("No samples to transmit")

	idx = 0
	while True:
		end = min(idx + buf_len, N)
		buf = data[idx:end]
		if buf.size < buf_len and repeat:
			# Wrap-around to fill the buffer for smoother streaming
			need = buf_len - buf.size
			wrap = data[0:min(need, N)]
			buf = np.concatenate([buf, wrap])

		tx.tx_cyclic_buffer = False  # we manage repetition
		tx._ctx.set_timeout(5000)
		tx._ctx.set_kernel_buffers_count(2)
		tx._tx_main_buffer_size = max(buf_len, 16384)
		tx._txbuf.set_buffer_size(max(buf_len, 16384)) if hasattr(tx, "_txbuf") else None
		tx.tx(buf)

		idx += buf_len
		if idx >= N:
			if repeat:
				idx = 0
			else:
				break


def main():
	parser = argparse.ArgumentParser(description="Transmit SIGMF IQ to PlutoSDR using pyadi-iio")
	parser.add_argument("data", help="Path to .sigmf-data file")
	parser.add_argument("--meta", help="Path to .sigmf-meta file (auto center freq and sample rate)")
	parser.add_argument("--uri", default="ip:192.168.2.1", help="IIO device URI, e.g. ip:192.168.2.1 or usb:1.2.5")
	parser.add_argument("--freq", type=float, default=None, help="Center frequency in Hz (overrides meta)")
	parser.add_argument("--srate", type=float, default=None, help="Sample rate in Hz (overrides meta)")
	parser.add_argument("--gain", type=float, default=-10.0, help="TX attenuation (negative dB). Pluto uses attenuation.")
	parser.add_argument("--repeat", action="store_true", help="Loop the file indefinitely")
	parser.add_argument("--dtype", choices=["int8", "float32"], default="int8", help="Interpretation of .sigmf-data samples")
	parser.add_argument("--buf", type=int, default=1 << 14, help="TX buffer chunk length (complex samples)")
	args = parser.parse_args()

	if adi is None:
		print("ERROR: pyadi-iio is not installed. Install with: pip install pyadi-iio", file=sys.stderr)
		sys.exit(1)

	if not os.path.isfile(args.data):
		print(f"ERROR: data file not found: {args.data}", file=sys.stderr)
		sys.exit(1)

	meta_path = args.meta
	if meta_path is None:
		# try to infer sibling .sigmf-meta
		candidate = os.path.splitext(args.data)[0] + ".sigmf-meta"
		if os.path.isfile(candidate):
			meta_path = candidate

	meta_freq = None
	meta_rate = None
	if meta_path and os.path.isfile(meta_path):
		meta_freq, meta_rate = read_sigmf_meta(meta_path)

	center_freq = args.freq if args.freq is not None else meta_freq
	sample_rate = args.srate if args.srate is not None else meta_rate
	if center_freq is None or sample_rate is None:
		print("WARNING: Missing center frequency or sample rate. Provide --freq and --srate or a valid .sigmf-meta.", file=sys.stderr)

	# Load data
	data = load_sigmf_data(args.data, dtype=args.dtype)

	# Create Pluto device
	tx = adi.Pluto(args.uri)
	if sample_rate is not None:
		tx.sample_rate = int(sample_rate)
	if center_freq is not None:
		tx.tx_lo = int(center_freq)
	# Pluto uses attenuation (0 = max power). Keep conservative default.
	try:
		tx.tx_hardwaregain = float(args.gain)
	except Exception:
		pass

	# Baseband filter bandwidth slightly below sample rate (if set)
	if sample_rate is not None:
		try:
			tx.tx_rf_bandwidth = int(min(max(sample_rate * 0.8, 200000.0), 56000000.0))
		except Exception:
			pass

	print(f"Pluto configured: uri={args.uri}, f={tx.tx_lo} Hz, fs={tx.sample_rate} Hz, attn={getattr(tx,'tx_hardwaregain', 'n/a')} dB")
	print(f"Streaming {data.size} complex samples from {args.data} ({args.dtype})... repeat={args.repeat}")

	try:
		chunked_stream(tx, data, float(tx.sample_rate), args.repeat, buf_len=int(args.buf))
	except KeyboardInterrupt:
		print("Interrupted. Stopping TX...")
	finally:
		# A short mute to ensure buffers flush
		tx.tx(np.zeros(16384, dtype=np.complex64))
		time.sleep(0.1)
		tx.tx_destroy_buffer()


if __name__ == "__main__":
	main()
