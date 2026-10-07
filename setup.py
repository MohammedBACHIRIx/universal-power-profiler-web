#!/usr/bin/env python3
"""
Cross-Platform Installer & Setup Script for Universal Power Profiler
Works on Windows, Linux, and macOS.
"""

import sys
import subprocess
import os
import shutil
import platform

REQUIREMENTS = [
    "pyserial>=3.5",
    "websockets>=12.0",
    "matplotlib>=3.8.0",
    "numpy>=1.26.0"
]

def print_header():
    print("=" * 70)
    print("   UNIVERSAL POWER PROFILER & DUAL WATTMETER — SETUP & INSTALLER")
    print("   Compatible with ISW8001 Serial COM, Ethernet TCP & Web IDE")
    print("=" * 70)

def check_python():
    print(f"[*] Detected Python: {sys.version.split()[0]} on {platform.system()}")
    if sys.version_info < (3, 9):
        print("[!] Warning: Python 3.9+ is recommended.")

def install_requirements():
    print("\n[*] Installing dependencies...")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + REQUIREMENTS
    try:
        subprocess.check_call(cmd)
        print("[OK] All Python dependencies installed successfully!")
    except subprocess.CalledProcessError:
        print("[!] Attempting installation with --user flag...")
        cmd_user = [sys.executable, "-m", "pip", "install", "--user", "--upgrade"] + REQUIREMENTS
        subprocess.check_call(cmd_user)
        print("[OK] Dependencies installed successfully via user site-packages!")

def create_windows_shortcuts():
    if platform.system() != "Windows":
        return
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        
        ps_cmd = f"""
        $ws = New-Object -ComObject WScript.Shell
        $s1 = $ws.CreateShortcut('{desktop}\\PowerProfilerWeb.lnk')
        $s1.TargetPath = '{current_dir}\\Launch-Web-IDE.bat'
        $s1.WorkingDirectory = '{current_dir}'
        $s1.Description = 'Universal Power Profiler Web IDE'
        $s1.Save()

        $s2 = $ws.CreateShortcut('{desktop}\\PowerProfilerDesktop.lnk')
        $s2.TargetPath = '{current_dir}\\Launch-Desktop-GUI.bat'
        $s2.WorkingDirectory = '{current_dir}'
        $s2.Description = 'Universal Power Profiler Desktop'
        $s2.Save()
        """
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
        print(f"[OK] Created Desktop shortcuts in: {desktop}")
    except Exception as e:
        print(f"[!] Note: Could not create desktop shortcuts automatically ({e})")

def main():
    print_header()
    check_python()
    install_requirements()
    create_windows_shortcuts()
    print("\n" + "=" * 70)
    print("Setup completed successfully!")
    print("To launch Web IDE:        python web_server.py")
    print("To launch Desktop GUI:    python dual_wattmeter_gui.py")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
