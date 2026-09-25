@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Server of Dreams launcher.
rem The admin GUI owns the API server and headless mitmdump child processes.

set "PROJECT_DIR=D:\server-of-dreams\server-of-dreams-main"
set "ADB_DIR=D:\server-of-dreams\platform-tools-latest-windows\platform-tools"
set "BLUESTACKS_EXE=C:\Program Files\BlueStacks_nxt\HD-Player.exe"
set "BLUESTACKS_SERIAL=127.0.0.1:5555"
set "PROXY_PORT=8080"
set "PYTHONW=%PROJECT_DIR%\venv\Scripts\pythonw.exe"
set "ADB=%ADB_DIR%\adb.exe"

if not exist "%PYTHONW%" (
    echo ERROR: Python virtual environment not found: %PYTHONW%
    echo Run: venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
if not exist "%ADB%" (
    echo ERROR: ADB not found: %ADB%
    exit /b 1
)

echo Detecting the PC address used by the emulator...
set "MYIP="
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command ^
  "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'VMware|vEthernet|Loopback|Bluetooth' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' }).IPAddress | Select-Object -First 1"`) do set "MYIP=%%a"
if not defined MYIP (
    echo ERROR: Could not determine a reachable PC IPv4 address.
    echo Check ipconfig and network adapter settings, then run this launcher again.
    exit /b 1
)
echo PC address: %MYIP%

if exist "%BLUESTACKS_EXE%" (
    echo Starting BlueStacks...
    start "" "%BLUESTACKS_EXE%"
) else (
    echo WARNING: BlueStacks executable not found; continuing with the GUI.
)

echo Waiting for emulator ADB: %BLUESTACKS_SERIAL%
set /a TRIES=0
:wait_for_adb
"%ADB%" connect %BLUESTACKS_SERIAL% >nul 2>&1
"%ADB%" -s %BLUESTACKS_SERIAL% get-state >nul 2>&1
if not errorlevel 1 goto :adb_ready
set /a TRIES+=1
if %TRIES% GEQ 30 (
    echo ERROR: Emulator did not become available through ADB.
    echo Check the emulator and serial, then run this launcher again.
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto :wait_for_adb

:adb_ready
echo Setting emulator proxy to %MYIP%:%PROXY_PORT%...
"%ADB%" -s %BLUESTACKS_SERIAL% shell settings put global http_proxy %MYIP%:%PROXY_PORT%
if errorlevel 1 (
    echo ERROR: Could not set the emulator proxy.
    exit /b 1
)

echo Starting the admin GUI.
echo The GUI manages the API server and headless mitmdump without console windows.
start "Server of Dreams Admin" /b "%PYTHONW%" -m gui.main
echo Launcher complete. Use the GUI tray menu to stop child processes.
endlocal
exit /b 0
