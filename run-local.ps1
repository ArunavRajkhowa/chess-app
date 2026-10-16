# One-command local run on Windows PowerShell. Same steps as run-local.sh.
# Usage: .\run-local.ps1          (one process on http://127.0.0.1:8765)
#        .\run-local.ps1 dev      (backend + Vite dev server on :5173)
param([string]$Mode = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
pip install -q -r backend\requirements.txt
if (-not (Test-Path frontend\node_modules)) { Push-Location frontend; npm install; Pop-Location }
Push-Location frontend; node scripts\copy-engine.mjs; Pop-Location
$port = if ($env:PORT) { $env:PORT } else { "8765" }
if ($Mode -eq "dev") {
  Start-Process -NoNewWindow powershell -ArgumentList "-Command", "cd frontend; npm run dev -- --host 127.0.0.1 --port 5173"
  python -m uvicorn backend.app:app --host 127.0.0.1 --port $port --reload
} else {
  Push-Location frontend; npm run build; Pop-Location
  Write-Host "Open http://127.0.0.1:$port"
  python -m uvicorn backend.app:app --host 127.0.0.1 --port $port
}
