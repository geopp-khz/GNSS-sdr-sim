# GNSS SDR Simulator - Detailed File Structure Guide

## Project Overview
This is a comprehensive GNSS (Global Navigation Satellite System) software-defined radio (SDR) signal simulator that supports GPS, Galileo, BeiDou, GLONASS, IRNSS, QZSS, and SBAS signal generation. The project includes multiple modules covering Python-based simulation, C++ implementations, FPGA hardware design, and more.

## Directory Structure

### 📁 Root Directory Files
- **README.MD** - Basic project overview and usage guide
- **FILE_STRUCTURE.md** - This file, a detailed explanation of the project file structure
- **networkedSDR.grc** - GNU Radio Companion flowgraph file
- **networkedSDR.py** - GNU Radio Python script for network SDR configuration
- **libad9361.dll** - AD9361 RF front-end library
- **libiio.dll** - IIO (Industrial I/O) library

---

## 🐍 GNSS-sim-python/ - Python Simulation Module

### Core Simulation Files
- **main.py** - Main simulation program for generating GNSS signal data and time-delay files
- **const.py** - Global constant definitions (speed of light, Earth parameters, etc.)
- **Satallite.py** - Satellite class definitions and orbit calculations
- **orbit.py** - Orbital mechanics calculations (propagation time, Doppler shift, visibility)
- **NavMessage.py** - Navigation message generation and handling
- **RINEX.py** - RINEX-format navigation file parser
- **ionosphere.py** - Ionospheric delay model

### Constellation Implementations
- **GPS.py** - GPS L1 C/A signal implementation
  - Supports RINEX data parsing for the GPS constellation
  - Includes PRN code generation and navigation message formatting
  - Frequency: 1575.42 MHz
- **Galileo.py** - Galileo E1 signal implementation
  - Supports RINEX data parsing for the Galileo constellation
  - Includes CBOC modulation and navigation message formatting
  - Frequency: 1575.42 MHz
- **Glonass.py** - GLONASS L1 signal implementation
  - Supports RINEX data parsing for the GLONASS constellation
  - Includes FDMA frequency allocation and navigation message formatting
  - Frequency: 1602 MHz + k x 562.5 kHz
- **BeiDou.py** - BeiDou B1I signal implementation
  - Supports RINEX data parsing for the BeiDou constellation
  - Includes navigation message formatting and orbit calculations
  - Frequency: 1561.098 MHz
- **IRNSS.py** - IRNSS L5 signal implementation
  - Supports RINEX data parsing for the IRNSS constellation
  - Includes navigation message formatting
  - Frequency: 1176.45 MHz
- **Constelation.py** - Base constellation class definitions

### Utility Tools
- **sampleGeneration.py** - Sample generation utility
- **mixFiles.py** - File mixing utility
- **mulSatpos.py** - Multi-satellite position calculation
- **steering.py** - Antenna steering control
- **testAltMethode.py** - Alternative method test
- **testplot.py** - Plotting test utility
- **client.py** - Client communication module
- **pluto_studio.py** - ADALM-Pluto SDR studio interface
- **pluto_tx.py** - ADALM-Pluto SDR transmitter

---

## ⚙️ GNSS-sim-C/ - C++ Implementation Module

### Core C++ Files
- **GNSS-sim-C.cpp** - Main C++ program for high-performance signal generation
- **Manager.h** - Manager class coordinating the signal generation workflow
- **ChainLink.h** - Signal-processing chain component
- **DataFrame.h** - Data frame structure definitions
- **DataHandler.h** - Data handler
- **DataHandler2.h** - Version 2 of the data handler
- **FileSource.h** - File input source
- **FileSink.h** - File output sink
- **NetworkSink.h** - Network output sink
- **Server.h** - Network server
- **Parse.h** - Data parser
- **Resample.h** - Resampler
- **Resample2.h** - Version 2 of the resampler
- **Satellite.h** - Satellite class
- **WeilCode.h** - Weil code generator

### Constellation-Specific Implementations
#### GPS Module (GPS/)
- **Sat.h** - GPS satellite class
- **PRN_Code.h** - GPS PRN code generator
- **Modulation.h** - GPS modulator
- **L1c/** - GPS L1C signal implementation
  - Modulation.h, PRN_Code.h, Sat.h
- **L2c/** - GPS L2C signal implementation
  - Modulation.h, PRN_Code.h, Sat.h
- **L5/** - GPS L5 signal implementation
  - Sat.h

#### Galileo Module (Galileo/)
- **Sat.h** - Galileo satellite class
- **PRN_Code.h** - Galileo PRN code generator
- **Carrier.h** - Galileo carrier generation
- **CBOC.h** - CBOC modulator

#### Other Constellation Modules
- **BeiDou/** - BeiDou B1C signal implementation
- **Glonass/** - GLONASS signal implementation
- **IRNSS/** - IRNSS signal implementation

### Supporting Files
- **IQ.h** - IQ data format definitions
- **FPGA_data.h** - FPGA data transfer format

---

## 🔧 GNSS-sim-fpga/ - FPGA Hardware Implementation

### HDL Version 1 (HDL/)
- **Top.vhd** - Top-level FPGA design
- **Constants.vhd** - Constant definitions
- **DataSource.vhd** - Data source module
- **DopplerUpsample.vhd** - Doppler upsampler
- **ExampleSource.vhd** - Example data source
- **FrameHandler.vhd** - Frame handler
- **Mixer.vhd** - Mixer
- **Chanel.vhd** - Channel processor

#### Communication Modules (comminucation/)
- **ClockDiv16.vhd** - Clock divider
- **FIFO.vhd** - First-in, first-out buffer
- **InputHandler.vhd** - Input handler
- **OutputHandler.vhd** - Output handler
- **SPI.vhd** - SPI communication protocol

#### Simple Signals (simplesignals/)
- **GlonassModulation.vhd** - GLONASS modulator

#### Testbenches (testbenches/)
- Various VHDL testbench files

### HDL Version 2 (HDL2/) - Improved Version
- **Top.vhd** - Improved top-level design
- **ChanelsHandler.vhd** - Channel processor
- **DopplerUpsample.vhd** - Doppler upsampler
- **FrameHandler.vhd** - Frame handler
- **Mixer.vhd** - Mixer
- **Modulation.vhd** - Generic modulator
- **RegisterInterface.vhd** - Register interface

#### Constellation-Specific FPGA Implementations
- **GPS/** - GPS FPGA implementation
- **Galileo/** - Galileo FPGA implementation
- **BeiDou/** - BeiDou FPGA implementation
- **Glonass/** - GLONASS FPGA implementation
- **IRNSS/** - IRNSS FPGA implementation

#### Communication Modules (communication/)
- **ClockDiv16.vhd** - Clock divider
- **FIFO.vhd** - First-in, first-out buffer
- **SPI.vhd** - SPI communication protocol
- **UART_RX.vhd** - UART receiver
- **UART_TX.vhd** - UART transmitter

### ISE Project Files
- **ISE/** - Xilinx ISE project files
- **ISE2/** - Second ISE project
- **Top.ucf** - Pin constraint file
- **LogicAnalyzerSettings.kvset** - Logic analyzer settings

---

## 🔌 GNSS-sim-fpga-io/ - FPGA Interface Module

### Arduino Interface Code
- **GNSS-sim-fpga-io.ino** - Main Arduino program
- **fpgaInterface.h** - FPGA interface definitions
- **dataFrame.h** - Data frame structure
- **parsing.h** - Data parsing
- **IQ.h** - IQ data format
- **delayStepCheck.py** - Delay step check
- **delay_step_formulas.txt** - Delay step formulas
- **pynq_transmit.py** - PYNQ transmission script
- **transmit.py** - Transmission script

### Raw Code (raw/)
- **fpgaInterface.h** - Original FPGA interface
- **iq.h** - Original IQ format
- **raw.ino** - Original Arduino code

---

## 📊 data/ - Data File Directory

### Navigation Data Files
#### GPS Data (GPS/)
- **Brdc0530.24n** - 2024 GPS broadcast ephemeris
- **brdc3240.23n** - 2023 GPS broadcast ephemeris
- **brdc3250.23n** - 2023 GPS broadcast ephemeris
- **brdc3260.23n** - 2023 GPS broadcast ephemeris

#### Galileo Data (Galileo/)
- **Brdc0530.24l** - 2024 Galileo broadcast ephemeris
- **C7_E1B.txt** - Galileo E1B signal data
- **C8_E1C.txt** - Galileo E1C signal data
- **IZMI00TUR_S_20233320000_01D_EN.rnx** - Galileo RINEX file

#### GLONASS Data (Glonass/)
- **Brdc0070.24g** - 2024 GLONASS broadcast ephemeris
- **Brdc0530.24g** - 2024 GLONASS broadcast ephemeris
- **ANK200TUR_S_20240110000_01D_RN.rnx** - GLONASS RINEX file
- **MCCT_240109.agl** - GLONASS almanac file
- **MCCT_240109.agp** - GLONASS almanac file

#### Other Constellation Data
- **BeiDou/** - BeiDou navigation data
- **IRNSS/** - IRNSS navigation data
- **QZSS/** - QZSS navigation data
- **SBAS/** - SBAS augmentation data
- **Mixed/** - Mixed-constellation data

### Output and Utility Files
- **OutputIQ.sigmf-meta** - IQ output metadata
- **compare.py** - IQ data comparison utility
- **plotIQ.py** - IQ data plotting utility

---

## 🔍 detectors/ - Signal Detection Module

- **CN0.py** - Carrier-to-noise ratio (C/N0) detector
- **energy.py** - Energy detector
- **fingers.py** - Correlator bank detector
- **settings.py** - Detector settings

---

## 🛠️ Technical Features

### Supported Signal Types
1. **GPS L1 C/A** - 1575.42 MHz
2. **GPS L1C** - 1575.42 MHz
3. **GPS L2C** - 1227.60 MHz
4. **GPS L5** - 1176.45 MHz
5. **Galileo E1** - 1575.42 MHz (CBOC modulation)
6. **GLONASS L1** - 1602 MHz + k x 562.5 kHz
7. **BeiDou B1I** - 1561.098 MHz
8. **BeiDou B1C** - 1575.42 MHz
9. **IRNSS L5** - 1176.45 MHz
10. **QZSS** - 1575.42 MHz
11. **SBAS** - 1575.42 MHz

### Accuracy Characteristics
- GPS, Galileo, GLONASS, and IRNSS: 0-10 meter accuracy (compared with FGI-GSRx)
- BeiDou: approximately 5 km error (known issue pending a fix)

### Hardware Support
- **ADALM-Pluto SDR** - RF front end
- **FPGA** - Hardware-accelerated signal generation
- **Arduino** - Interface control

### Development Environment
- **Python 3.x** - Primary simulation environment
- **Visual Studio 2019** - C++ development
- **Xilinx ISE** - FPGA development
- **Arduino IDE** - Microcontroller programming
- **GNU Radio** - SDR processing

---

## 🚀 Usage

### Basic Workflow
1. Prepare the RINEX file matching the desired constellation and time.
2. Edit the configuration file and parameters in `GNSS-sim-python/main.py`.
3. Run `main.py` to generate the data and delay files.
4. Edit `GNSS-sim-C/GNSS-sim-C/GNSS-sim-C.cpp` to set the sample rate and center frequency.
5. Run the C++ project in Visual Studio.
6. The IQ file is written to `data/OutputIQ.sigmf-data`.

### Advanced Features
- **Real-time transmission** - Transmit live through the ADALM-Pluto SDR
- **FPGA acceleration** - Use hardware acceleration for signal generation
- **Network SDR** - Remote SDR control
- **Signal analysis** - Built-in signal quality detection

---

## 📝 Notes

1. **Project status** - This project is still under active development.
2. **BeiDou accuracy** - The BeiDou implementation currently has a known 5 km error issue.
3. **Dependencies** - The required Python packages and development tools must be installed.
4. **Hardware requirements** - FPGA and SDR hardware are optional components.
5. **Data files** - Valid RINEX navigation data files are required.

---

## 🤝 Contribution Guide

This is an open-source project, and contributions are welcome:
- Report bugs and issues
- Submit code improvements
- Add support for new constellations
- Optimize performance and accuracy
- Improve documentation and examples

---

*Last updated: January 2025*
