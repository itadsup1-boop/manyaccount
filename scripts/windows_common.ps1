# Shared Windows helpers for manyaccount launchers.

$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path

function Get-ProjectPython {
    $explicitPython = ([string]$env:MANYACCOUNT_PYTHON).Trim().Trim('"')
    if ($explicitPython -and (Test-Path -LiteralPath $explicitPython)) {
        return (Resolve-Path -LiteralPath $explicitPython).Path
    }

    $candidates = @(
        (Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $script:ProjectRoot "venv\Scripts\python.exe")
    )

    foreach ($commandName in @("python", "py")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            try {
                & $command.Source --version 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { $candidates += $command.Source }
            } catch {
                # Ignore Windows Store aliases and broken shims.
            }
        }
    }

    $candidates += @(
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python311\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python313\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python312\python.exe"),
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python313\python.exe",
        "D:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe"
    )

    foreach ($candidate in $candidates) {
        try {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $resolved = (Resolve-Path -LiteralPath $candidate).Path
                $previousErrorAction = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                & $resolved --version 2>$null | Out-Null
                $pythonExitCode = $LASTEXITCODE
                $ErrorActionPreference = $previousErrorAction
                if ($pythonExitCode -eq 0) { return $resolved }
            }
        } catch {
            # A protected/unavailable installation should not stop discovery.
        }
    }

    throw "Khong tim thay Python. Chay scripts\setup_windows.bat hoac cai Python 3.11+ roi chay lai."
}

function Add-FfmpegToPath {
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        return $true
    }

    # imageio-ffmpeg ships a platform binary after requirements.txt is installed.
    try {
        $python = Get-ProjectPython
        $ffmpegExe = & $python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ffmpegExe -and (Test-Path -LiteralPath $ffmpegExe.Trim())) {
            $ffmpegDir = Split-Path -Parent $ffmpegExe.Trim()
            $env:Path = "$ffmpegDir;$env:Path"
            return $true
        }
    } catch {
        # The caller prints the actionable warning.
    }
    return $false
}

function Set-ProjectEnvironment {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Set-Location -LiteralPath $script:ProjectRoot
    [void](Add-FfmpegToPath)
}

function Test-PythonModules {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [string[]]$Modules = @("customtkinter", "playwright", "supabase", "ffmpeg", "yt_dlp")
    )

    $imports = ($Modules | ForEach-Object { "import $_" }) -join ";"
    $code = "$imports; print('MODULES_OK')"
    try {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $raw = & $Python -c $code 2>&1
        $moduleExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
        return ($moduleExitCode -eq 0 -and (($raw -join "`n") -match "MODULES_OK"))
    } catch {
        return $false
    }
}

function Show-ReadyStatus {
    param([switch]$RequireFfmpeg)

    $python = Get-ProjectPython
    $envFile = Join-Path $script:ProjectRoot ".env"
    $ffmpegReady = Add-FfmpegToPath
    Write-Host "Project : $script:ProjectRoot"
    Write-Host "Python  : $python"
    Write-Host ("FFmpeg  : " + ($(if ($ffmpegReady) { "OK" } else { "MISSING" })))
    Write-Host ("Env     : " + ($(if (Test-Path -LiteralPath $envFile) { "OK (.env)" } else { "MISSING (.env)" })))

    if (-not (Test-PythonModules -Python $python)) {
        throw "Thieu package Python. Chay scripts\setup_windows.bat de cai requirements.txt."
    }
    if ($RequireFfmpeg -and -not $ffmpegReady) {
        throw "Khong tim thay FFmpeg. Cai FFmpeg (winget install Gyan.FFmpeg.Shared) roi mo terminal moi."
    }
    return $python
}
