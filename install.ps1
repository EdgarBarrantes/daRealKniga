# Installs daRealKniga on Windows into .\.venv (run from the repository folder, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Tesseract (and DjVuLibre, for DjVu input) are installed separately; see the README.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = if ($env:PYTHON) { $env:PYTHON } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$pyArgs = if ($py -eq "py") { @("-3.12") } else { @() }
& $py @pyArgs -c "import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 13), 'Python 3.10 to 3.13 required'"
if (-not (Test-Path .venv)) { & $py @pyArgs -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
.\.venv\Scripts\python.exe -m pip install --prefer-binary -e ".[gui]"
Write-Host ""
.\.venv\Scripts\darealkniga.exe doctor
$bin = (Resolve-Path .venv\Scripts).Path
Write-Host @"

Installed. Commands are in $bin
  $bin\darealkniga-gui.exe                     the window
  $bin\darealkniga.exe make document.pdf --lang bul+eng
  $bin\drk.exe ...                               short form, same command
To type just 'darealkniga' or 'drk' anywhere, add that folder to your PATH:
  [Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';$bin', 'User')
Missing Tesseract?  winget install UB-Mannheim.TesseractOCR
"@
