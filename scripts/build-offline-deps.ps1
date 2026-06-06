param(
    [string]$Python = "py -3.12",
    [string]$OutputDir = "vendor",
    [switch]$WithBrowser,
    [switch]$WithNodeTools,
    [switch]$PipTrustedHost,
    [switch]$NpmUseSystemCa,
    [switch]$NpmStrictSslFalse
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Quote-CommandArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -match '[\s"]') {
        return '"' + $Value.Replace('"', '\"') + '"'
    }
    return $Value
}

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
    param([Parameter(Mandatory = $true)][string]$CommandLine)

    Invoke-Expression $CommandLine
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $CommandLine"
    }
}

function Invoke-PythonCommand {
    param([Parameter(Mandatory = $true)][string[]]$ArgumentList)

    $command = "$Python " + (($ArgumentList | ForEach-Object { Quote-CommandArgument $_ }) -join " ")
    Invoke-NativeExpression $command
}

$OutputPath = $OutputDir
if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $Root $OutputPath
}
$WheelhousePath = Join-Path $OutputPath "python-wheels"
$NpmCachePath = Join-Path $OutputPath "npm-cache"
New-Item -ItemType Directory -Force -Path $WheelhousePath | Out-Null

$PipSourceArgs = @()
if ($PipTrustedHost) {
    $PipSourceArgs = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")
}

Invoke-PythonCommand (@("-m", "pip", "download") + $PipSourceArgs + @("--dest", $WheelhousePath, "-r", "requirements-dev.txt"))

if ($WithBrowser) {
    Invoke-PythonCommand (@("-m", "pip", "download") + $PipSourceArgs + @("--dest", $WheelhousePath, "-r", "requirements-browser.txt"))
}

if ($WithNodeTools -and (Test-Path "package.json")) {
    New-Item -ItemType Directory -Force -Path $NpmCachePath | Out-Null
    $NpmArgs = @("ci", "--no-audit", "--no-fund", "--prefer-offline", "--cache", $NpmCachePath)
    if (-not (Test-Path "package-lock.json")) {
        $NpmArgs = @("install", "--no-audit", "--no-fund", "--prefer-offline", "--cache", $NpmCachePath)
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
}

$manifest = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    platform = "windows"
    python_command = $Python
    wheelhouse = (Resolve-Path $WheelhousePath).Path
    requirements = @("requirements-dev.txt")
    with_browser = [bool]$WithBrowser
    with_node_tools = [bool]$WithNodeTools
    npm_cache = if (Test-Path $NpmCachePath) { (Resolve-Path $NpmCachePath).Path } else { $null }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputPath "dependency-bundle.json") -Encoding UTF8

Write-Host "Offline dependency bundle prepared under: $OutputPath"
