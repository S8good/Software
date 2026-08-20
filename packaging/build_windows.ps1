[CmdletBinding()]
param(
    [string]$Python = $env:NANOSENSE_PYTHON,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "C:\ProgramData\anaconda3\envs\py39\python.exe"
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

$distRoot = Join-Path $root "dist"
$portableRoot = Join-Path $distRoot "portable\NanoSense"
$portableZip = Join-Path $distRoot "NanoSense-Portable.zip"
$installerOutput = Join-Path $distRoot "installer\NanoSense-Setup.exe"

Push-Location $root
try {
    & $Python -m PyInstaller (Join-Path $root "packaging\nanosense.spec") --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $frozenExe = Join-Path $distRoot "NanoSense\NanoSense.exe"
    if (-not (Test-Path -LiteralPath $frozenExe)) {
        throw "PyInstaller output missing: $frozenExe"
    }

    if (Test-Path -LiteralPath $portableRoot) {
        Remove-Item -LiteralPath $portableRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path (Split-Path $portableRoot) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $distRoot "NanoSense") -Destination $portableRoot -Recurse

    if (Test-Path -LiteralPath $portableZip) {
        Remove-Item -LiteralPath $portableZip -Force
    }
    Compress-Archive -Path $portableRoot -DestinationPath $portableZip -CompressionLevel Optimal

    if (-not $SkipInstaller) {
        $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
        if ($null -eq $iscc) {
            $candidates = @(
                "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
            ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
            if ($candidates.Count -gt 0) {
                $iscc = Get-Item -LiteralPath $candidates[0]
            }
        }
        if ($null -eq $iscc) {
            throw "Inno Setup compiler not found. Install Inno Setup 6 or pass -SkipInstaller."
        }

        & $iscc.Source (Join-Path $root "packaging\NanoSense.iss")
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed with exit code $LASTEXITCODE"
        }
        if (-not (Test-Path -LiteralPath $installerOutput)) {
            throw "Inno Setup output missing: $installerOutput"
        }
    }
}
finally {
    Pop-Location
}
