@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
set "LAUNCHER=%AUTOCATALYST_PYTHON%"

if not defined LAUNCHER (
  for %%P in (py python python3) do (
    where %%P >nul 2>nul
    if not errorlevel 1 (
      set "LAUNCHER=%%P"
      goto :launcher_found
    )
  )
)

:launcher_found
if not defined LAUNCHER (
  echo AutoCatalyst: could not find py, python, or python3 in PATH. 1>&2
  exit /b 1
)

if /I "%LAUNCHER%"=="py" (
  "%LAUNCHER%" -3 "%SCRIPT_DIR%bootstrap.py" %*
) else (
  "%LAUNCHER%" "%SCRIPT_DIR%bootstrap.py" %*
)
