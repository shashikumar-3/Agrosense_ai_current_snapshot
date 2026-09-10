@echo off
REM ===================================================================
REM  start.bat  -  one-command launcher for AgroSense AI
REM
REM  Starts the Flask backend and the Vite frontend, each in its own
REM  window that stays open (cmd /k) so a crash leaves its error on
REM  screen. Waits for both to answer, then opens the app in your
REM  default browser. This launcher window also stays open until YOU
REM  close it -- closing it does NOT stop the two service windows.
REM
REM  Ports (both auto-detected free, every run):
REM    Backend  - backend\.env pins PORT=..., and Flask reloads that
REM               file with override=True, so an env var alone can't
REM               override it (the file always wins). So: if the
REM               pinned port is busy, this script REWRITES that one
REM               "PORT=" line in backend\.env (and VITE_API_BASE in
REM               the root .env, so the frontend still finds it) to
REM               the next free port, then launches. Nothing else in
REM               either file is touched. Undo by editing PORT= back
REM               by hand if you ever want it pinned again.
REM    Frontend - vite.config.ts pins port 8080 but does NOT set
REM               strictPort, so Vite itself walks 8080, 8081, 8082...
REM               until one is free. This script watches that range
REM               and opens the browser at whichever one comes up.
REM ===================================================================

setlocal EnableDelayedExpansion
title AgroSense AI - Launcher

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "FRONTEND_PORT_BASE=8080"
set "FRONTEND_PORT_SPAN=10"

echo.
echo  ============================================
echo   AgroSense AI - starting backend + frontend
echo  ============================================
echo.

REM ---- prerequisite: executables ---------------------------------------
where npm >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] "npm" was not found on your PATH.
    echo          Install Node.js 18+, open a NEW terminal, and try again.
    goto :fail
)
echo  [ok] found npm

if not exist "%VENV_PY%" (
    echo  [ERROR] Backend virtual environment is missing: %VENV_PY%
    echo          Create it first:
    echo            cd backend
    echo            python -m venv .venv
    echo            .venv\Scripts\pip install -r requirements.txt
    goto :fail
)
echo  [ok] found backend\.venv

REM ---- prerequisite: directories ---------------------------------------
if not exist "%BACKEND_DIR%" (
    echo  [ERROR] Missing directory: %BACKEND_DIR%
    goto :fail
)
echo  [ok] project directories present

REM ---- prerequisite: env files -------------------------------------------
if not exist "%BACKEND_DIR%\.env" (
    echo.
    echo  [ERROR] backend\.env.example exists but backend\.env does not.
    echo          Run:   copy backend\.env.example backend\.env
    echo          Fill in the values, then run this script again.
    goto :fail
)
echo  [ok] backend\.env present

REM ---- prerequisite: node_modules -----------------------------------------
if not exist "%ROOT%node_modules" (
    echo.
    echo  [info] node_modules not found - running "npm install" first.
    echo         This can take a few minutes on the first run.
    pushd "%ROOT%"
    call npm install
    popd
    if errorlevel 1 (
        echo  [ERROR] npm install failed. See the output above.
        goto :fail
    )
)
echo  [ok] frontend dependencies installed

REM ---- resolve backend port: read backend\.env, auto-pick a free one -----
set "PINNED_PORT=5000"
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "PORT=" "%BACKEND_DIR%\.env"`) do set "PINNED_PORT=%%B"
if "!PINNED_PORT!"=="" set "PINNED_PORT=5000"

call :find_free_port !PINNED_PORT! BACKEND_PORT
if errorlevel 1 goto :fail

if not "!BACKEND_PORT!"=="!PINNED_PORT!" (
    echo  [info] backend port !PINNED_PORT! busy - switching to !BACKEND_PORT!
    echo         updating backend\.env and root .env to match ...
    powershell -NoProfile -Command ^
        "(Get-Content -Raw '%BACKEND_DIR%\.env') -replace '(?m)^PORT=.*$', 'PORT=!BACKEND_PORT!' | Set-Content -NoNewline '%BACKEND_DIR%\.env';" ^
        "if (Test-Path '%ROOT%.env') { (Get-Content -Raw '%ROOT%.env') -replace '(?m)^VITE_API_BASE=.*$', 'VITE_API_BASE=http://127.0.0.1:!BACKEND_PORT!' | Set-Content -NoNewline '%ROOT%.env' }"
    if errorlevel 1 (
        echo  [ERROR] Could not update .env files with the new port.
        goto :fail
    )
) else (
    echo  [ok] backend port !BACKEND_PORT! is free
)

REM ---- launch backend ------------------------------------------------------
start "AgroSense Backend  (port !BACKEND_PORT!)" cmd /k "cd /d "%BACKEND_DIR%" && echo Running: .venv\Scripts\python.exe app.py && echo. && "%VENV_PY%" app.py"

call :wait_for_port !BACKEND_PORT! 30 "backend"

REM ---- launch frontend -------------------------------------------------------
start "AgroSense Frontend  (port ~!FRONTEND_PORT_BASE!)" cmd /k "cd /d "%ROOT%" && echo Running: npm run dev && echo. && npm run dev"

REM Vite walks the port upward from 8080 if busy (no strictPort set) - watch
REM the whole span and use whichever one comes up first.
set "FRONTEND_PORT="
call :wait_for_port_range !FRONTEND_PORT_BASE! !FRONTEND_PORT_SPAN! 60 FRONTEND_PORT

if "!FRONTEND_PORT!"=="" (
    echo.
    echo  [warn] No port in !FRONTEND_PORT_BASE!-!FRONTEND_PORT_BASE!+!FRONTEND_PORT_SPAN! answered yet.
    echo         Check the frontend window for an error. Defaulting the
    echo         browser to http://localhost:!FRONTEND_PORT_BASE! anyway.
    set "FRONTEND_PORT=!FRONTEND_PORT_BASE!"
)

set "APP_URL=http://localhost:!FRONTEND_PORT!"

echo.
echo  ============================================
echo   Running.
echo.
echo     APP      -^>  !APP_URL!
echo     BACKEND  -^>  http://127.0.0.1:!BACKEND_PORT!
echo.
echo   Opening !APP_URL! in your browser.
echo   If nothing opens, no default browser is registered --
echo   copy the URL above instead.
echo  ============================================
echo.

start "" "!APP_URL!"

echo  Backend and frontend run in their own windows. Close those windows
echo  (or Ctrl+C inside them) to stop them. Closing THIS window does not
echo  stop them.
echo  Port stuck after a crash?  free_ports.bat
echo.
echo  This window stays open until you close it.
pause
endlocal
exit /b 0


REM ===================================================================
REM  DO NOT EDIT BELOW
REM ===================================================================

REM  :wait_for_port <port> <timeout_seconds> <label>
:wait_for_port
setlocal EnableDelayedExpansion
set /a "waited=0"
set /a "cap=%~2"
echo  waiting for %~3 on port %~1 ...
:_wait1
netstat -ano -p TCP | findstr /r /c:":%~1 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  [ok] %~3 is answering on port %~1
    endlocal
    exit /b 0
)
ping -n 2 127.0.0.1 >nul
set /a "waited+=1"
if !waited! LSS !cap! goto :_wait1
echo  [warn] %~3 did not answer on port %~1 within !cap!s.
echo         It may still be starting. Check its window for an error.
endlocal
exit /b 0


REM  :find_free_port <base_port> <out_var_name>
REM  Scans upward from base_port for a port with no LISTENING socket.
:find_free_port
setlocal EnableDelayedExpansion
set /a "port=%~1"
set /a "limit=%~1 + 50"
:_probe
if !port! GEQ !limit! (
    echo  [ERROR] No free port between %~1 and !limit!.
    endlocal
    exit /b 1
)
netstat -ano -p TCP | findstr /r /c:":!port! .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    set /a "port+=1"
    goto :_probe
)
endlocal & set "%~2=%port%"
exit /b 0


REM  :wait_for_port_range <base_port> <span> <timeout_seconds> <out_var_name>
REM  Polls base_port..base_port+span every ~1s until one of them answers,
REM  or the timeout expires. Used for Vite, which walks the port upward
REM  itself when the base port is busy (no strictPort configured).
:wait_for_port_range
setlocal EnableDelayedExpansion
set /a "base=%~1"
set /a "span=%~2"
set /a "cap=%~3"
set /a "waited=0"
echo  waiting for frontend on port !base!-!base!+!span! ...
:_wait2
set /a "p=base"
set /a "top=base+span"
:_scan
if !p! GTR !top! goto :_next
netstat -ano -p TCP | findstr /r /c:":!p! .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  [ok] frontend is answering on port !p!
    endlocal & set "%~4=%p%"
    exit /b 0
)
set /a "p+=1"
goto :_scan
:_next
ping -n 2 127.0.0.1 >nul
set /a "waited+=1"
if !waited! LSS !cap! goto :_wait2
endlocal & set "%~4="
exit /b 0


:fail
echo.
echo  Startup aborted. Nothing was launched.
echo.
pause
endlocal
exit /b 1
