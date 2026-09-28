# Build από καθαρό Windows x64 περιβάλλον με Python 3.14.
# Δεν χρησιμοποιούμε το development .venv ούτε αλλάζουμε τα global packages.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath '.build-venv\Scripts\python.exe')) {
    python -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create build environment' }
}
& .\.build-venv\Scripts\python.exe -m pip install -r build-requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.build-venv\Scripts\python.exe -c "from eyedesk.models import ensure_models; ensure_models()"
if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed' }
& .\.build-venv\Scripts\python.exe export_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License export failed' }
& .\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm DeskEye.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Copy-Item -LiteralPath README.md,THIRD_PARTY_NOTICES.md -Destination dist\DeskEye
Copy-Item -LiteralPath licenses -Destination dist\DeskEye -Recurse -Force
Write-Host 'Build complete: dist\DeskEye\DeskEye.exe. Distribute the entire folder.'
