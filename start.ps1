$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (Test-Path "$root\.venv\Scripts\python.exe") {
  $python = "$root\.venv\Scripts\python.exe"
} else {
  $python = "python"
}

Write-Output "Starting backend..."
$backend = Start-Process -FilePath $python `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory "$root\backend" -WindowStyle Hidden -PassThru

Write-Output "Starting frontend..."
$frontend = Start-Process -FilePath "npm.cmd" `
  -ArgumentList "run", "dev" `
  -WorkingDirectory "$root\frontend" -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 2
Write-Output ""
Write-Output "Backend API: http://127.0.0.1:8000/docs"
Write-Output "Frontend: http://127.0.0.1:5173"
Write-Output "Backend PID: $($backend.Id), frontend PID: $($frontend.Id)"
Write-Output "Stop with .\stop.ps1"
