#requires -Version 5.1
<#
TKAutoRipper Windows installer
------------------------------
Run from the repository root:

  powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\windows.ps1

This script installs missing Windows dependencies through winget, creates the
TKAutoRipper config/output/temp directories, builds the local Python virtualenv,
and writes a small launcher script.
#>

[CmdletBinding()]
param(
    [switch]$SkipPython,
    [switch]$SkipOpenSSL,
    [switch]$SkipHandBrake,
    [switch]$SkipMakeMKV,
    [switch]$NoShortcut,
    [switch]$ForceWingetInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Green
}

function Write-Note {
    param([string]$Message)
    Write-Host "[i] $Message" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[x] $Message" -ForegroundColor Red
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($machinePath, $userPath) -join ";"
}

function Add-PathForCurrentSession {
    param([string]$Directory)
    if ([string]::IsNullOrWhiteSpace($Directory) -or -not (Test-Path $Directory)) {
        return
    }

    $parts = $env:Path -split ";"
    if ($parts -notcontains $Directory) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Assert-Windows {
    if ($PSVersionTable.PSEdition -eq "Core" -and -not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
        throw "This installer is intended for Windows."
    }
}

function Assert-RepoRoot {
    param([string]$Root)
    $required = @("main.py", "app", "config", "installer\requirements_windows.txt")
    foreach ($item in $required) {
        if (-not (Test-Path (Join-Path $Root $item))) {
            throw "Please run this script from the TKAutoRipper repository root."
        }
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Winget {
    if (-not (Test-Command "winget")) {
        throw "winget was not found. Install App Installer from the Microsoft Store, then re-run this script."
    }
}

function Install-WingetPackage {
    param(
        [string]$Id,
        [string]$Name
    )

    Ensure-Winget

    Write-Info "Installing/checking $Name via winget ($Id)..."
    $args = @(
        "install",
        "--exact",
        "--id", $Id,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )

    if ($ForceWingetInstall) {
        $args += "--force"
    }

    & winget @args
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed while installing $Name ($Id)."
    }

    Refresh-Path
}

function Find-OpenSSL {
    $cmd = Get-Command "openssl.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\OpenSSL-Win64\bin\openssl.exe",
        "$env:ProgramFiles\OpenSSL-Win32\bin\openssl.exe",
        "${env:ProgramFiles(x86)}\OpenSSL-Win32\bin\openssl.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            Add-PathForCurrentSession -Directory (Split-Path $candidate -Parent)
            return $candidate
        }
    }

    return $null
}

function Test-HandBrake {
    if (Test-Path "$env:ProgramFiles\HandBrake\HandBrakeCLI.exe") {
        return $true
    }
    return (Test-Command "HandBrakeCLI.exe")
}

function Test-MakeMKV {
    if (Test-Path "${env:ProgramFiles(x86)}\MakeMKV\makemkvcon64.exe") {
        return $true
    }
    if (Test-Path "$env:ProgramFiles\MakeMKV\makemkvcon64.exe") {
        return $true
    }
    return (Test-Command "makemkvcon64.exe")
}

function Get-PythonCommand {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Test-Command $candidate.Exe)) {
            continue
        }

        try {
            $version = & $candidate.Exe @($candidate.Args) -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) {
                return [pscustomobject]@{
                    Exe = $candidate.Exe
                    Args = [string[]]$candidate.Args
                    Version = [string]$version
                }
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Invoke-BasePython {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Python,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$PythonArgs
    )

    & $Python.Exe @($Python.Args) @PythonArgs
}

function Ensure-Python {
    if ($SkipPython) {
        Write-Note "Skipping Python install by request."
        $python = Get-PythonCommand
        if (-not $python) {
            throw "Python was not found, and -SkipPython was specified."
        }
        return $python
    }

    $python = Get-PythonCommand
    if ($python) {
        Write-Info "Python detected: $($python.Version)"
        return $python
    }

    Install-WingetPackage -Id "Python.Python.3.12" -Name "Python 3.12"
    $python = Get-PythonCommand
    if (-not $python) {
        throw "Python was installed, but this shell cannot see it yet. Open a new PowerShell window and re-run the installer."
    }

    Write-Info "Python detected after install: $($python.Version)"
    return $python
}

function Ensure-ExternalTools {
    if ($SkipOpenSSL) {
        Write-Note "Skipping OpenSSL install/check by request."
    }
    else {
        $openssl = Find-OpenSSL
        if (-not $openssl) {
            Install-WingetPackage -Id "ShiningLight.OpenSSL.Light" -Name "OpenSSL Light"
            $openssl = Find-OpenSSL
        }

        if ($openssl) {
            Write-Info "OpenSSL detected: $openssl"
        }
        else {
            Write-Warn "OpenSSL was not found. TKAutoRipper needs openssl.exe to create its HTTPS certificate on first start."
        }
    }

    if ($SkipHandBrake) {
        Write-Note "Skipping HandBrake install/check by request."
    }
    elseif (Test-HandBrake) {
        Write-Info "HandBrakeCLI detected."
    }
    else {
        Install-WingetPackage -Id "HandBrake.HandBrake.CLI" -Name "HandBrake CLI"
        if (Test-HandBrake) {
            Write-Info "HandBrakeCLI detected after install."
        }
        else {
            Write-Warn "HandBrake CLI installed, but HandBrakeCLI.exe was not found."
        }
    }

    if ($SkipMakeMKV) {
        Write-Note "Skipping MakeMKV install/check by request."
    }
    elseif (Test-MakeMKV) {
        Write-Info "MakeMKV detected."
    }
    else {
        Install-WingetPackage -Id "GuinpinSoft.MakeMKV" -Name "MakeMKV"
        if (Test-MakeMKV) {
            Write-Info "MakeMKV detected after install."
        }
        else {
            Write-Warn "MakeMKV installed, but makemkvcon64.exe was not found at the expected path."
        }
    }
}

function Setup-AppDirectories {
    param([string]$RepoRoot)

    $homeRoot = Join-Path $env:USERPROFILE "TKAutoRipper"
    $configRoot = Join-Path $homeRoot "config"
    $dirs = @(
        $homeRoot,
        $configRoot,
        (Join-Path $homeRoot "output"),
        (Join-Path $homeRoot "output\DVD"),
        (Join-Path $homeRoot "output\BLURAY"),
        (Join-Path $homeRoot "output\ISO"),
        (Join-Path $homeRoot "temp"),
        (Join-Path $homeRoot "logs")
    )

    Write-Info "Creating TKAutoRipper directories under $homeRoot..."
    foreach ($dir in $dirs) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    Write-Info "Installing default config files into $configRoot..."
    Get-ChildItem -Path (Join-Path $RepoRoot "config") -File | ForEach-Object {
        if ($_.Name -eq "credentials.conf") {
            return
        }

        $target = Join-Path $configRoot $_.Name
        if (Test-Path $target) {
            Write-Note "Keeping existing config: $target"
        }
        else {
            Copy-Item -Path $_.FullName -Destination $target
        }
    }

    $credentials = Join-Path $configRoot "credentials.conf"
    $credentialsExample = Join-Path $RepoRoot "config\credentials.example.conf"
    if (-not (Test-Path $credentials) -and (Test-Path $credentialsExample)) {
        Write-Info "Creating credentials file: $credentials"
        Copy-Item -Path $credentialsExample -Destination $credentials
    }
}

function Setup-PythonVenv {
    param(
        [string]$RepoRoot,
        [object]$Python
    )

    if (-not $Python) {
        throw "No Python interpreter is available for virtualenv creation."
    }

    $venvDir = Join-Path $RepoRoot ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    $requirements = Join-Path $RepoRoot "installer\requirements_windows.txt"

    if ((Test-Path $venvDir) -and -not (Test-Path $venvPython)) {
        Write-Warn "Existing .venv is incomplete; recreating it."
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    if (-not (Test-Path $venvPython)) {
        Write-Info "Creating Python virtual environment in .venv..."
        Invoke-BasePython -Python $Python -PythonArgs @("-m", "venv", $venvDir)
        if ($LASTEXITCODE -ne 0) {
            throw "Python failed to create the virtual environment."
        }
    }
    else {
        Write-Info "Virtualenv .venv already exists; reusing."
    }

    Write-Info "Upgrading pip..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed."
    }

    Write-Info "Installing Python dependencies from installer\requirements_windows.txt..."
    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed."
    }

    Write-Info "Running Python import smoke test..."
    & $venvPython -c "import fastapi, uvicorn, yaml, psutil, requests, httpx, cpuinfo; print('Python dependencies OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "Python import smoke test failed."
    }

    Push-Location $RepoRoot
    try {
        & $venvPython -c "import main; print('TKAutoRipper import OK')"
        if ($LASTEXITCODE -ne 0) {
            throw "TKAutoRipper import smoke test failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Write-Launcher {
    param([string]$RepoRoot)

    $launcher = Join-Path $RepoRoot "start_windows.cmd"
    $content = @"
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
"@

    Set-Content -Path $launcher -Value $content -Encoding ASCII
    Write-Info "Wrote launcher: $launcher"

    if ($NoShortcut) {
        Write-Note "Skipping desktop shortcut by request."
        return
    }

    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shortcutPath = Join-Path $desktop "TKAutoRipper.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $RepoRoot
        $shortcut.Description = "Start TKAutoRipper"
        $shortcut.Save()
        Write-Info "Created desktop shortcut: $shortcutPath"
    }
    catch {
        Write-Warn "Could not create desktop shortcut: $($_.Exception.Message)"
    }
}

function Main {
    Assert-Windows

    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Set-Location $repoRoot
    Assert-RepoRoot -Root $repoRoot

    Write-Info "TKAutoRipper Windows installer"
    if (-not (Test-Admin)) {
        Write-Warn "PowerShell is not running as Administrator. Winget installers may prompt for elevation or fail."
    }

    Ensure-Winget
    $python = Ensure-Python
    Ensure-ExternalTools
    Setup-AppDirectories -RepoRoot $repoRoot
    Setup-PythonVenv -RepoRoot $repoRoot -Python $python
    Write-Launcher -RepoRoot $repoRoot

    Write-Host ""
    Write-Host "Installation complete." -ForegroundColor Green
    Write-Host ""
    Write-Host "Start TKAutoRipper with:"
    Write-Host "  .\start_windows.cmd"
    Write-Host ""
    Write-Host "Then open:"
    Write-Host "  https://[::1]:8000"
    Write-Host ""
    Write-Host "Default auth (change this in ~/TKAutoRipper/config/TKAutoRipper.conf):"
    Write-Host "  username: admin"
    Write-Host "  password: admin"
}

try {
    Main
}
catch {
    Write-Fail $_.Exception.Message
    exit 1
}
