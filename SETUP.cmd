@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "from eyedesk.models import ensure_models; ensure_models()"
if errorlevel 1 goto failed
echo Setup complete. Open START.cmd.
pause
exit /b 0
:failed
echo Setup failed. Copy the error shown above.
pause
exit /b 1
