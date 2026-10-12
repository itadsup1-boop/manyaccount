param([switch]$NoBrowser)

. (Join-Path $PSScriptRoot "windows_common.ps1")
$ErrorActionPreference = "Stop"
Set-ProjectEnvironment

$venvPython = Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $python = (Resolve-Path -LiteralPath $venvPython).Path
} else {
    $python = Get-ProjectPython
}
Write-Host "Python Web Hub: $python"
if (-not (Test-PythonModules -Python $python -Modules @("fastapi", "uvicorn", "dotenv"))) {
    throw "Python Web Hub khong co FastAPI/Uvicorn: $python. Hay kiem tra .venv\Scripts\python.exe."
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { throw "Thieu Node.js/npm. Cai Node.js LTS roi chay lai." }

$frontendDir = Join-Path $script:ProjectRoot "adsup_central_hub\frontend"
$backendDir = Join-Path $script:ProjectRoot "adsup_central_hub\backend"
$logDir = Join-Path $script:ProjectRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Chua co node_modules, dang chay npm install..." -ForegroundColor Yellow
    Push-Location $frontendDir
    & $npm.Source install
    Pop-Location
}

$backendLog = Join-Path $logDir "hub_backend.log"
$backendErrorLog = Join-Path $logDir "hub_backend_error.log"
$frontendLog = Join-Path $logDir "hub_frontend.log"
$frontendErrorLog = Join-Path $logDir "hub_frontend_error.log"
$backend = $null
$frontend = $null

function Wait-HttpPort {
    param([int]$Port, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $client.Connect("127.0.0.1", $Port)
            $client.Dispose()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

try {
    Write-Host "Khoi dong FastAPI backend tai http://127.0.0.1:8000 ..."
    $backend = Start-Process -FilePath $python -WorkingDirectory $backendDir -ArgumentList @(
        "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"
    ) -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrorLog -PassThru

    Write-Host "Khoi dong Vite frontend tai http://localhost:5173 ..."
    $frontend = Start-Process -FilePath $npm.Source -WorkingDirectory $frontendDir -ArgumentList @(
        "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"
    ) -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog -PassThru

    if (-not (Wait-HttpPort -Port 8000)) {
        throw "Backend khong mo duoc cong 8000. Xem data\logs\hub_backend_error.log."
    }
    if (-not (Wait-HttpPort -Port 5173)) {
        throw "Frontend khong mo duoc cong 5173. Xem data\logs\hub_frontend_error.log."
    }

    Write-Host ""
    Write-Host "WEB HUB DA SAN SANG: http://localhost:5173" -ForegroundColor Green
    Write-Host "API: http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "Nhan Ctrl+C de dung ca backend va frontend."
    if (-not $NoBrowser) { Start-Process "http://localhost:5173" }

    while ($true) {
        Start-Sleep -Seconds 1
        if ($backend.HasExited -or $frontend.HasExited) {
            throw "Mot tien trinh hub da dung. Kiem tra log trong data\logs."
        }
    }
} finally {
    foreach ($process in @($frontend, $backend)) {
        if ($process -and -not $process.HasExited) {
            try { & taskkill.exe /PID $process.Id /T /F | Out-Null } catch { }
        }
    }
}
