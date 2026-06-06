param(
    [int]$Port = 8765,
    [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"

$PythonExe = Join-Path $Root ".venv-win\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Missing .venv-win. Run scripts/setup-windows.ps1 first."
}

& $PythonExe -m uvicorn main:app --host $HostName --port $Port --reload
