# GoiasMonitorPy - Start Application Script
# PowerShell version for development server startup

param(
    [switch]$NoReload,
    [string]$HostAddr = "127.0.0.1",
    [int]$Port = 8000
)

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Activate virtual environment
$venvPath = Join-Path $scriptDir ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $activateScript)) {
    Write-Error "Virtual environment not found at $venvPath"
    exit 1
}

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python executable not found at $pythonExe"
    exit 1
}

& $activateScript

# Install runtime dependencies only when uvicorn is not available in the venv
$uvicornCheck = & $pythonExe -c "import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing runtime dependencies..." -ForegroundColor Cyan
    $requirementsFile = Join-Path $scriptDir "requirements.txt"
    if (-not (Test-Path $requirementsFile)) {
        Write-Error "requirements.txt not found at $requirementsFile"
        exit 1
    }

    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to upgrade pip"
        exit 1
    }

    & $pythonExe -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install runtime dependencies"
        exit 1
    }
}

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($null -ne $portInUse) {
    $owner = Get-Process -Id $portInUse[0].OwningProcess -ErrorAction SilentlyContinue
    if ($null -ne $owner) {
        Write-Error "Port $Port is already in use by process $($owner.ProcessName) (PID $($owner.Id)). Use -Port with another value or stop that process."
    } else {
        Write-Error "Port $Port is already in use. Use -Port with another value or stop the process using it."
    }
    exit 1
}

# Build uvicorn command
$uvicornArgs = @(
    "app:app"
    "--host", $HostAddr
    "--port", $Port
)

if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting GoiasMonitorPy on http://$($HostAddr):$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Run uvicorn using python -m (more reliable)
& $pythonExe -m uvicorn @uvicornArgs
