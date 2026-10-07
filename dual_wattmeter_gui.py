"""
Universal Dual Wattmeter & Power Profiler
Compatible with IeS ISW8001 / ISW-series meters via Serial RS-232 / COM or Ethernet TCP (WIZnet WIZ750SR-110).
Redesigned with baseline-ui & WCAG-compliant design principles.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import csv
import datetime
import serial
import serial.tools.list_ports
import socket
import threading
import time
import re
import collections
import random

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation


# --- Mock Serial Simulator for Testing & Validation ---
class MockSerial:
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.is_open = True
        self.in_waiting = 0
        self.mode = "WATT"
        self.auto = False
        self._buffer = b""
        self._stop = False
        
        # P2 output is ~88% of P1 for realistic efficiency simulation
        self.eff_factor = 0.88 if "P2" in port else 1.0

        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def write(self, data):
        cmd = data.decode('ascii', errors='ignore').strip().upper()
        if cmd == "MA1":
            self.auto = True
        elif cmd == "MA0":
            self.auto = False
        elif cmd in ["WATT", "VAR", "VOLT", "AMP", "PWF"]:
            self.mode = cmd
            
    def read(self, size=1):
        if size > len(self._buffer):
            size = len(self._buffer)
        data = self._buffer[:size]
        self._buffer = self._buffer[size:]
        self.in_waiting = len(self._buffer)
        return data
        
    def _run(self):
        v = 230.0
        i = 2.4 * self.eff_factor
        
        while not self._stop:
            if self.auto:
                v_noise = v + random.uniform(-1.2, 1.2)
                i_noise = i + random.uniform(-0.03, 0.03)
                w_noise = v_noise * i_noise * 0.96 + random.uniform(-1.5, 1.5)
                
                if self.mode == "WATT":
                    line = f"U3={v_noise:.1f}E+0 I2={i_noise:.3f}E+0 W={w_noise:.2f}E+0\r"
                elif self.mode == "VAR":
                    var_val = w_noise * 0.22
                    line = f"U3={v_noise:.1f}E+0 I2={i_noise:.3f}E+0 VAR={var_val:.2f}E+0\r"
                elif self.mode == "PWF":
                    line = f"U3={v_noise:.1f}E+0 I2={i_noise:.3f}E+0 PF=0.960E+0\r"
                else:
                    line = f"U3={v_noise:.1f}E+0 I2={i_noise:.3f}E+0 W={w_noise:.2f}E+0\r"
                
                b_line = line.encode('ascii')
                # Inject intermittent XON/XOFF noise as documented for ISW8001
                if random.random() > 0.75:
                    b_line = b_line[:5] + b'\x11' + b_line[5:10] + b'\x13' + b_line[10:]
                
                self._buffer += b_line
                self.in_waiting = len(self._buffer)
            
            time.sleep(0.47)
            
    def close(self):
        self.is_open = False
        self._stop = True


# --- Universal Connection Handler (Serial COM or TCP/Ethernet for WIZ750SR) ---
class ConnectionHandler:
    def __init__(self, conn_type, target, baudrate=9600):
        self.conn_type = conn_type  # "SERIAL" or "TCP"
        self.target = target        # COM port string OR "IP:PORT"
        self.baudrate = baudrate
        self.serial_conn = None
        self.tcp_sock = None
        self.is_connected = False
        self.thread = None
        self.callback = None

    def connect(self):
        try:
            if self.conn_type == "SERIAL":
                if self.target.startswith("SIMULATOR"):
                    self.serial_conn = MockSerial(self.target, self.baudrate)
                else:
                    self.serial_conn = serial.Serial(self.target, self.baudrate, timeout=1)
            elif self.conn_type == "TCP":
                if ":" in self.target:
                    host, port_str = self.target.split(":", 1)
                    port = int(port_str.strip())
                else:
                    host = self.target.strip()
                    port = 5000
                
                self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tcp_sock.settimeout(3.0)
                self.tcp_sock.connect((host, port))
                self.tcp_sock.settimeout(0.5)

            self.is_connected = True
            self.send_command("MA1")
            
            self.thread = threading.Thread(target=self.read_loop, daemon=True)
            self.thread.start()
            return True, "Connected"
        except Exception as e:
            self.disconnect()
            return False, str(e)

    def disconnect(self):
        self.is_connected = False
        try:
            self.send_command("MA0")
            time.sleep(0.05)
        except Exception:
            pass

        if self.serial_conn and getattr(self.serial_conn, 'is_open', False):
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        if self.tcp_sock:
            try:
                self.tcp_sock.close()
            except Exception:
                pass
            self.tcp_sock = None

    def send_command(self, cmd):
        if not self.is_connected:
            return
        payload = f"{cmd}\r".encode('ascii')
        try:
            if self.conn_type == "SERIAL" and self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.write(payload)
            elif self.conn_type == "TCP" and self.tcp_sock:
                self.tcp_sock.sendall(payload)
        except Exception:
            pass

    def read_loop(self):
        buffer = b""
        while self.is_connected:
            try:
                data = b""
                if self.conn_type == "SERIAL":
                    if self.serial_conn and self.serial_conn.in_waiting > 0:
                        data = self.serial_conn.read(self.serial_conn.in_waiting)
                    else:
                        time.sleep(0.05)
                        continue
                elif self.conn_type == "TCP":
                    try:
                        data = self.tcp_sock.recv(1024)
                        if not data:
                            raise ConnectionResetError("Connection closed by WIZ750SR")
                    except socket.timeout:
                        continue

                if data:
                    data = data.replace(b'\x11', b'').replace(b'\x13', b'')
                    buffer += data
                    
                    if b'\r' in buffer:
                        lines = buffer.split(b'\r')
                        buffer = lines[-1]
                        for line in lines[:-1]:
                            if line.strip():
                                if self.callback:
                                    self.callback(line.decode('ascii', errors='ignore').strip())
            except Exception as e:
                if self.is_connected and self.callback:
                    self.callback(f"Error: {e}")
                self.disconnect()
                break


# ==============================================================================
# UI COLOR PALETTE & TYPOGRAPHY SPECIFICATION (CLEAN LAB WHITE / BASELINE-UI)
# ==============================================================================
THEME = {
    "bg": "#f8fafc",             # Clean slate-50 light canvas
    "surface": "#ffffff",        # Pure crisp white cards
    "surface_subtle": "#f1f5f9", # Subtle light gray elevated card (slate-100)
    "border": "#e2e8f0",         # Slate-200 clean borders
    "border_focus": "#0284c7",   # Sky-600 focus accent
    "text_primary": "#0f172a",   # Slate-900 sharp readable text
    "text_secondary": "#475569", # Slate-600 secondary labels
    "text_muted": "#64748b",     # Slate-500 captions / units
    
    # Semantic Readouts & Instruments
    "accent_cyan": "#0284c7",    # Channel 1 voltage (crisp blue)
    "accent_emerald": "#16a34a", # Current & efficiency (vibrant green)
    "accent_amber": "#d97706",   # Power & warnings (deep warm amber)
    "accent_violet": "#7c3aed",  # Secondary metrics
    
    # Control States
    "btn_bg": "#f1f5f9",
    "btn_hover": "#e2e8f0",
    "btn_active": "#0284c7",
    "btn_primary_bg": "#0284c7",
    "btn_primary_fg": "#ffffff",
    "badge_disconnected": "#94a3b8",
    "badge_connected": "#16a34a",
}

FONT_DISPLAY = ("Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", "Arial")
FONT_MONO = ("Consolas", "Cascadia Code", "Courier New")


class ModernCard(tk.Frame):
    """Refined container with subtle 1px border and consistent background."""
    def __init__(self, parent, **kwargs):
        bg = kwargs.pop("bg", THEME["surface"])
        super().__init__(parent, bg=bg, highlightthickness=1, 
                         highlightbackground=THEME["border"], highlightcolor=THEME["border"], **kwargs)


class DualPortGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Power Profiler — Universal Dual-Channel Bench")
        self.root.geometry("1240x880")
        self.root.minsize(1080, 760)
        self.root.configure(bg=THEME["bg"])

        # Configure TTK Styles to match Baseline Dark Theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.style.configure(".", background=THEME["surface"], foreground=THEME["text_primary"])
        self.style.configure("TCombobox", 
                             fieldbackground=THEME["surface_subtle"], 
                             background=THEME["border"],
                             foreground=THEME["text_primary"],
                             arrowcolor=THEME["text_secondary"],
                             darkcolor=THEME["border"],
                             lightcolor=THEME["border"],
                             bordercolor=THEME["border"])
        self.style.map("TCombobox", fieldbackground=[("readonly", THEME["surface_subtle"])])

        self.style.configure("TEntry", 
                             fieldbackground=THEME["surface_subtle"], 
                             foreground=THEME["text_primary"],
                             bordercolor=THEME["border"])

        # Action Buttons
        self.style.configure("Action.TButton",
                             background=THEME["btn_bg"],
                             foreground=THEME["text_primary"],
                             font=(FONT_DISPLAY[0], 9, "bold"),
                             borderwidth=1,
                             focuscolor="none",
                             padding=(10, 5))
        self.style.map("Action.TButton",
                       background=[("active", THEME["btn_hover"]), ("pressed", THEME["surface_subtle"])])

        # Primary Accent Button
        self.style.configure("Primary.TButton",
                             background=THEME["btn_primary_bg"],
                             foreground="#ffffff",
                             font=(FONT_DISPLAY[0], 9, "bold"),
                             borderwidth=0,
                             padding=(12, 5))
        self.style.map("Primary.TButton",
                       background=[("active", "#0369a1"), ("pressed", "#075985")])

        # State Variables
        self.handlers = {1: None, 2: None}
        self.data_history = {1: collections.deque(maxlen=120), 2: collections.deque(maxlen=120)}
        self.latest_power = {1: 0.0, 2: 0.0}
        self.latest_metrics = {
            1: {"v": None, "i": None, "p": None, "pf": None, "var": None},
            2: {"v": None, "i": None, "p": None, "pf": None, "var": None}
        }

        self.is_logging = False
        self.log_file = None
        self.csv_writer = None
        self.log_records_count = 0
        self.log_status_var = tk.StringVar(value="Idle")
        self.log_records_var = tk.StringVar(value="0 rows")

        # Top Header & Navigation Bar
        self._build_top_header()

        # Efficiency & Power Loss KPI Strip
        self._build_kpi_strip()

        # Main Dual-Channel Columns
        main_content = tk.Frame(root, bg=THEME["bg"])
        main_content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        self.col1 = self._build_channel_column(main_content, 1, "Channel 1 — Input Meter")
        self.col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.col2 = self._build_channel_column(main_content, 2, "Channel 2 — Output Meter")
        self.col2.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(8, 0))

        # Bottom System & Logging Strip
        self._build_bottom_toolbar()

        self.refresh_ports()
        self.ani = animation.FuncAnimation(self.fig1, self.update_charts, interval=500, cache_frame_data=False)

    def _build_top_header(self):
        header = tk.Frame(self.root, bg=THEME["bg"])
        header.pack(fill=tk.X, padx=18, pady=(14, 8))

        # Left brand / title
        left_box = tk.Frame(header, bg=THEME["bg"])
        left_box.pack(side=tk.LEFT)

        app_title = tk.Label(left_box, text="POWER PROFILER", 
                             font=(FONT_DISPLAY[0], 13, "bold"), fg=THEME["text_primary"], bg=THEME["bg"])
        app_title.pack(side=tk.LEFT)

        sub_tag = tk.Label(left_box, text="UNIVERSAL BENCH INSTRUMENT", 
                           font=(FONT_DISPLAY[0], 8, "bold"), fg=THEME["text_muted"], bg=THEME["surface"],
                           padx=6, pady=2)
        sub_tag.pack(side=tk.LEFT, padx=10)

        # Right status tag
        status_tag = tk.Label(header, text="DUAL ISW8001 / SERIAL + ETHERNET WIZ750SR",
                              font=(FONT_MONO[0], 9), fg=THEME["text_muted"], bg=THEME["bg"])
        status_tag.pack(side=tk.RIGHT)

    def _build_kpi_strip(self):
        kpi_card = ModernCard(self.root, bg=THEME["surface_subtle"])
        kpi_card.pack(fill=tk.X, padx=16, pady=(0, 12))

        inner = tk.Frame(kpi_card, bg=THEME["surface_subtle"], padx=16, pady=10)
        inner.pack(fill=tk.X)

        # Efficiency Pill
        eff_container = tk.Frame(inner, bg=THEME["surface_subtle"])
        eff_container.pack(side=tk.LEFT)

        tk.Label(eff_container, text="SYSTEM EFFICIENCY (η)", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(anchor="w")

        self.lbl_efficiency = tk.Label(eff_container, text="--- %", font=(FONT_MONO[0], 22, "bold"),
                                       fg=THEME["accent_emerald"], bg=THEME["surface_subtle"])
        self.lbl_efficiency.pack(anchor="w")

        # Divider
        tk.Frame(inner, bg=THEME["border"], width=1, height=44).pack(side=tk.LEFT, padx=24)

        # Power Delta Pill
        diff_container = tk.Frame(inner, bg=THEME["surface_subtle"])
        diff_container.pack(side=tk.LEFT)

        tk.Label(diff_container, text="POWER LOSS / DELTA (P1 - P2)", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(anchor="w")

        self.lbl_delta = tk.Label(diff_container, text="--- W", font=(FONT_MONO[0], 22, "bold"),
                                  fg=THEME["accent_amber"], bg=THEME["surface_subtle"])
        self.lbl_delta.pack(anchor="w")

        # Live Summary Details
        summary_container = tk.Frame(inner, bg=THEME["surface_subtle"])
        summary_container.pack(side=tk.RIGHT, fill=tk.Y)

        self.lbl_status_summary = tk.Label(
            summary_container, 
            text="Waiting for synchronized dual-channel measurements...",
            font=(FONT_DISPLAY[0], 9), fg=THEME["text_secondary"], bg=THEME["surface_subtle"], justify=tk.RIGHT
        )
        self.lbl_status_summary.pack(anchor="e", pady=(8, 0))

    def _build_channel_column(self, parent, port_id, title_text):
        card = ModernCard(parent, bg=THEME["surface"])

        # Header of Card
        hdr = tk.Frame(card, bg=THEME["surface"], padx=14, pady=10)
        hdr.pack(fill=tk.X)

        # Status badge dot
        badge_dot = tk.Label(hdr, text="●", font=(FONT_DISPLAY[0], 12), fg=THEME["text_muted"], bg=THEME["surface"])
        badge_dot.pack(side=tk.LEFT, padx=(0, 6))
        setattr(self, f"badge_dot_{port_id}", badge_dot)

        title_lbl = tk.Label(hdr, text=title_text, font=(FONT_DISPLAY[0], 11, "bold"),
                             fg=THEME["text_primary"], bg=THEME["surface"])
        title_lbl.pack(side=tk.LEFT)

        status_text = tk.Label(hdr, text="DISCONNECTED", font=(FONT_DISPLAY[0], 8, "bold"),
                               fg=THEME["text_muted"], bg=THEME["surface"])
        status_text.pack(side=tk.RIGHT)
        setattr(self, f"status_text_{port_id}", status_text)

        # Separator line
        tk.Frame(card, bg=THEME["border"], height=1).pack(fill=tk.X)

        # Connection Control Sub-card
        conn_bar = tk.Frame(card, bg=THEME["surface"], padx=14, pady=10)
        conn_bar.pack(fill=tk.X)

        # Mode Selector
        mode_var = tk.StringVar(value="SERIAL (COM)" if port_id == 1 else "ETHERNET (TCP)")
        setattr(self, f"conn_mode_{port_id}", mode_var)

        mode_cb = ttk.Combobox(conn_bar, textvariable=mode_var, values=["SERIAL (COM)", "ETHERNET (TCP)"],
                               width=13, state="readonly")
        mode_cb.pack(side=tk.LEFT, padx=(0, 6))
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self.on_mode_change(port_id))

        # Target Frame
        target_container = tk.Frame(conn_bar, bg=THEME["surface"])
        target_container.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Serial Frame
        serial_frame = tk.Frame(target_container, bg=THEME["surface"])
        setattr(self, f"serial_frame_{port_id}", serial_frame)

        port_cb = ttk.Combobox(serial_frame, width=14, font=(FONT_DISPLAY[0], 9))
        port_cb.pack(side=tk.LEFT, padx=(0, 4))
        setattr(self, f"port_cb_{port_id}", port_cb)

        btn_refresh = ttk.Button(serial_frame, text="↻", width=3, style="Action.TButton", command=self.refresh_ports)
        btn_refresh.pack(side=tk.LEFT)

        # TCP Frame
        tcp_frame = tk.Frame(target_container, bg=THEME["surface"])
        setattr(self, f"tcp_frame_{port_id}", tcp_frame)

        default_ip = "192.168.11.2:5000" if port_id == 1 else "192.168.11.3:5000"
        tcp_entry = ttk.Entry(tcp_frame, width=17, font=(FONT_MONO[0], 9))
        tcp_entry.insert(0, default_ip)
        tcp_entry.pack(side=tk.LEFT, padx=2)
        setattr(self, f"tcp_entry_{port_id}", tcp_entry)

        if mode_var.get() == "ETHERNET (TCP)":
            tcp_frame.pack(side=tk.LEFT)
        else:
            serial_frame.pack(side=tk.LEFT)

        # Connect Button
        btn_connect = ttk.Button(conn_bar, text="Connect", style="Primary.TButton",
                                 command=lambda: self.toggle_connection(port_id))
        btn_connect.pack(side=tk.RIGHT, padx=(6, 0))
        setattr(self, f"btn_connect_{port_id}", btn_connect)

        # Numeric KPI Readout Surface
        num_surface = tk.Frame(card, bg=THEME["surface_subtle"], padx=14, pady=12,
                               highlightthickness=1, highlightbackground=THEME["border"])
        num_surface.pack(fill=tk.X, padx=14, pady=6)

        # 3 Metrics side by side (Voltage, Current, Power)
        # Power is emphasized
        c_v = tk.Frame(num_surface, bg=THEME["surface_subtle"])
        c_v.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        tk.Label(c_v, text="VOLTAGE", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(anchor="center")
        var_v = tk.StringVar(value="--- V")
        setattr(self, f"var_v_{port_id}", var_v)
        tk.Label(c_v, textvariable=var_v, font=(FONT_MONO[0], 14, "bold"),
                 fg=THEME["accent_cyan"], bg=THEME["surface_subtle"]).pack(anchor="center", pady=2)

        # Subtle vertical separator
        tk.Frame(num_surface, bg=THEME["border"], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        c_i = tk.Frame(num_surface, bg=THEME["surface_subtle"])
        c_i.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        tk.Label(c_i, text="CURRENT", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(anchor="center")
        var_i = tk.StringVar(value="--- A")
        setattr(self, f"var_i_{port_id}", var_i)
        tk.Label(c_i, textvariable=var_i, font=(FONT_MONO[0], 14, "bold"),
                 fg=THEME["accent_emerald"], bg=THEME["surface_subtle"]).pack(anchor="center", pady=2)

        tk.Frame(num_surface, bg=THEME["border"], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        c_w = tk.Frame(num_surface, bg=THEME["surface_subtle"])
        c_w.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        tk.Label(c_w, text="ACTIVE POWER", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(anchor="center")
        var_w = tk.StringVar(value="--- W")
        setattr(self, f"var_w_{port_id}", var_w)
        tk.Label(c_w, textvariable=var_w, font=(FONT_MONO[0], 16, "bold"),
                 fg=THEME["accent_amber"], bg=THEME["surface_subtle"]).pack(anchor="center", pady=2)

        # Mode Action Buttons Bar
        cmd_bar = tk.Frame(card, bg=THEME["surface"], padx=14, pady=4)
        cmd_bar.pack(fill=tk.X)

        tk.Label(cmd_bar, text="ISW8001 Commands:", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface"]).pack(side=tk.LEFT, padx=(0, 6))

        for cmd in ["WATT", "VAR", "VOLT", "AMP", "PWF"]:
            btn = ttk.Button(cmd_bar, text=cmd, width=5, style="Action.TButton",
                             command=lambda c=cmd: self.send_cmd(port_id, c))
            btn.pack(side=tk.LEFT, padx=2)

        btn_auto = ttk.Button(cmd_bar, text="AutoRange", style="Action.TButton",
                              command=lambda: self.send_cmd(port_id, "AUTORANGE"))
        btn_auto.pack(side=tk.RIGHT, padx=2)

        # Real-Time Matplotlib Waveform Canvas
        chart_box = tk.Frame(card, bg=THEME["surface"], padx=14, pady=4)
        chart_box.pack(fill=tk.BOTH, expand=True)

        fig = Figure(figsize=(4, 2.8), dpi=100)
        fig.patch.set_facecolor(THEME["surface"])
        
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["bg"])
        ax.tick_params(colors=THEME["text_muted"], labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(THEME["border"])
        ax.grid(True, linestyle=':', alpha=0.35, color=THEME["text_muted"])
        ax.set_title(f"Channel {port_id} Power Trend (W)", fontsize=9, color=THEME["text_secondary"], pad=6)
        fig.tight_layout(pad=1.8)

        canvas = FigureCanvasTkAgg(fig, master=chart_box)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        setattr(self, f"fig_{port_id}", fig)
        setattr(self, f"ax_{port_id}", ax)
        setattr(self, f"canvas_{port_id}", canvas)
        if port_id == 1:
            self.fig1 = fig

        # Raw Stream Scrolled Text (Terminal aesthetic)
        stream_box = tk.Frame(card, bg=THEME["surface"], padx=14, pady=4)
        stream_box.pack(fill=tk.X, pady=(2, 10))

        tk.Label(stream_box, text="Raw ASCII Stream:", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface"]).pack(anchor="w", pady=(2, 2))

        log_txt = scrolledtext.ScrolledText(stream_box, height=3, font=(FONT_MONO[0], 8),
                                            bg=THEME["surface_subtle"], fg=THEME["text_primary"],
                                            insertbackground=THEME["text_primary"],
                                            highlightthickness=1, highlightbackground=THEME["border"],
                                            bd=0)
        log_txt.pack(fill=tk.X)
        setattr(self, f"log_txt_{port_id}", log_txt)

        return card

    def _build_bottom_toolbar(self):
        bottom_card = ModernCard(self.root, bg=THEME["surface_subtle"])
        bottom_card.pack(fill=tk.X, padx=16, pady=(0, 14))

        bar = tk.Frame(bottom_card, bg=THEME["surface_subtle"], padx=14, pady=8)
        bar.pack(fill=tk.X)

        # Logging controls
        self.btn_log = ttk.Button(bar, text="▶ Start CSV Recording", style="Action.TButton",
                                  command=self.toggle_logging)
        self.btn_log.pack(side=tk.LEFT, padx=(0, 6))

        btn_export = ttk.Button(bar, text="💾 Snapshot CSV", style="Action.TButton",
                                command=self.export_snapshot_csv)
        btn_export.pack(side=tk.LEFT, padx=6)

        # Logging Status
        tk.Label(bar, text="CSV STATUS:", font=(FONT_DISPLAY[0], 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(side=tk.LEFT, padx=(14, 4))

        tk.Label(bar, textvariable=self.log_status_var, font=(FONT_DISPLAY[0], 9),
                 fg=THEME["text_primary"], bg=THEME["surface_subtle"]).pack(side=tk.LEFT)

        tk.Label(bar, text="|", font=(FONT_DISPLAY[0], 10),
                 fg=THEME["border"], bg=THEME["surface_subtle"]).pack(side=tk.LEFT, padx=10)

        tk.Label(bar, textvariable=self.log_records_var, font=(FONT_MONO[0], 9),
                 fg=THEME["accent_emerald"], bg=THEME["surface_subtle"]).pack(side=tk.LEFT)

        # Right-aligned utility info
        tk.Label(bar, text="Rate: ~470ms/sample", font=(FONT_DISPLAY[0], 8),
                 fg=THEME["text_muted"], bg=THEME["surface_subtle"]).pack(side=tk.RIGHT)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        simulators = ["SIMULATOR-P1", "SIMULATOR-P2"]
        all_ports = ports + simulators
        
        for pid in [1, 2]:
            cb = getattr(self, f"port_cb_{pid}", None)
            if cb:
                current_val = cb.get()
                cb['values'] = all_ports
                if current_val in all_ports:
                    cb.set(current_val)
                elif all_ports:
                    default_idx = len(all_ports) - (3 - pid)
                    if 0 <= default_idx < len(all_ports):
                        cb.current(default_idx)

    def on_mode_change(self, port_id):
        mode = getattr(self, f"conn_mode_{port_id}").get()
        serial_frame = getattr(self, f"serial_frame_{port_id}")
        tcp_frame = getattr(self, f"tcp_frame_{port_id}")
        if mode == "ETHERNET (TCP)":
            serial_frame.pack_forget()
            tcp_frame.pack(side=tk.LEFT)
        else:
            tcp_frame.pack_forget()
            serial_frame.pack(side=tk.LEFT)

    def send_cmd(self, port_id, cmd):
        handler = self.handlers.get(port_id)
        if handler and handler.is_connected:
            handler.send_command(cmd)
        else:
            messagebox.showwarning("Not Connected", f"Channel {port_id} is not connected.")

    def toggle_connection(self, port_id):
        btn = getattr(self, f"btn_connect_{port_id}")
        badge_dot = getattr(self, f"badge_dot_{port_id}")
        status_text = getattr(self, f"status_text_{port_id}")
        mode = getattr(self, f"conn_mode_{port_id}").get()
        
        if btn["text"] == "Connect":
            if mode == "ETHERNET (TCP)":
                target = getattr(self, f"tcp_entry_{port_id}").get().strip()
                if not target:
                    messagebox.showerror("Error", "Please enter WIZ750SR IP:Port (e.g. 192.168.11.2:5000)")
                    return
                handler = ConnectionHandler("TCP", target)
            else:
                target = getattr(self, f"port_cb_{port_id}").get().strip()
                if not target:
                    messagebox.showerror("Error", "Please select a COM port")
                    return
                handler = ConnectionHandler("SERIAL", target)

            handler.callback = lambda data, pid=port_id: self.root.after(0, self.process_data, pid, data)
            
            success, msg = handler.connect()
            if success:
                self.handlers[port_id] = handler
                btn.config(text="Disconnect")
                badge_dot.config(fg=THEME["badge_connected"])
                status_text.config(text=f"CONNECTED ({target})", fg=THEME["accent_emerald"])
                self.data_history[port_id].clear()
                self.latest_power[port_id] = 0.0
                self.update_efficiency()
            else:
                messagebox.showerror("Connection Error", msg)
        else:
            handler = self.handlers.get(port_id)
            if handler:
                handler.disconnect()
                self.handlers[port_id] = None
            btn.config(text="Connect")
            badge_dot.config(fg=THEME["text_muted"])
            status_text.config(text="DISCONNECTED", fg=THEME["text_muted"])
            
            getattr(self, f"var_v_{port_id}").set("--- V")
            getattr(self, f"var_i_{port_id}").set("--- A")
            getattr(self, f"var_w_{port_id}").set("--- W")
            self.data_history[port_id].clear()
            self.latest_power[port_id] = 0.0
            
            ax = getattr(self, f"ax_{port_id}")
            ax.clear()
            ax.set_facecolor(THEME["bg"])
            ax.tick_params(colors=THEME["text_muted"], labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(THEME["border"])
            ax.grid(True, linestyle=':', alpha=0.35, color=THEME["text_muted"])
            ax.set_title(f"Channel {port_id} Power Trend (W)", fontsize=9, color=THEME["text_secondary"], pad=6)
            getattr(self, f"canvas_{port_id}").draw()
            self.update_efficiency()

    def process_data(self, port_id, data):
        log_txt = getattr(self, f"log_txt_{port_id}")
        log_txt.insert(tk.END, data + "\n")
        log_txt.see(tk.END)
        if float(log_txt.index('end-1c').split('.')[0]) > 25:
            log_txt.delete('1.0', '2.0')

        v_match = re.search(r'U\d=([+-]?[\d\.]+E[+-]?\d+)', data)
        i_match = re.search(r'I\d=([+-]?[\d\.]+E[+-]?\d+)', data)
        w_match = re.search(r'W=([+-]?[\d\.]+E[+-]?\d+)', data)
        pf_match = re.search(r'PF=([+-]?[\d\.]+E[+-]?\d+)', data)
        var_match = re.search(r'VAR=([+-]?[\d\.]+E[+-]?\d+)', data)

        if v_match:
            try:
                val = float(v_match.group(1))
                self.latest_metrics[port_id]["v"] = val
                getattr(self, f"var_v_{port_id}").set(f"{val:.2f} V")
            except Exception: pass
            
        if i_match:
            try:
                val = float(i_match.group(1))
                self.latest_metrics[port_id]["i"] = val
                getattr(self, f"var_i_{port_id}").set(f"{val:.3f} A")
            except Exception: pass
            
        if w_match:
            try:
                val = float(w_match.group(1))
                self.latest_metrics[port_id]["p"] = val
                getattr(self, f"var_w_{port_id}").set(f"{val:.2f} W")
                self.data_history[port_id].append(val)
                self.latest_power[port_id] = val
                self.update_efficiency()
                self._record_csv_row()
            except Exception: pass
        elif var_match:
            try:
                val = float(var_match.group(1))
                self.latest_metrics[port_id]["var"] = val
                getattr(self, f"var_w_{port_id}").set(f"{val:.2f} VAR")
                self.data_history[port_id].append(val)
            except Exception: pass
        elif pf_match:
            try:
                val = float(pf_match.group(1))
                self.latest_metrics[port_id]["pf"] = val
                getattr(self, f"var_w_{port_id}").set(f"{val:.3f} PF")
                self.data_history[port_id].append(val)
            except Exception: pass
        elif "overflow" in data.lower():
            getattr(self, f"var_w_{port_id}").set("OVERFLOW")

    def update_efficiency(self):
        p1 = self.latest_power.get(1, 0.0)
        p2 = self.latest_power.get(2, 0.0)
        
        if p1 > 0 and p2 >= 0:
            eff = (p2 / p1) * 100.0
            diff = p1 - p2
            self.lbl_efficiency.config(text=f"{eff:.2f} %")
            self.lbl_delta.config(text=f"{diff:.2f} W")
            self.lbl_status_summary.config(
                text=f"CH1 Input: {p1:.2f} W  ➔  CH2 Output: {p2:.2f} W  |  Loss: {diff:.2f} W"
            )
        else:
            self.lbl_efficiency.config(text="--- %")
            self.lbl_delta.config(text="--- W")
            self.lbl_status_summary.config(
                text="Waiting for active measurements on both channels..."
            )

    def toggle_logging(self):
        if not self.is_logging:
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"power_profiler_{timestamp_str}.csv"
            filepath = filedialog.asksaveasfilename(
                title="Select CSV Log File",
                initialfile=default_name,
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
            )
            if not filepath:
                return
            try:
                self.log_file = open(filepath, "w", newline="", encoding="utf-8")
                self.csv_writer = csv.writer(self.log_file)
                self.csv_writer.writerow([
                    "timestamp_iso", "timestamp_epoch",
                    "ch1_volts", "ch1_amps", "ch1_watts", "ch1_pf",
                    "ch2_volts", "ch2_amps", "ch2_watts", "ch2_pf",
                    "ratio_pct", "delta_watts"
                ])
                self.log_file.flush()
                self.is_logging = True
                self.log_records_count = 0
                self.btn_log.config(text="⏹ Stop CSV Recording")
                filename_only = filepath.split('/')[-1].split('\\')[-1]
                self.log_status_var.set(f"Logging: {filename_only}")
                self.log_records_var.set("0 rows")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start CSV log: {e}")
        else:
            self.is_logging = False
            if self.log_file:
                try:
                    self.log_file.close()
                except Exception:
                    pass
                self.log_file = None
            self.btn_log.config(text="▶ Start CSV Recording")
            self.log_status_var.set("Idle (Stopped)")

    def _record_csv_row(self):
        if not self.is_logging or not self.csv_writer:
            return
        now = time.time()
        now_iso = datetime.datetime.now().isoformat()
        m1 = self.latest_metrics[1]
        m2 = self.latest_metrics[2]
        p1 = m1["p"] or 0.0
        p2 = m2["p"] or 0.0
        eff = round((p2 / p1) * 100.0, 3) if p1 > 0 else ""
        diff = round(p1 - p2, 3) if p1 > 0 else ""

        try:
            self.csv_writer.writerow([
                now_iso, f"{now:.3f}",
                m1["v"], m1["i"], m1["p"], m1["pf"],
                m2["v"], m2["i"], m2["p"], m2["pf"],
                eff, diff
            ])
            self.log_records_count += 1
            if self.log_records_count % 5 == 0:
                self.log_file.flush()
                self.log_records_var.set(f"{self.log_records_count} rows")
        except Exception:
            pass

    def export_snapshot_csv(self):
        filepath = filedialog.asksaveasfilename(
            title="Save Snapshot to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return
        try:
            now_iso = datetime.datetime.now().isoformat()
            m1 = self.latest_metrics[1]
            m2 = self.latest_metrics[2]
            p1 = m1["p"] or 0.0
            p2 = m2["p"] or 0.0
            eff = round((p2 / p1) * 100.0, 3) if p1 > 0 else ""
            diff = round(p1 - p2, 3) if p1 > 0 else ""

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["metric", "value", "unit"])
                w.writerow(["timestamp", now_iso, "ISO-8601"])
                w.writerow(["ch1_voltage", m1["v"], "V"])
                w.writerow(["ch1_current", m1["i"], "A"])
                w.writerow(["ch1_power", m1["p"], "W"])
                w.writerow(["ch1_pf", m1["pf"], ""])
                w.writerow(["ch2_voltage", m2["v"], "V"])
                w.writerow(["ch2_current", m2["i"], "A"])
                w.writerow(["ch2_power", m2["p"], "W"])
                w.writerow(["ch2_pf", m2["pf"], ""])
                w.writerow(["ratio_pct", eff, "%"])
                w.writerow(["delta_power", diff, "W"])
            messagebox.showinfo("Export Complete", f"Snapshot exported to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export snapshot: {e}")

    def update_charts(self, frame):
        for port_id in [1, 2]:
            if not self.handlers[port_id]:
                continue
                
            ax = getattr(self, f"ax_{port_id}")
            canvas = getattr(self, f"canvas_{port_id}")
            data = list(self.data_history[port_id])
            
            ax.clear()
            ax.set_facecolor(THEME["bg"])
            ax.tick_params(colors=THEME["text_muted"], labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(THEME["border"])
            ax.grid(True, linestyle=':', alpha=0.35, color=THEME["text_muted"])
            ax.set_title(f"Channel {port_id} Power Trend (W)", fontsize=9, color=THEME["text_secondary"], pad=6)
            
            if data:
                line_color = THEME["accent_cyan"] if port_id == 1 else THEME["accent_amber"]
                ax.plot(data, color=line_color, linewidth=1.8)
                min_y, max_y = min(data), max(data)
                pad = max(0.2, (max_y - min_y) * 0.12)
                ax.set_ylim(min_y - pad, max_y + pad)
            
            canvas.draw()

    def on_closing(self):
        for pid, handler in self.handlers.items():
            if handler:
                handler.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = DualPortGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
