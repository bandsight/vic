param(
    [string]$Profile = "runtime_code",
    [string]$OutputDir = "exports\portable",
    [switch]$IncludeDependencyBundle
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$AllowedProfiles = @("runtime_code", "with_governed_data", "with_source_evidence")
if ($AllowedProfiles -notcontains $Profile) {
    throw "Unknown profile: $Profile. Allowed profiles: $($AllowedProfiles -join ', ')"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$PackageName = "eba-workbench-$Profile-$Timestamp.zip"
$OutputPath = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
$ZipPath = Join-Path $OutputPath $PackageName

$ExcludeRegex = @(
    '\\.env$',
    '\\.git(\\|$)',
    '\\.venv(\\|$)',
    '\\.venv-win(\\|$)',
    '\\node_modules(\\|$)',
    '\\__pycache__(\\|$)',
    '\\.pytest_cache(\\|$)',
    '\\cache(\\|$)',
    '\\llm-bundle(\\|$)',
    '\\llm-bundle\.zip$',
    '\\artifacts(\\|$)',
    '\\exports(\\|$)',
    '\\var(\\|$)',
    'uvicorn-.*\.log$',
    '\.pyc$'
) -join '|'

$IncludeDataRegex = $null
if ($Profile -eq "with_governed_data") {
    $IncludeDataRegex = '\\(canonical|registers|scenario-overrides)(\\|$)|\\data\\analysis(\\|$)|\\data\\bronze\\phase1_source_build\\candidate_agreements(\\|$)'
} elseif ($Profile -eq "with_source_evidence") {
    $IncludeDataRegex = '\\(canonical|registers|scenario-overrides)(\\|$)|\\data\\analysis(\\|$)|\\data\\bronze\\phase1_source_build\\candidate_agreements(\\|$)|\\documents\\immutable(\\|$)'
}

$Temp = Join-Path ([System.IO.Path]::GetTempPath()) "eba-workbench-package-$Timestamp"
if (Test-Path $Temp) {
    Remove-Item -Recurse -Force $Temp
}
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
$RootPath = (Resolve-Path $Root).Path.TrimEnd('\')

try {
    Get-ChildItem -Force -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($RootPath.Length).TrimStart('\')
        $relForMatch = "\" + $rel
        if (-not $IncludeDependencyBundle -and $relForMatch -match '\\vendor(\\|$)') {
            return
        }
        if ($relForMatch -match $ExcludeRegex) {
            return
        }
        if ($Profile -eq "runtime_code") {
            $isRuntimeAssetManifest = $relForMatch -match '\\data\\analysis\\[^\\]+\.asset\.json$'
            if ($relForMatch -match '\\(canonical|registers|scenario-overrides|documents\\immutable)(\\|$)|\\data\\analysis(\\|$)|\\data\\bronze(\\|$)') {
                if (-not $isRuntimeAssetManifest) {
                    return
                }
            }
        } elseif ($IncludeDataRegex -and $relForMatch -match '\\documents\\immutable(\\|$)' -and $Profile -ne "with_source_evidence") {
            return
        }
        $target = Join-Path $Temp $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
    Compress-Archive -Path (Join-Path $Temp '*') -DestinationPath $ZipPath -Force
} finally {
    if (Test-Path $Temp) {
        Remove-Item -Recurse -Force $Temp
    }
}

Write-Host "Created portable package: $ZipPath"
