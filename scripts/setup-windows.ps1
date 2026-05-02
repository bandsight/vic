param(
    [string]$Python = "py -3.12",
    [switch]$WithBrowser,
    [switch]$PipTrustedHost,
    [switch]$Offline,
    [string]$Wheelhouse = "vendor\python-wheels",
    [switch]$WithNodeTools,
    [string]$NpmCache = "vendor\npm-cache",
    [switch]$NpmUseSystemCa,
    [switch]$NpmStrictSslFalse
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

function Invoke-NativeExpression {
    param(
        [Parameter(Mandatory = $true)][string]$CommandLine
    )

    Invoke-Expression $CommandLine
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $CommandLine"
    }
}

if (-not (Test-Path ".venv-win")) {
    Write-Host "Creating Windows virtual environment..."
    Invoke-NativeExpression "$Python -m venv .venv-win"
}

$PythonExe = Join-Path $Root ".venv-win\Scripts\python.exe"
$PipSourceArgs = @()
if ($Offline) {
    $WheelhousePath = $Wheelhouse
    if (-not [System.IO.Path]::IsPathRooted($WheelhousePath)) {
        $WheelhousePath = Join-Path $Root $WheelhousePath
    }
    if (-not (Test-Path $WheelhousePath)) {
        throw "Offline Python wheelhouse not found: $WheelhousePath. Run scripts/build-offline-deps.ps1 first."
    }
    $PipSourceArgs = @("--no-index", "--find-links", $WheelhousePath)
    Write-Host "Using offline Python wheelhouse: $WheelhousePath"
} else {
    if ($PipTrustedHost) {
        $PipSourceArgs = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")
    }
    Invoke-NativeCommand $PythonExe (@("-m", "pip", "install") + $PipSourceArgs + @("--upgrade", "pip"))
}

Invoke-NativeCommand $PythonExe (@("-m", "pip", "install") + $PipSourceArgs + @("-r", "requirements-dev.txt"))

if ($WithBrowser) {
    Invoke-NativeCommand $PythonExe (@("-m", "pip", "install") + $PipSourceArgs + @("-r", "requirements-browser.txt"))
    Invoke-NativeCommand $PythonExe @("-m", "playwright", "install", "chromium")
}

if ($WithNodeTools -and (Test-Path "package.json")) {
    $NpmArgs = @("ci", "--no-audit", "--no-fund")
    if (-not (Test-Path "package-lock.json")) {
        $NpmArgs = @("install", "--no-audit", "--no-fund")
    }
    $NpmCachePath = $NpmCache
    if (-not [System.IO.Path]::IsPathRooted($NpmCachePath)) {
        $NpmCachePath = Join-Path $Root $NpmCachePath
    }
    if ($Offline) {
        if (-not (Test-Path $NpmCachePath)) {
            throw "Offline npm cache not found: $NpmCachePath. Run scripts/build-offline-deps.ps1 -WithNodeTools first."
        }
        $NpmArgs += @("--offline", "--cache", $NpmCachePath)
    } elseif (Test-Path $NpmCachePath) {
        $NpmArgs += @("--prefer-offline", "--cache", $NpmCachePath)
    }
    if ($NpmStrictSslFalse) {
        $NpmArgs += "--strict-ssl=false"
    }
    $PreviousNodeOptions = $env:NODE_OPTIONS
    if ($NpmUseSystemCa) {
        $env:NODE_OPTIONS = (($PreviousNodeOptions, "--use-system-ca") | Where-Object { $_ }) -join " "
    }
    try {
        Invoke-NativeCommand "npm" $NpmArgs
    } finally {
        $env:NODE_OPTIONS = $PreviousNodeOptions
    }
} elseif (Test-Path "package.json") {
    Write-Host "Skipped Node tooling install. Pass -WithNodeTools to install lint/dev dependencies."
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add provider keys before extraction work."
}

Write-Host "Windows setup complete."
