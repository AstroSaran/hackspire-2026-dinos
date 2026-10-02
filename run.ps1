$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
  py -m venv (Join-Path $root '.venv')
}
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m pip install -r (Join-Path $root 'backend\requirements-live.txt')
Push-Location (Join-Path $root 'backend')
try { & $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001 }
finally { Pop-Location }
