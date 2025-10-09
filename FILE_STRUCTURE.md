# GNSS SDR Simulator - 详细文件结构说明

## 项目概述
这是一个全面的GNSS（全球导航卫星系统）软件定义无线电（SDR）信号仿真器，支持GPS、Galileo、BeiDou、GLONASS、IRNSS、QZSS和SBAS信号生成。项目包含Python仿真、C++实现、FPGA硬件设计等多个模块。

## 目录结构

### 📁 根目录文件
- **README.MD** - 项目基本说明和使用指南
- **FILE_STRUCTURE.md** - 本文件，详细的项目文件结构说明
- **networkedSDR.grc** - GNU Radio Companion流程图文件
- **networkedSDR.py** - GNU Radio Python脚本，用于网络SDR配置
- **libad9361.dll** - AD9361射频前端库文件
- **libiio.dll** - IIO（Industrial I/O）库文件

---

## 🐍 GNSS-sim-python/ - Python仿真模块

### 核心仿真文件
- **main.py** - 主仿真程序，生成GNSS信号数据和时间延迟文件
- **const.py** - 全局常量定义（光速、地球参数等）
- **Satallite.py** - 卫星类定义和轨道计算
- **orbit.py** - 轨道力学计算（传播时间、多普勒频移、可见性）
- **NavMessage.py** - 导航消息生成和处理
- **RINEX.py** - RINEX格式导航文件解析器
- **ionosphere.py** - 电离层延迟模型

### 星座系统实现
- **GPS.py** - GPS L1 C/A信号实现
  - 支持GPS星座的RINEX数据解析
  - 包含PRN码生成、导航消息格式
  - 频率：1575.42 MHz
- **Galileo.py** - Galileo E1信号实现
  - 支持Galileo星座的RINEX数据解析
  - 包含CBOC调制、导航消息格式
  - 频率：1575.42 MHz
- **Glonass.py** - GLONASS L1信号实现
  - 支持GLONASS星座的RINEX数据解析
  - 包含FDMA频率分配、导航消息格式
  - 频率：1602 MHz + k×562.5 kHz
- **BeiDou.py** - BeiDou B1I信号实现
  - 支持BeiDou星座的RINEX数据解析
  - 包含导航消息格式和轨道计算
  - 频率：1561.098 MHz
- **IRNSS.py** - IRNSS L5信号实现
  - 支持IRNSS星座的RINEX数据解析
  - 包含导航消息格式
  - 频率：1176.45 MHz
- **Constelation.py** - 星座基类定义

### 辅助工具
- **sampleGeneration.py** - 样本生成工具
- **mixFiles.py** - 文件混合工具
- **mulSatpos.py** - 多卫星位置计算
- **steering.py** - 天线指向控制
- **testAltMethode.py** - 测试替代方法
- **testplot.py** - 测试绘图工具
- **client.py** - 客户端通信模块
- **pluto_studio.py** - ADALM-Pluto SDR工作室界面
- **pluto_tx.py** - ADALM-Pluto SDR发射器

---

## ⚙️ GNSS-sim-C/ - C++实现模块

### 核心C++文件
- **GNSS-sim-C.cpp** - C++主程序，高性能信号生成
- **Manager.h** - 管理器类，协调信号生成流程
- **ChainLink.h** - 信号处理链组件
- **DataFrame.h** - 数据帧结构定义
- **DataHandler.h** - 数据处理器
- **DataHandler2.h** - 数据处理器第二版
- **FileSource.h** - 文件输入源
- **FileSink.h** - 文件输出汇
- **NetworkSink.h** - 网络输出汇
- **Server.h** - 网络服务器
- **Parse.h** - 数据解析器
- **Resample.h** - 重采样器
- **Resample2.h** - 重采样器第二版
- **Satellite.h** - 卫星类
- **WeilCode.h** - Weil码生成器

### 星座特定实现
#### GPS模块 (GPS/)
- **Sat.h** - GPS卫星类
- **PRN_Code.h** - GPS PRN码生成器
- **Modulation.h** - GPS调制器
- **L1c/** - GPS L1C信号实现
  - Modulation.h, PRN_Code.h, Sat.h
- **L2c/** - GPS L2C信号实现
  - Modulation.h, PRN_Code.h, Sat.h
- **L5/** - GPS L5信号实现
  - Sat.h

#### Galileo模块 (Galileo/)
- **Sat.h** - Galileo卫星类
- **PRN_Code.h** - Galileo PRN码生成器
- **Carrier.h** - Galileo载波生成
- **CBOC.h** - CBOC调制器

#### 其他星座模块
- **BeiDou/** - BeiDou B1C信号实现
- **Glonass/** - GLONASS信号实现
- **IRNSS/** - IRNSS信号实现

### 支持文件
- **IQ.h** - IQ数据格式定义
- **FPGA_data.h** - FPGA数据传输格式

---

## 🔧 GNSS-sim-fpga/ - FPGA硬件实现

### HDL版本1 (HDL/)
- **Top.vhd** - 顶层FPGA设计
- **Constants.vhd** - 常量定义
- **DataSource.vhd** - 数据源模块
- **DopplerUpsample.vhd** - 多普勒上采样器
- **ExampleSource.vhd** - 示例数据源
- **FrameHandler.vhd** - 帧处理器
- **Mixer.vhd** - 混频器
- **Chanel.vhd** - 通道处理器

#### 通信模块 (comminucation/)
- **ClockDiv16.vhd** - 时钟分频器
- **FIFO.vhd** - 先进先出缓冲区
- **InputHandler.vhd** - 输入处理器
- **OutputHandler.vhd** - 输出处理器
- **SPI.vhd** - SPI通信协议

#### 简单信号 (simplesignals/)
- **GlonassModulation.vhd** - GLONASS调制器

#### 测试台 (testbenches/)
- 各种VHDL测试台文件

### HDL版本2 (HDL2/) - 改进版本
- **Top.vhd** - 改进的顶层设计
- **ChanelsHandler.vhd** - 通道处理器
- **DopplerUpsample.vhd** - 多普勒上采样器
- **FrameHandler.vhd** - 帧处理器
- **Mixer.vhd** - 混频器
- **Modulation.vhd** - 通用调制器
- **RegisterInterface.vhd** - 寄存器接口

#### 星座特定FPGA实现
- **GPS/** - GPS FPGA实现
- **Galileo/** - Galileo FPGA实现
- **BeiDou/** - BeiDou FPGA实现
- **Glonass/** - GLONASS FPGA实现
- **IRNSS/** - IRNSS FPGA实现

#### 通信模块 (communication/)
- **ClockDiv16.vhd** - 时钟分频器
- **FIFO.vhd** - 先进先出缓冲区
- **SPI.vhd** - SPI通信协议
- **UART_RX.vhd** - UART接收器
- **UART_TX.vhd** - UART发射器

### ISE项目文件
- **ISE/** - Xilinx ISE项目文件
- **ISE2/** - 第二个ISE项目
- **Top.ucf** - 引脚约束文件
- **LogicAnalyzerSettings.kvset** - 逻辑分析仪设置

---

## 🔌 GNSS-sim-fpga-io/ - FPGA接口模块

### Arduino接口代码
- **GNSS-sim-fpga-io.ino** - 主Arduino程序
- **fpgaInterface.h** - FPGA接口定义
- **dataFrame.h** - 数据帧结构
- **parsing.h** - 数据解析
- **IQ.h** - IQ数据格式
- **delayStepCheck.py** - 延迟步长检查
- **delay_step_formulas.txt** - 延迟步长公式
- **pynq_transmit.py** - PYNQ传输脚本
- **transmit.py** - 传输脚本

### 原始代码 (raw/)
- **fpgaInterface.h** - 原始FPGA接口
- **iq.h** - 原始IQ格式
- **raw.ino** - 原始Arduino代码

---

## 📊 data/ - 数据文件目录

### 导航数据文件
#### GPS数据 (GPS/)
- **Brdc0530.24n** - 2024年GPS广播星历
- **brdc3240.23n** - 2023年GPS广播星历
- **brdc3250.23n** - 2023年GPS广播星历
- **brdc3260.23n** - 2023年GPS广播星历

#### Galileo数据 (Galileo/)
- **Brdc0530.24l** - 2024年Galileo广播星历
- **C7_E1B.txt** - Galileo E1B信号数据
- **C8_E1C.txt** - Galileo E1C信号数据
- **IZMI00TUR_S_20233320000_01D_EN.rnx** - Galileo RINEX文件

#### GLONASS数据 (Glonass/)
- **Brdc0070.24g** - 2024年GLONASS广播星历
- **Brdc0530.24g** - 2024年GLONASS广播星历
- **ANK200TUR_S_20240110000_01D_RN.rnx** - GLONASS RINEX文件
- **MCCT_240109.agl** - GLONASS历书文件
- **MCCT_240109.agp** - GLONASS历书文件

#### 其他星座数据
- **BeiDou/** - BeiDou导航数据
- **IRNSS/** - IRNSS导航数据
- **QZSS/** - QZSS导航数据
- **SBAS/** - SBAS增强数据
- **Mixed/** - 混合星座数据

### 输出和工具文件
- **OutputIQ.sigmf-meta** - IQ输出元数据
- **compare.py** - IQ数据比较工具
- **plotIQ.py** - IQ数据绘图工具

---

## 🔍 detectors/ - 信号检测模块

- **CN0.py** - 载噪比(C/N0)检测器
- **energy.py** - 能量检测器
- **fingers.py** - 相关器组检测器
- **settings.py** - 检测器设置

---

## 🛠️ 技术特性

### 支持的信号类型
1. **GPS L1 C/A** - 1575.42 MHz
2. **GPS L1C** - 1575.42 MHz
3. **GPS L2C** - 1227.60 MHz
4. **GPS L5** - 1176.45 MHz
5. **Galileo E1** - 1575.42 MHz (CBOC调制)
6. **GLONASS L1** - 1602 MHz + k×562.5 kHz
7. **BeiDou B1I** - 1561.098 MHz
8. **BeiDou B1C** - 1575.42 MHz
9. **IRNSS L5** - 1176.45 MHz
10. **QZSS** - 1575.42 MHz
11. **SBAS** - 1575.42 MHz

### 精度特性
- GPS、Galileo、GLONASS、IRNSS：0-10米精度（与FGI-GSRx对比）
- BeiDou：约5公里误差（已知问题待修复）

### 硬件支持
- **ADALM-Pluto SDR** - 射频前端
- **FPGA** - 硬件加速信号生成
- **Arduino** - 接口控制

### 开发环境
- **Python 3.x** - 主要仿真环境
- **Visual Studio 2019** - C++开发
- **Xilinx ISE** - FPGA开发
- **Arduino IDE** - 微控制器编程
- **GNU Radio** - SDR处理

---

## 🚀 使用方法

### 基本工作流程
1. 准备对应星座和时间的RINEX文件
2. 编辑 `GNSS-sim-python/main.py` 配置文件和参数
3. 运行 `main.py` 生成数据和延迟文件
4. 编辑 `GNSS-sim-C/GNSS-sim-C/GNSS-sim-C.cpp` 设置采样率和中心频率
5. 在Visual Studio中运行C++项目
6. IQ文件输出到 `data/OutputIQ.sigmf-data`

### 高级功能
- **实时传输** - 通过ADALM-Pluto SDR实时发射
- **FPGA加速** - 硬件加速信号生成
- **网络SDR** - 远程SDR控制
- **信号分析** - 内置信号质量检测

---

## 📝 注意事项

1. **项目状态** - 这是一个正在开发中的项目
2. **BeiDou精度** - BeiDou实现存在已知的5公里误差问题
3. **依赖项** - 需要安装相应的Python包和开发工具
4. **硬件要求** - FPGA和SDR硬件为可选组件
5. **数据文件** - 需要有效的RINEX导航数据文件

---

## 🤝 贡献指南

这是一个开源项目，欢迎贡献：
- 报告Bug和问题
- 提交代码改进
- 添加新的星座支持
- 优化性能和精度
- 完善文档和示例

---

*最后更新：2025年1月*
