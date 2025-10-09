# GNSS SDR Signal Simulator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![C++](https://img.shields.io/badge/C++-17-green.svg)](https://en.cppreference.com/w/cpp/17)
[![FPGA](https://img.shields.io/badge/FPGA-VHDL-orange.svg)](https://en.wikipedia.org/wiki/VHDL)

A comprehensive **Software-Defined Radio (SDR)** simulator for Global Navigation Satellite System (GNSS) signals. This project supports multiple satellite constellations and provides both software simulation and hardware implementation capabilities.

## 🌟 Features

### Supported Satellite Systems
- **GPS** - L1 C/A, L1C, L2C, L5 signals
- **Galileo** - E1 signals with CBOC modulation
- **GLONASS** - L1 signals with FDMA
- **BeiDou** - B1I and B1C signals
- **IRNSS** - L5 signals
- **QZSS** - Japanese regional system
- **SBAS** - Satellite-Based Augmentation Systems

### Implementation Approaches
- **Python Simulation** - High-level signal generation and orbit modeling
- **C++ Implementation** - High-performance real-time signal generation
- **FPGA Hardware** - Hardware-accelerated signal processing
- **SDR Integration** - ADALM-Pluto SDR support for real-time transmission

## 📊 Accuracy Performance

| Constellation | Accuracy | Status |
|---------------|----------|---------|
| GPS | 0-10 meters | ✅ Verified |
| Galileo | 0-10 meters | ✅ Verified |
| GLONASS | 0-10 meters | ✅ Verified |
| IRNSS | 0-10 meters | ✅ Verified |
| BeiDou | ~5 km error | ⚠️ Known Issue |

*Accuracy measured against FGI-GSRx reference receiver*

## 🚀 Quick Start

### Prerequisites
- Python 3.x with NumPy, SciPy
- Visual Studio 2019 (for C++ implementation)
- Xilinx ISE (for FPGA development)
- ADALM-Pluto SDR (optional, for real-time transmission)

### Basic Usage

1. **Prepare RINEX Data**
   ```bash
   # Download RINEX navigation files for your desired constellation and time period
   # Place them in the appropriate data/ directory
   ```

2. **Configure Simulation**
   ```python
   # Edit GNSS-sim-python/main.py
   constelation = GPS.getConstelation()  # Choose constellation
   rinexFile = "data/GPS/brdc3240.23n"   # Set RINEX file
   startTime = datetime.datetime(2023,11,20, 0, 0)  # Set start time
   duration = datetime.timedelta(seconds=181)       # Set duration
   ```

3. **Generate Signal Data**
   ```bash
   cd GNSS-sim-python
   python main.py
   ```

4. **Configure C++ Implementation**
   ```cpp
   // Edit GNSS-sim-C/GNSS-sim-C/GNSS-sim-C.cpp
   // Set sampling rate and center frequency
   ```

5. **Run Signal Generation**
   ```bash
   # Open in Visual Studio 2019 and build/run
   # Output: data/OutputIQ.sigmf-data
   ```

## 📁 Project Structure

```
GNSS-sdr-sim/
├── GNSS-sim-python/     # Python simulation modules
├── GNSS-sim-C/          # C++ high-performance implementation
├── GNSS-sim-fpga/       # FPGA hardware design (VHDL)
├── GNSS-sim-fpga-io/    # FPGA interface (Arduino)
├── data/                # Navigation data files (RINEX)
├── detectors/           # Signal quality analysis
└── FILE_STRUCTURE.md    # Detailed file documentation
```

*See [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for comprehensive file documentation*

## 🛠️ Advanced Features

### Real-time SDR Transmission
```python
# Use ADALM-Pluto SDR for real-time signal transmission
python GNSS-sim-python/pluto_studio.py
```

### FPGA Hardware Acceleration
```vhdl
-- Synthesize VHDL code for FPGA implementation
-- Provides real-time signal generation capabilities
```

### Signal Analysis
```python
# Analyze generated signals
python detectors/CN0.py      # Carrier-to-noise ratio
python detectors/energy.py   # Energy detection
```

## 🔧 Configuration Options

### Signal Parameters
- **Sampling Rate**: Configurable (typically 2-10 MHz)
- **Center Frequency**: Constellation-specific
- **Signal Duration**: User-defined
- **User Position**: ECEF coordinates
- **Power Levels**: Adjustable per satellite

### Output Formats
- **IQ Files**: Standard complex baseband format
- **Network Streaming**: Real-time UDP transmission
- **Hardware Output**: Direct FPGA/SDR interface

## 📚 Documentation

- **[FILE_STRUCTURE.md](FILE_STRUCTURE.md)** - Detailed file and module documentation
- **Inline Comments** - Extensive code documentation
- **Configuration Examples** - Sample configurations for different scenarios

## 🤝 Contributing

This is an active development project. Contributions are welcome:

- 🐛 **Bug Reports** - Report issues and inaccuracies
- 💻 **Code Improvements** - Optimize performance and add features
- 📡 **New Constellations** - Add support for additional GNSS systems
- 📖 **Documentation** - Improve guides and examples
- 🧪 **Testing** - Validate against reference receivers

### Known Issues
- BeiDou implementation has ~5km positioning error (investigation ongoing)
- Some edge cases in orbit propagation need refinement
- Real-time performance optimization needed for extended simulations

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- FGI-GSRx for accuracy validation
- RINEX data providers
- Open source SDR community
- GNSS research community

## 📞 Support

For questions, issues, or contributions:
- Create an [Issue](https://github.com/lzs920924/GNSS-sdr-sim/issues)
- Review the [FILE_STRUCTURE.md](FILE_STRUCTURE.md) documentation
- Check inline code comments for implementation details

---

**Note**: This project is actively maintained and improved. The BeiDou accuracy issue is a known limitation that will be addressed in future releases.