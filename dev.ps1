# Windows equivalent of `make dev`: installs what is missing, then runs the API and the web app.
# Run from PowerShell in the repo folder:  .\dev.ps1     (Ctrl+C stops both)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'Setting up Python (first run only)...'
    uv venv .venv --python 3.11
    uv pip install --python $py -r backend\api\requirements.txt -r backend\pipeline\requirements.txt -r backend\agent\requirements.txt
}
if (-not (Test-Path 'frontend\node_modules\.bin\vite.cmd')) {
    Write-Host 'Installing web packages (first run only)...'
    Push-Location frontend; npm ci; Pop-Location
}

# The API runs in its own window so its log stays readable.
$api = Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'backend.api.main:app', '--port', '8000' `
    -WorkingDirectory $PSScriptRoot -PassThru

Write-Host ''
Write-Host '  Groundwork  ->  http://localhost:5173'
Write-Host '  API docs    ->  http://localhost:8000/docs'
Write-Host '  (Ctrl+C stops both)'
Write-Host ''

Push-Location frontend
try {
    npm run dev -- --port 5173 --strictPort
} finally {
    Pop-Location
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
