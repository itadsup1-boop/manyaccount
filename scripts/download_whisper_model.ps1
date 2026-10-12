param(
    [ValidateSet("tiny", "base", "small", "medium", "large-v3")]
    [string]$Model = "base"
)

. (Join-Path $PSScriptRoot "windows_common.ps1")
$ErrorActionPreference = "Stop"
Set-ProjectEnvironment

$python = Get-ProjectPython
Write-Host "Python : $python"
Write-Host "Model  : faster-whisper $Model"

if (-not (Test-PythonModules -Python $python -Modules @("faster_whisper"))) {
    Write-Host "Chua co faster-whisper; dang cai package..." -ForegroundColor Yellow
    & $python -m pip install "faster-whisper>=1.2,<2"
    if ($LASTEXITCODE -ne 0) {
        throw "Khong cai duoc faster-whisper."
    }
}

Write-Host "Dang tai/kiem tra model tu Hugging Face (lan dau co the mat vai phut)..." -ForegroundColor Cyan
$code = @"
import sys
from faster_whisper import WhisperModel
WhisperModel(sys.argv[1], device=sys.argv[2], compute_type=sys.argv[3])
print(sys.argv[1])
"@
& $python -c $code $Model cpu float32
if ($LASTEXITCODE -ne 0) {
    throw "Khong tai duoc model faster-whisper $Model. Kiem tra ket noi mang hoac HF_TOKEN."
}
Write-Host "Da san sang model faster-whisper $Model." -ForegroundColor Green
