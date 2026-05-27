# GoiasMonitorPy - Stop detached application process

param(
    [int]$Port = 8000
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logsDir = Join-Path $scriptDir "logs"
$pidFile = Join-Path $logsDir "uvicorn-$Port.pid"

if (-not (Test-Path $pidFile)) {
    Write-Error "PID file not found at $pidFile. The detached app may already be stopped."
    exit 1
}

$processId = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $processId) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Error "PID file is empty. Removed stale PID file."
    exit 1
}

$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($null -eq $process) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Process $processId is no longer running. Removed stale PID file." -ForegroundColor Yellow
    exit 0
}

Stop-Process -Id $processId -Force
Remove-Item $pidFile -Force -ErrorAction SilentlyContinue

Write-Host "Stopped GoiasMonitorPy process $processId on port $Port." -ForegroundColor Green