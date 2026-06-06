param(
    [string]$SourceZip,
    [string]$Destination,
    [switch]$Force,
    [switch]$RunSetup
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

if (-not $SourceZip) {
    $SourceZip = Get-ChildItem -File -LiteralPath "exports\portable" -Filter "eba-workbench-*.zip" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $SourceZip -or -not (Test-Path $SourceZip)) {
    throw "Source zip not found. Provide -SourceZip or create a package first."
}

if (-not $Destination) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($SourceZip)
    $Destination = Join-Path $ProjectRoot "exports\portable\unpacked\$baseName"
}

if (Test-Path $Destination) {
    if (-not $Force) {
        throw "Destination already exists: $Destination. Pass -Force to replace it."
    }
    Remove-Item -Recurse -Force -LiteralPath $Destination
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Expand-Archive -LiteralPath $SourceZip -DestinationPath $Destination -Force

foreach ($dir in @("cache", "exports", "var", "artifacts", "canonical", "registers", "scenario-overrides", "documents", "documents\immutable", "data\analysis")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Destination $dir) | Out-Null
}

$envPath = Join-Path $Destination ".env"
$envExample = Join-Path $Destination ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExample)) {
    Copy-Item -LiteralPath $envExample -Destination $envPath
}

$installRecordDir = Join-Path $Destination "var"
New-Item -ItemType Directory -Force -Path $installRecordDir | Out-Null
$installRecord = [ordered]@{
    unpacked_at = (Get-Date).ToUniversalTime().ToString("o")
    source_zip = (Resolve-Path $SourceZip).Path
    destination = (Resolve-Path $Destination).Path
    platform = "windows"
    setup_run = [bool]$RunSetup
}
$installRecord | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $installRecordDir "portable-install.json") -Encoding UTF8

if ($RunSetup) {
    & (Join-Path $Destination "scripts\setup-windows.ps1")
}

Write-Host "Unpacked workbench to: $Destination"
