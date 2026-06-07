param(
    [Parameter(Mandatory = $true)]
    [string]$DllPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-MibToBytesOrNull {
    param($Value)
    if ($null -eq $Value) {
        return $null
    }

    $number = [double]$Value
    if ($number -le 0) {
        return $null
    }

    if ($number -gt 1048576) {
        return [int64][Math]::Round($number)
    }

    return [int64][Math]::Round($number * 1048576)
}

function Round-OrNull {
    param($Value, [int]$Digits = 1)
    if ($null -eq $Value) {
        return $null
    }
    return [Math]::Round([double]$Value, $Digits)
}

function Get-PreferredSensorValue {
    param(
        [array]$Sensors,
        [string]$SensorType,
        [string[]]$Patterns,
        [switch]$MaxFallback
    )

    foreach ($pattern in $Patterns) {
        foreach ($sensor in $Sensors) {
            if ($sensor.SensorType.ToString() -ne $SensorType) {
                continue
            }
            if ($sensor.Name -match $pattern -and $null -ne $sensor.Value) {
                return $sensor.Value
            }
        }
    }

    $values = @()
    foreach ($sensor in $Sensors) {
        if ($sensor.SensorType.ToString() -eq $SensorType -and $null -ne $sensor.Value) {
            $values += [double]$sensor.Value
        }
    }

    if ($values.Count -eq 0) {
        return $null
    }

    if ($MaxFallback) {
        return ($values | Measure-Object -Maximum).Maximum
    }

    return $values[0]
}

function Update-HardwareTree {
    param($Hardware)

    $Hardware.Update()
    foreach ($subHardware in $Hardware.SubHardware) {
        Update-HardwareTree -Hardware $subHardware
    }
}

function Get-HardwareSensors {
    param($Hardware)

    $sensors = @()
    foreach ($sensor in $Hardware.Sensors) {
        $sensors += $sensor
    }
    foreach ($subHardware in $Hardware.SubHardware) {
        $sensors += Get-HardwareSensors -Hardware $subHardware
    }
    return $sensors
}

function Get-Vendor {
    param([string]$HardwareType, [string]$Name)

    if ($HardwareType -match "Nvidia" -or $Name -match "NVIDIA|GeForce|Quadro|RTX|GTX") {
        return "nvidia"
    }
    if ($HardwareType -match "Amd" -or $Name -match "AMD|Radeon") {
        return "amd"
    }
    if ($HardwareType -match "Intel" -or $Name -match "Intel|Arc|Iris|UHD") {
        return "intel"
    }
    return "unknown"
}

if (-not (Test-Path $DllPath)) {
    throw "LibreHardwareMonitorLib.dll not found: $DllPath"
}

$resolvedDllPath = (Resolve-Path $DllPath).Path
$dllDirectory = Split-Path $resolvedDllPath -Parent

foreach ($dll in Get-ChildItem -Path $dllDirectory -Filter "*.dll" -ErrorAction SilentlyContinue) {
    if ($dll.FullName -eq $resolvedDllPath) {
        continue
    }

    try {
        [void][Reflection.Assembly]::LoadFrom($dll.FullName)
    }
    catch {
        # Native helper DLLs are expected in this folder too; ignore those.
    }
}

Add-Type -Path $resolvedDllPath

$computer = [LibreHardwareMonitor.Hardware.Computer]::new()
$computer.IsGpuEnabled = $true
$computer.Open()

try {
    Start-Sleep -Milliseconds 150
    $gpus = @()

    foreach ($hardware in $computer.Hardware) {
        $hardwareType = $hardware.HardwareType.ToString()
        if ($hardwareType -notmatch "^Gpu") {
            continue
        }

        Update-HardwareTree -Hardware $hardware
        $sensors = Get-HardwareSensors -Hardware $hardware

        $temperature = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "Temperature" `
            -Patterns @("^GPU Core$", "GPU Core", "Core", "Hot Spot", "Junction")

        $usage = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "Load" `
            -Patterns @("^GPU Core$", "GPU Core", "GPU Total", "D3D 3D", "3D", "Core") `
            -MaxFallback

        $usedMemory = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "SmallData" `
            -Patterns @("D3D Dedicated Memory Used", "GPU Memory Used", "Memory Used", "Dedicated Memory Used")

        if ($null -eq $usedMemory) {
            $usedMemory = Get-PreferredSensorValue `
                -Sensors $sensors `
                -SensorType "Data" `
                -Patterns @("D3D Dedicated Memory Used", "GPU Memory Used", "Memory Used", "Dedicated Memory Used")
        }

        $totalMemory = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "SmallData" `
            -Patterns @("GPU Memory Total", "Dedicated Memory Total", "Memory Total")

        if ($null -eq $totalMemory) {
            $totalMemory = Get-PreferredSensorValue `
                -Sensors $sensors `
                -SensorType "Data" `
                -Patterns @("GPU Memory Total", "Dedicated Memory Total", "Memory Total")
        }

        $memoryPercent = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "Load" `
            -Patterns @("GPU Memory", "Memory")

        if ($null -eq $memoryPercent -and $null -ne $usedMemory -and $null -ne $totalMemory -and [double]$totalMemory -gt 0) {
            $memoryPercent = ([double]$usedMemory / [double]$totalMemory) * 100.0
        }

        $power = Get-PreferredSensorValue `
            -Sensors $sensors `
            -SensorType "Power" `
            -Patterns @("GPU Package", "GPU Core", "Power")

        $gpus += [pscustomobject]@{
            model = $hardware.Name
            vendor = Get-Vendor -HardwareType $hardwareType -Name $hardware.Name
            usage = Round-OrNull -Value $usage -Digits 1
            temperature = Round-OrNull -Value $temperature -Digits 1
            used_memory = Convert-MibToBytesOrNull -Value $usedMemory
            total_memory = Convert-MibToBytesOrNull -Value $totalMemory
            percent_memory = Round-OrNull -Value $memoryPercent -Digits 1
            power = Round-OrNull -Value $power -Digits 1
            source = "LibreHardwareMonitor"
        }
    }

    ConvertTo-Json -InputObject @($gpus) -Depth 4 -Compress
}
finally {
    $computer.Close()
}
