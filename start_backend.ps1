# Start ETH Microstructure Terminal — Backend
Set-Location "$PSScriptRoot\backend"

if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv venv
}

Write-Host "Activating venv..." -ForegroundColor Cyan
& ".\venv\Scripts\Activate.ps1"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt -q

if (-not (Test-Path ".env")) {
    Write-Host "No .env found — copying .env.example. Edit backend\.env to add your ANTHROPIC_API_KEY." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

Write-Host "Starting FastAPI backend on http://localhost:8000" -ForegroundColor Green
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
