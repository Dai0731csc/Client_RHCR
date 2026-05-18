param(
    [string]$PythonExe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClientRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

function Invoke-CommandArray {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command,
        [string[]]$Arguments = @()
    )

    if ($Command.Count -gt 1) {
        & $Command[0] $Command[1..($Command.Count - 1)] @Arguments
    }
    else {
        & $Command[0] @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
}

function Resolve-PythonCommand {
    param([string]$ExplicitPython)

    if ($ExplicitPython) {
        if ($ExplicitPython -eq "py") {
            return @("py", "-3.11")
        }
        return @($ExplicitPython)
    }

    $VenvPython = Join-Path $ClientRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        return @($VenvPython)
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3.11")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python 3.11 executable not found. Pass -PythonExe or create .venv first."
}

$PythonCommand = Resolve-PythonCommand -ExplicitPython $PythonExe
Invoke-CommandArray -Command $PythonCommand -Arguments @(
    "-c",
    "import sys; assert sys.version_info[:2] == (3, 11), 'Python 3.11 is required'"
)

$VerifyCode = @'
import importlib

required = ["aiohttp", "jinja2", "numpy", "scipy"]
bundled = ["aiortc", "cv2"]

for name in required:
    importlib.import_module(name)
    print(f"[ok] required package: {name}")

for name in bundled:
    importlib.import_module(name)
    print(f"[ok] bundled package: {name}")
'@

$VerifyScript = [System.IO.Path]::Combine(
    [System.IO.Path]::GetTempPath(),
    "teleprogram_verify_{0}.py" -f ([System.Guid]::NewGuid().ToString("N"))
)

try {
    Set-Content -Path $VerifyScript -Value $VerifyCode -Encoding UTF8

    Write-Host "Checking required Python packages"
    Invoke-CommandArray -Command $PythonCommand -Arguments @($VerifyScript)

    Write-Host "Checking TLS files"
    foreach ($Path in @(
        (Join-Path $ClientRoot "config\certificate\local\ca.crt"),
        (Join-Path $ClientRoot "config\certificate\local\cert.pem"),
        (Join-Path $ClientRoot "config\certificate\local\key.pem")
    )) {
        if (-not (Test-Path $Path)) {
            throw "Missing TLS file: $Path"
        }
        Write-Host "[ok] $Path"
    }

    Write-Host "Compiling Python sources"
    Invoke-CommandArray -Command $PythonCommand -Arguments @(
        "-m", "compileall",
        (Join-Path $ClientRoot "main.py"),
        (Join-Path $ClientRoot "backend")
    )

    Write-Host "Checking application import"
    Push-Location $ClientRoot
    try {
        Invoke-CommandArray -Command $PythonCommand -Arguments @(
            "-c",
            "from backend import create_app; create_app(); print('[ok] create_app')"
        )
    }
    finally {
        Pop-Location
    }
}
finally {
    if (Test-Path $VerifyScript) {
        Remove-Item $VerifyScript -Force
    }
}

Write-Host ""
Write-Host "Environment verification complete."
