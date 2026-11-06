# Temporary scheduler entry point, used until Docker + Celery Beat exist.
# Starts the local dev Postgres if needed, then scrapes every active product.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "venv not found at $python" }

try {
    & $python "scripts\dev_db.py" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "dev_db.py failed with exit code $LASTEXITCODE" }

    $env:DATABASE_URL = "postgresql://postgres:@127.0.0.1:55432/postgres"
    & $python "scripts\scrape_all.py"
    exit $LASTEXITCODE
}
catch {
    $log = Join-Path $root "data\scheduler.log"
    Add-Content -Path $log -Value "$(Get-Date -Format o) ERROR $_"
    exit 1
}
