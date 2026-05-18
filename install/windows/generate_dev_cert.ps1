param(
    [Parameter(Mandatory = $true)]
    [string[]]$PythonCommand,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClientRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$ConfigDir = Join-Path $ClientRoot "config"
$CertDir = Join-Path $ConfigDir "certificate\local"
$CaCertPath = Join-Path $CertDir "ca.crt"
$CaKeyPath = Join-Path $CertDir "ca.key"
$CertPath = Join-Path $CertDir "cert.pem"
$KeyPath = Join-Path $CertDir "key.pem"

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

if ((-not $Force) -and (Test-Path $CaCertPath) -and (Test-Path $CertPath) -and (Test-Path $KeyPath)) {
    Write-Host "TLS files already exist, keeping current local CA and relay certificate"
    exit 0
}

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

$HostNameValue = [System.Net.Dns]::GetHostName()
$ShortHostName = $HostNameValue.Split(".")[0]

$PythonCode = @'
import datetime
import ipaddress
import pathlib
import sys

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ModuleNotFoundError as error:
    raise SystemExit(
        "cryptography is required to generate TLS certificates on Windows. "
        "Install dependencies first."
    ) from error

ca_cert_path = pathlib.Path(sys.argv[1])
ca_key_path = pathlib.Path(sys.argv[2])
cert_path = pathlib.Path(sys.argv[3])
key_path = pathlib.Path(sys.argv[4])
hostname = sys.argv[5]
short_hostname = sys.argv[6]

ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ca_subject = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "RHCR Local Relay CA"),
])

ca_certificate = (
    x509.CertificateBuilder()
    .subject_name(ca_subject)
    .issuer_name(ca_subject)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(minutes=5))
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .sign(private_key=ca_key, algorithm=hashes.SHA256())
)

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
])
sans = [
    x509.DNSName("localhost"),
    x509.DNSName(hostname),
    x509.DNSName(short_hostname),
    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    x509.IPAddress(ipaddress.IPv6Address("::1")),
]

certificate = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(ca_subject)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(minutes=5))
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
    .add_extension(x509.SubjectAlternativeName(sans), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
        critical=False,
    )
    .sign(private_key=ca_key, algorithm=hashes.SHA256())
)

ca_cert_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
ca_key_path.write_bytes(
    ca_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
key_path.write_bytes(
    key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
'@

$PythonScript = [System.IO.Path]::Combine(
    [System.IO.Path]::GetTempPath(),
    "teleprogram_cert_{0}.py" -f ([System.Guid]::NewGuid().ToString("N"))
)

try {
    Set-Content -Path $PythonScript -Value $PythonCode -Encoding UTF8
    Invoke-CommandArray -Command $PythonCommand -Arguments @(
        $PythonScript,
        $CaCertPath,
        $CaKeyPath,
        $CertPath,
        $KeyPath,
        $HostNameValue,
        $ShortHostName
    )
}
finally {
    if (Test-Path $PythonScript) {
        Remove-Item $PythonScript -Force
    }
}

Write-Host "Generated $CaCertPath, $CertPath, and $KeyPath"
