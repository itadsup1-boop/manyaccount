param(
    [ValidateSet("menu", "hub", "tiktok", "facebook", "article", "facebook-once", "article-once", "chatgpt-login", "facebook-login", "verify")]
    [string]$App = "menu",
    [string]$ProfileId = "",
    [switch]$NoWait
)

. (Join-Path $PSScriptRoot "windows_common.ps1")
$ErrorActionPreference = "Stop"
Set-ProjectEnvironment

function Invoke-Verify {
    $python = Get-ProjectPython
    Write-Host "=== manyaccount Windows check ===" -ForegroundColor Cyan
    Write-Host "Project: $script:ProjectRoot"
    Write-Host "Python : $python"
    Write-Host (".env  : " + ($(if (Test-Path (Join-Path $script:ProjectRoot ".env")) { "OK" } else { "MISSING" })))
    $ffmpegReady = Add-FfmpegToPath
    Write-Host ("FFmpeg: " + ($(if ($ffmpegReady) { "OK" } else { "MISSING" })))
    $profileRoot = Join-Path $script:ProjectRoot "data\chrome_profiles\chatgpt"
    $profiles = Get-ChildItem -LiteralPath $profileRoot -Directory -ErrorAction SilentlyContinue
    if (-not $profiles) { throw "Chua co data\chrome_profiles\chatgpt. Hay login ChatGPT truoc." }
    foreach ($profile in $profiles) {
        $cookie = Join-Path $profile.FullName "Default\Network\Cookies"
        $status = if (Test-Path -LiteralPath $cookie) { "OK" } else { "MISSING" }
        Write-Host ("ChatGPT {0}: {1}" -f $profile.Name, $status)
    }
    if (-not (Test-PythonModules -Python $python -Modules @("playwright"))) {
        Write-Host "Playwright: MISSING (chay setup_windows.bat)" -ForegroundColor Yellow
    } else {
        Write-Host "Playwright: OK" -ForegroundColor Green
    }
}

if ($App -eq "verify") {
    Invoke-Verify
    if (-not $NoWait) { Read-Host "Nhan Enter de dong" }
    exit 0
}

if ($App -eq "menu") {
    Write-Host ""
    Write-Host "manyaccount - Windows launcher" -ForegroundColor Cyan
    Write-Host "1. Mo Web Hub"
    Write-Host "2. TikTok Matrix Bot"
    Write-Host "3. Facebook News GUI"
    Write-Host "4. Article News GUI"
    Write-Host "5. Facebook pipeline - run once"
    Write-Host "6. Article pipeline - run once"
    Write-Host "7. Login ChatGPT profile chung"
    Write-Host "8. Login Facebook crawler"
    Write-Host "9. Kiem tra he thong/profile"
    $choice = Read-Host "Chon 1-9"
    $map = @{ "1"="hub"; "2"="tiktok"; "3"="facebook"; "4"="article"; "5"="facebook-once"; "6"="article-once"; "7"="chatgpt-login"; "8"="facebook-login"; "9"="verify" }
    if (-not $map.ContainsKey($choice)) { throw "Lua chon khong hop le." }
    $App = $map[$choice]
}

if ($App -eq "hub") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "run_hub_windows.ps1")
    exit $LASTEXITCODE
}

if ($App -eq "verify") {
    Invoke-Verify
    if (-not $NoWait) { Read-Host "Nhan Enter de dong" }
    exit 0
}

$python = Get-ProjectPython
$entry = $null
$scriptArgs = @()
$needsFfmpeg = $false
switch ($App) {
    "tiktok"         { $entry = "apps\uploader_tiktok\desktop_app.py"; $needsFfmpeg = $true }
    "facebook"       { $entry = "apps\creator_facebook\fb_desktop_app.py"; $needsFfmpeg = $true }
    "article"        { $entry = "apps\creator_article\article_desktop_app.py"; $needsFfmpeg = $true }
    "facebook-once"  { $entry = "apps\creator_facebook\fb_pipeline.py"; $scriptArgs = @("run-once"); $needsFfmpeg = $true }
    "article-once"   { $entry = "apps\creator_article\article_pipeline_core.py"; $scriptArgs = @("run-once"); $needsFfmpeg = $true }
    "chatgpt-login"  { $entry = "apps\creator_facebook\chatgpt_automator.py"; $scriptArgs = @("login") }
    "facebook-login" { $entry = "apps\creator_facebook\fb_crawler.py"; $scriptArgs = @("login") }
}

if (-not $entry) { throw "Khong xac dinh duoc ung dung." }
$entryPath = Join-Path $script:ProjectRoot $entry
if (-not (Test-Path -LiteralPath $entryPath)) { throw "Khong tim thay entry point: $entry" }
if ($needsFfmpeg -and -not (Add-FfmpegToPath)) {
    throw "Khong tim thay FFmpeg. Cai bang 'winget install Gyan.FFmpeg.Shared', sau do mo terminal moi."
}
if (-not (Test-PythonModules -Python $python -Modules @("playwright"))) {
    throw "Thieu Playwright. Chay scripts\setup_windows.bat truoc."
}

if ($App -eq "chatgpt-login" -and $ProfileId) {
    $scriptArgs += $ProfileId
}

Write-Host "Chay $App ..." -ForegroundColor Green
& $python $entryPath @scriptArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { throw "Ung dung ket thuc voi ma loi $exitCode." }
