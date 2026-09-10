@echo off
REM ===================================================================
REM  free_ports.bat  -  reclaims the ports start.bat uses
REM
REM    free_ports.bat            frees backend\.env's PORT + 8080, asks first
REM    free_ports.bat 8000 5173  frees those ports instead
REM    free_ports.bat /y         frees the default ports without asking
REM
REM  Companion to start.bat, and the difference matters: start.bat
REM  refuses to run if the backend port is busy (see the note in that
REM  file about why it can't just pick another one). This script is
REM  how you get that port back after a crash left an orphan on it.
REM
REM  This terminates processes. It shows you what it found and asks
REM  before doing it, and it never touches PID 0 or PID 4 (System).
REM ===================================================================

setlocal EnableDelayedExpansion
title Free AgroSense AI ports

set "ROOT=%~dp0"

REM ------------------------- CONFIG ----------------------------------
set "BACKEND_PORT=5000"
if exist "%ROOT%backend\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "PORT=" "%ROOT%backend\.env"`) do set "BACKEND_PORT=%%B"
)
if "!BACKEND_PORT!"=="" set "BACKEND_PORT=5000"
set "PORTS=!BACKEND_PORT! 8080"
REM -------------------------------------------------------------------

set "ASSUME_YES="
set "ARGPORTS="
for %%A in (%*) do (
    if /i "%%A"=="/y" (set "ASSUME_YES=1") else (set "ARGPORTS=!ARGPORTS! %%A")
)
if not "!ARGPORTS!"=="" for /f "tokens=*" %%T in ("!ARGPORTS!") do set "PORTS=%%T"

echo.
echo  ============================================
echo   Freeing ports: !PORTS!
echo  ============================================
echo.

REM ---- pass 1: find what is holding each port -------------------------
set "KILL_LIST="
set "FOUND="

for %%P in (%PORTS%) do (
    set "HIT="
    for /f "tokens=5" %%I in ('netstat -ano -p TCP ^| findstr /r /c:":%%P .*LISTENING" 2^>nul') do (
        set "PID=%%I"

        if "!PID!"=="0" (
            echo   port %%P    PID 0     System Idle  -- skipped, cannot be ended
        ) else if "!PID!"=="4" (
            echo   port %%P    PID 4     System       -- skipped, cannot be ended
        ) else (
            set "IMG=unknown"
            for /f "tokens=1 delims=," %%N in ('tasklist /FI "PID eq !PID!" /NH /FO CSV 2^>nul') do (
                set "IMG=%%~N"
            )
            echo   port %%P    PID !PID!    !IMG!
            set "HIT=1"
            set "FOUND=1"
            echo !KILL_LIST! | findstr /c:" !PID! " >nul 2>&1
            if errorlevel 1 set "KILL_LIST=!KILL_LIST! !PID! "
        )
    )
    if not defined HIT echo   port %%P    free
)

if not defined FOUND (
    echo.
    echo  Nothing to free. All listed ports are already available.
    goto :done
)

REM ---- confirm ---------------------------------------------------------
echo.
if defined ASSUME_YES (
    echo  /y given - not asking.
) else (
    set "ANS="
    set /p "ANS=  Force-end the processes listed above? [y/N] "
    if /i not "!ANS!"=="y" (
        echo.
        echo  Cancelled. Nothing was ended.
        goto :done
    )
)

REM ---- pass 2: kill -----------------------------------------------------
echo.
for %%K in (!KILL_LIST!) do (
    taskkill /F /PID %%K >nul 2>&1
    if errorlevel 1 (
        echo  [FAILED] PID %%K would not end.
        echo           Usually: it belongs to another user, it is a service,
        echo           or this terminal needs to run as Administrator.
    ) else (
        echo  [ok] ended PID %%K
    )
)

REM ---- verify ------------------------------------------------------------
echo.
echo  --- rechecking ---
set "STILL="
for %%P in (%PORTS%) do (
    netstat -ano -p TCP | findstr /r /c:":%%P .*LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo   port %%P    free
    ) else (
        echo   port %%P    STILL HELD
        set "STILL=1"
    )
)

if defined STILL (
    echo.
    echo  [warn] At least one port is still held. It may be a service that
    echo         restarted itself, or a process this account cannot end.
    echo         Identify it with:  netstat -ano ^| findstr :PORT
)

:done
echo.
pause
endlocal
