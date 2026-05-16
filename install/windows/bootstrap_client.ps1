param(
    [string]$PythonExe = "",
    [string]$Venv = "prompt",
    [switch]$ForceCert
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
        return @($ExplicitPython)
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3.11")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python 3.11 executable not found. Install Python 3.11 or pass -PythonExe."
}

function Normalize-VenvAnswer {
    param([string]$Value)

    switch ($Value.Trim().ToLowerInvariant()) {
        "yes" { return "yes" }
        "y" { return "yes" }
        "no" { return "no" }
        "n" { return "no" }
        default { throw "Please answer yes or no." }
    }
}

$PythonCommand = Resolve-PythonCommand -ExplicitPython $PythonExe
$PythonCommandText = $PythonCommand -join " "
Write-Host "Using Python: $($PythonCommand -join ' ')"
Invoke-CommandArray -Command $PythonCommand -Arguments @(
    "-c",
    "import sys; assert sys.version_info[:2] == (3, 11), 'Python 3.11 is required'"
)

if ($Venv -eq "prompt") {
    $Venv = Read-Host "Do you want to install a Python 3.11 virtual environment? (yes/no)"
}

$Venv = Normalize-VenvAnswer -Value $Venv

if ($Venv -eq "yes") {
    $VenvDir = Join-Path $ClientRoot ".venv"
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"

    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating virtual environment at $VenvDir"
        Invoke-CommandArray -Command $PythonCommand -Arguments @("-m", "venv", $VenvDir)
    }

    $ActivePythonCommand = @($VenvPython)
}
else {
    Write-Host "Skipping virtual environment installation"
    $ActivePythonCommand = $PythonCommand
}

Write-Host "Upgrading pip tooling"
Invoke-CommandArray -Command $ActivePythonCommand -Arguments @(
    "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"
)

Write-Host "Installing dependencies"
Invoke-CommandArray -Command $ActivePythonCommand -Arguments @(
    "-m", "pip", "install", "-r", (Join-Path $ClientRoot "install\requirements.txt")
)

$CertArguments = @("-PythonCommand") + $ActivePythonCommand
if ($ForceCert) {
    $CertArguments += "-Force"
}

& (Join-Path $ScriptDir "generate_dev_cert.ps1") @CertArguments

Write-Host ""
Write-Host "Bootstrap complete."
if ($Venv -eq "yes") {
    Write-Host "Activate venv: .\.venv\Scripts\Activate.ps1"
    Write-Host "Verify env:    .\install\windows\verify_client.ps1"
    Write-Host "Run client:    .\.venv\Scripts\python.exe main.py"
}
else {
    Write-Host "Verify env:    .\install\windows\verify_client.ps1"
    Write-Host "Run client:    $PythonCommandText main.py"
}
