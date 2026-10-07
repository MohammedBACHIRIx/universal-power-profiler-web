"""
Universal Power Profiler — Production Cloud & Heroku Server
Serves static assets and provides a unified WebSocket endpoint on a single PORT (required by Heroku / cloud).
"""

import os
import json
import socket
import threading
import time
import re
import collections
import random
from typing import Set

import serial
import serial.tools.list_ports

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="Power Profiler Web IDE")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# --- Mock Serial Simulator ---
class MockSerial:
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.is_open = True
        self.in_waiting = 0
        self.mode = "WATT"
        self.auto = False
        self._buffer = b""
        self._stop = False
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
                if random.random() > 0.75:
                    b_line = b_line[:5] + b'\x11' + b_line[5:10] + b'\x13' + b_line[10:]

                self._buffer += b_line
                self.in_waiting = len(self._buffer)
            time.sleep(0.47)

    def close(self):
        self.is_open = False
        self._stop = True


# --- Connection Handler (Serial COM, Mock Simulator, or TCP WIZ750SR) ---
class ConnectionHandler:
    def __init__(self, conn_type, target, baudrate=9600):
        self.conn_type = conn_type
        self.target = target
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
                            raise ConnectionResetError("Connection closed")
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


# --- Global State & WebSocket Connection Manager ---
class InstrumentHub:
    def __init__(self):
        self.handlers = {1: None, 2: None}
        self.active_websockets: Set[WebSocket] = set()
        self.loop = None

    def get_port_list(self):
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        simulators = ["SIMULATOR-P1", "SIMULATOR-P2"]
        return ports + simulators

    async def broadcast(self, payload: dict):
        text = json.dumps(payload)
        disconnected = set()
        for ws in self.active_websockets:
            try:
                await ws.send_text(text)
            except Exception:
                disconnected.add(ws)
        self.active_websockets -= disconnected

    def on_instrument_telemetry(self, port_id, raw):
        if self.loop and self.loop.is_running():
            import asyncio
            asyncio.run_coroutine_threadsafe(
                self.broadcast({"type": "data", "port_id": port_id, "data": raw}),
                self.loop
            )

hub = InstrumentHub()


@app.on_event("startup")
async def startup_event():
    import asyncio
    hub.loop = asyncio.get_running_loop()


@app.get("/")
async def root():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    hub.active_websockets.add(websocket)
    try:
        # Initial ports & state
        await websocket.send_text(json.dumps({
            "type": "ports",
            "ports": hub.get_port_list()
        }))

        for pid in [1, 2]:
            h = hub.handlers[pid]
            await websocket.send_text(json.dumps({
                "type": "status",
                "port_id": pid,
                "connected": h.is_connected if h else False,
                "target": h.target if h else ""
            }))

        while True:
            text = await websocket.receive_text()
            data = json.loads(text)
            action = data.get("action")
            pid = data.get("port_id")

            if action == "refresh_ports":
                await hub.broadcast({"type": "ports", "ports": hub.get_port_list()})

            elif action == "connect":
                conn_type = data.get("conn_type", "SERIAL")
                target = data.get("target", "")

                if hub.handlers[pid]:
                    hub.handlers[pid].disconnect()

                handler = ConnectionHandler(conn_type, target)
                handler.callback = lambda raw, p=pid: hub.on_instrument_telemetry(p, raw)
                success, msg = handler.connect()

                if success:
                    hub.handlers[pid] = handler
                    await hub.broadcast({
                        "type": "status",
                        "port_id": pid,
                        "connected": True,
                        "target": target
                    })
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Connection failed: {msg}"
                    }))

            elif action == "disconnect":
                if hub.handlers[pid]:
                    hub.handlers[pid].disconnect()
                    hub.handlers[pid] = None
                await hub.broadcast({
                    "type": "status",
                    "port_id": pid,
                    "connected": False,
                    "target": ""
                })

            elif action == "command":
                cmd = data.get("cmd", "")
                if hub.handlers[pid] and hub.handlers[pid].is_connected:
                    hub.handlers[pid].send_command(cmd)

    except WebSocketDisconnect:
        hub.active_websockets.discard(websocket)
    except Exception:
        hub.active_websockets.discard(websocket)


# Mount static files (if extra css/js are in web dir)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
