# Universal Power Profiler & Dual Wattmeter (Web IDE & Desktop)

A clean, modern, universal testbench instrument that runs **directly in your web browser (Arduino Online Cloud IDE style)** or as a **native desktop application**.

Built for dual-channel power profiling (input vs output), conversion ratio and efficiency ($\eta$) computation, real-time waveform plotting, and continuous CSV acquisition. Compatible with **IeS ISW8001** and serial/Ethernet power meters via **Serial COM (RS-232)** or **WIZnet WIZ750SR-110 (Ethernet TCP)**.

---

## 🌟 Key Highlights

- **Web Browser Interface (Arduino Cloud IDE Style)**:
  - Clean dark-mode instrument workbench powered by HTML5, Tailwind CSS, and Chart.js.
  - Tabular typography and WCAG-compliant accessible contrast (`baseline-ui`).
  - Real-time 60 FPS live waveform plotting for both channels.
  - **Direct Web Serial API**: Direct browser access to serial ports in Chrome & Edge with zero drivers required.
  - **Local WebSocket Bridge**: Connects browser seamlessly to local COM ports, WIZ750SR TCP sockets (`IP:5000`), or built-in test simulators.
- **Desktop GUI**:
  - Full-featured standalone desktop application (`dual_wattmeter_gui.py`).
- **Universal & Unlocked**:
  - Works with any dual-channel power setup (converters, chargers, inverters, power supplies, motors, or testbenches).
- **Automated 1-Click Installer**:
  - `install.bat` / `setup.py` automatically checks Python, installs all dependencies, and creates Desktop shortcuts.

---

## 🚀 1-Click Installation

### On Windows:
Double-click:
```cmd
install.bat
```
*(or run `python setup.py` in your terminal)*

This script will:
1. Check your Python environment (Python 3.9+ supported).
2. Install all required dependencies (`pyserial`, `websockets`, `matplotlib`, `numpy`).
3. Create 1-click shortcuts directly on your **Desktop**:
   - `PowerProfilerWeb.lnk` (Browser Web IDE)
   - `PowerProfilerDesktop.lnk` (Desktop GUI)

---

## 💻 How to Run

### Option 1: Browser Web IDE (Recommended)
Double-click `Launch-Web-IDE.bat` or run:
```bash
python web_server.py
```
Then open your browser at **[http://localhost:8000](http://localhost:8000)**.

### Option 2: Desktop GUI Application
Double-click `Launch-Desktop-GUI.bat` or run:
```bash
python dual_wattmeter_gui.py
```

---

## 🔌 Connection Modes

| Mode | Configuration | Description |
|---|---|---|
| **Serial COM** | Port selection (e.g. `COM3`), 9600 baud | Direct RS-232 serial cable connection |
| **Ethernet TCP** | `IP:Port` (e.g. `192.168.11.2:5000`) | Network connection via WIZnet WIZ750SR-110 serial-to-Ethernet gateway |
| **Virtual Simulator** | `SIMULATOR-P1` / `SIMULATOR-P2` | Integrated mock meter generating realistic ISW8001 telemetry for testing without hardware |
| **Web Serial API** | Top-bar button in Chrome/Edge | Direct sandbox serial communication from the browser |

---

## 📊 Live Metrics & Data Export

- **Primary Readouts**: Tabular numerical display for **Voltage (V)**, **Current (A)**, and **Active Power (W)**.
- **Conversion Efficiency**: Real-time ratio $\eta = \frac{P_2}{P_1} \times 100\%$.
- **Power Loss / Delta**: $\Delta P = P_1 - P_2$ (active dissipation in Watts).
- **ISW8001 Commands**: One-click command triggers for `WATT`, `VAR`, `VOLT`, `AMP`, `PWF`, and `AutoRange`.
- **CSV Data Logging**:
  - **Live Continuous Recording**: Stream rows directly to CSV with millisecond timestamps.
  - **Instant Snapshot**: Export current bench state to CSV with one click.

---

## 📁 Repository Structure

```
├── web/
│   └── index.html               # Web IDE interface (Tailwind + Chart.js + Web Serial)
├── web_server.py                # HTTP server & WebSocket instrument bridge
├── dual_wattmeter_gui.py        # Desktop Tkinter GUI application
├── install.bat                  # 1-Click Windows installer & shortcut generator
├── setup.py                     # Cross-platform automated setup script
├── Launch-Web-IDE.bat           # 1-Click launcher for Browser Web IDE
├── Launch-Desktop-GUI.bat       # 1-Click launcher for Desktop GUI
├── requirements.txt             # Python dependencies
└── README.md                    # Documentation
```

---

## 📄 License
MIT License. Free for laboratory, educational, and commercial testing benches.
