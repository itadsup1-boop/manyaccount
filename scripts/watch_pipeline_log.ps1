param([switch]$ErrorsOnly)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$logPath = Join-Path $projectRoot "data\pipeline_events.jsonl"
New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null
if (-not (Test-Path -LiteralPath $logPath)) {
    New-Item -ItemType File -Path $logPath | Out-Null
}

Write-Host "Theo doi pipeline: $logPath" -ForegroundColor Cyan
Write-Host "Nhan Ctrl+C de dung." -ForegroundColor DarkGray

Get-Content -LiteralPath $logPath -Tail 30 -Wait | ForEach-Object {
    try {
        $event = $_ | ConvertFrom-Json
        if ($ErrorsOnly -and $event.event -notin @("failed", "skipped")) { return }
        $channel = if ($event.channel_id) { $event.channel_id } else { "-" }
        $message = if ($event.message) { " | $($event.message)" } else { "" }
        $line = "[$($event.ts)] [$channel] $($event.event.ToUpper()) $($event.stage)$message"
        if ($event.event -eq "failed") {
            Write-Host $line -ForegroundColor Red
        } elseif ($event.event -eq "skipped") {
            Write-Host $line -ForegroundColor Yellow
        } else {
            Write-Host $line
        }
    } catch {
        Write-Host $_ -ForegroundColor DarkGray
    }
}
