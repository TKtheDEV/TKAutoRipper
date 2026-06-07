@echo off
setlocal
set "ROOT=%~dp0"

if exist "%ProgramFiles%\OpenSSL-Win64\bin\openssl.exe" set "PATH=%ProgramFiles%\OpenSSL-Win64\bin;%PATH%"
if exist "%ProgramFiles%\OpenSSL-Win32\bin\openssl.exe" set "PATH=%ProgramFiles%\OpenSSL-Win32\bin;%PATH%"
if exist "%ProgramFiles(x86)%\OpenSSL-Win32\bin\openssl.exe" set "PATH=%ProgramFiles(x86)%\OpenSSL-Win32\bin;%PATH%"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo TKAutoRipper virtualenv was not found. Run installer\windows.ps1 first.
  exit /b 1
)

"%ROOT%.venv\Scripts\python.exe" "%ROOT%main.py"
