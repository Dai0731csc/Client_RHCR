# Client Install

Bootstrap scripts for a fresh machine.

## Quick start

macOS / Linux:

```bash
./install/unix/bootstrap_client.sh
```

The script asks whether to create a `Python 3.11` virtual environment.

- Answer `yes`: create and use `client/.venv`
- Answer `no`: skip `.venv` and install with `python3.11` directly

Windows PowerShell:

```powershell
.\install\windows\bootstrap_client.ps1
```

If PowerShell blocks local scripts, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install\windows\bootstrap_client.ps1
```

If you want to skip creating `.venv` and use a specific Python 3.11 interpreter, pass it explicitly:

```powershell
.\install\windows\bootstrap_client.ps1 -PythonExe "C:\path\to\python.exe" -Venv no
```

Verify the environment:

```bash
./install/unix/verify_client.sh
```

```powershell
.\install\windows\verify_client.ps1
```

Run the client:

```bash
.venv/bin/python main.py
```

```powershell
.\.venv\Scripts\python.exe main.py
```

If you answered `no`, run:

```bash
python3.11 main.py
```

```powershell
py -3.11 main.py
```

Or, if you skipped `.venv` and want to use a specific interpreter:

```powershell
.\install\windows\verify_client.ps1 -PythonExe "C:\path\to\python.exe"
"C:\path\to\python.exe" main.py
```

## What the bootstrap script does

- Creates `client/.venv` when you answer `yes`
- Installs `install/requirements.txt`
- Generates `config/certificate/local/ca.crt`, `cert.pem`, and `key.pem` if needed
- On Windows, installs `cryptography`, which `generate_dev_cert.ps1` uses to create the local CA and relay certificate
- Uses one shared Unix implementation for macOS and Linux

## Notes

- `cloud.json` is not created or validated by these scripts. Place your config at `config/cloud.json` before the first run.
- After the client is running, open `https://<host>:8000/settings` to change transport mode without restarting the process.
- Use `--force-cert` to regenerate local relay TLS files.
- To regenerate certificates manually on Windows, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install\windows\generate_dev_cert.ps1 -PythonCommand python
```
