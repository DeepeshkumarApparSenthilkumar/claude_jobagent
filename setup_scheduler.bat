@echo off
REM Job Agent - Windows Task Scheduler Setup
REM Runs main.py every day at 8:00 AM, no popup window

SET TASK_NAME=JobAgentDaily
SET PYTHON_PATH=C:\Users\dk505\anaconda3\python.exe
SET SCRIPT_PATH=C:\Users\dk505\job-agent\main.py
SET WORK_DIR=C:\Users\dk505\job-agent
SET LOG_PATH=C:\Users\dk505\job-agent\logs\scheduler.log

REM Delete existing task if it exists
schtasks /Delete /TN "%TASK_NAME%" /F 2>nul

REM Create the scheduled task
schtasks /Create ^
  /TN "%TASK_NAME%" ^
  /TR "cmd /c cd /d \"%WORK_DIR%\" && \"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" >> \"%LOG_PATH%\" 2>&1" ^
  /SC DAILY ^
  /ST 08:00 ^
  /RL HIGHEST ^
  /F ^
  /RU "%USERNAME%"

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" created successfully.
    echo      Runs every day at 8:00 AM
    echo      Log: %LOG_PATH%
    echo.
    echo To verify: schtasks /Query /TN "%TASK_NAME%" /FO LIST
    echo To run now: schtasks /Run /TN "%TASK_NAME%"
    echo To delete:  schtasks /Delete /TN "%TASK_NAME%" /F
) ELSE (
    echo.
    echo [ERROR] Failed to create task. Try running as Administrator.
)

pause
