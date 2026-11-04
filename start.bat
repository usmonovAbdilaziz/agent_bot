@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title Qadam - Bot va Mini App
pushd "%~dp0"
if not exist "run.py" goto missing
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1"
set "BOT_EXIT=%ERRORLEVEL%"
echo.
if not "%BOT_EXIT%"=="0" echo Ishga tushirish tugamadi. Yuqoridagi xabarni tekshiring.
popd
pause
exit /b %BOT_EXIT%
:missing
echo ZIP faylni avval Extract All bilan toliq chiqaring, keyin start.bat ni oching.
popd
pause
exit /b 1
