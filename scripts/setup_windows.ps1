param([switch]$SkipInstall, [switch]$RepairVenv)

. (Join-Path $PSScriptRoot "windows_common.ps1")
$ErrorActionPreference = "Stop"
Set-ProjectEnvironment

try {
    $python = Get-ProjectPython
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Cai Python 3.11+ tu https://www.python.org/downloads/windows/ va nho tick 'Add python.exe to PATH'."
    exit 1
}

$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $python -c "import venv, ensurepip" 2>$null | Out-Null
$venvExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorAction
if ($venvExitCode -ne 0) {
    Write-Host "Python hien tai khong co module venv (thuong la Python di kem pgAdmin)." -ForegroundColor Red
    Write-Host "Hay cai Python 3.11+ chinh thuc tu https://www.python.org/downloads/windows/ va tick 'Add python.exe to PATH', sau do chay lai file nay."
    exit 1
}

$venvPython = Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"
if ($RepairVenv -and (Test-Path -LiteralPath (Join-Path $script:ProjectRoot ".venv"))) {
    Write-Host "Xoa .venv theo yeu cau -RepairVenv..." -ForegroundColor Yellow
    Remove-Item -LiteralPath (Join-Path $script:ProjectRoot ".venv") -Recurse -Force
}
if (Test-Path -LiteralPath $venvPython) {
    $oldAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPython --version 2>$null | Out-Null
    $venvWorks = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $oldAction
    if (-not $venvWorks) {
        Write-Host "Phat hien .venv hong, dang tao lai..." -ForegroundColor Yellow
        Remove-Item -LiteralPath (Join-Path $script:ProjectRoot ".venv") -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/5] Tao virtual environment .venv..."
    & $python -m venv (Join-Path $script:ProjectRoot ".venv")
    $python = $venvPython
} else {
    $python = (Resolve-Path -LiteralPath $venvPython).Path
    Write-Host "[1/5] Dung .venv hien co: $python"
}

Write-Host "Python dang dung: $python"

if (-not $SkipInstall) {
    Write-Host "[2/5] Cai dependency Python..."
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $script:ProjectRoot "requirements.txt")
    Write-Host "[3/5] Cai Chromium cho Playwright..."
    & $python -m playwright install chromium

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) {
        Write-Host "[4/5] Cai dependency giao dien web..."
        Push-Location (Join-Path $script:ProjectRoot "adsup_central_hub\frontend")
        & $npm.Source install
        Pop-Location
    } else {
        Write-Host "[4/5] Khong tim thay npm.cmd; bo qua frontend. Cai Node.js roi chay npm install trong adsup_central_hub\frontend." -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/5] Bo qua cai dependency theo yeu cau."
    Write-Host "[3/5] Bo qua Playwright browser theo yeu cau."
    Write-Host "[4/5] Bo qua frontend theo yeu cau."
}

$envFile = Join-Path $script:ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $script:ProjectRoot ".env.example") -Destination $envFile
    Write-Host "[5/5] Da tao .env tu .env.example. Hay dien key that truoc khi chay pipeline." -ForegroundColor Yellow
} else {
    Write-Host "[5/5] Da giu nguyen .env hien co."
}

Write-Host ""
Write-Host "Kiem tra nhanh:" -ForegroundColor Cyan
& $python -m compileall -q (Join-Path $script:ProjectRoot "apps") (Join-Path $script:ProjectRoot "shared")
if (-not (Test-PythonModules -Python $python -Modules @("fastapi", "uvicorn", "dotenv"))) {
    throw "Python environment chua co FastAPI/Uvicorn. Xoa .venv, dat MANYACCOUNT_PYTHON dung, roi chay lai setup_windows.bat."
}
if (-not (Add-FfmpegToPath)) {
    Write-Host "CANH BAO: chua co FFmpeg trong PATH. Cai bang: winget install Gyan.FFmpeg.Shared" -ForegroundColor Yellow
} else {
    Write-Host "FFmpeg: OK" -ForegroundColor Green
}
Write-Host "Hoan tat. Dung scripts\run_windows.bat de mo menu chay du an." -ForegroundColor Green
