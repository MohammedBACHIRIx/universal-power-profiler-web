@echo off
title Power Profiler Web IDE (Arduino Cloud Style)
echo ==============================================================================
echo    Starting Universal Power Profiler Web IDE
echo    Opening browser at http://localhost:8000 ...
echo ==============================================================================
start http://localhost:8000
python web_server.py
pause
