# Windows twin of scripts/bootstrap.sh: get a student from nothing to a
# working install, and say plainly what is missing.
#
# WRITTEN BUT NEVER RUN ON WINDOWS. It mirrors bootstrap.sh line for line and
# prints the same CALVIN_BOOTSTRAP line (same keys, same order) last, so the
# skill parses both identically. Report any failure rather than guessing.
#
# Idempotent: safe to run repeatedly.
#
# Run it with the execution policy bypassed for this one script, because a
# stock Windows machine refuses to run downloaded scripts:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
#
# Two modes, as in bootstrap.sh:
#   bootstrap.ps1
#       Cloned repository. The venv is .venv here and the project is this
#       repository.
#   bootstrap.ps1 -PluginData DIR [-Project DIR]
#       Installed as a Claude Code plugin. The venv goes in DIR (the plugin
#       data directory, which survives updates) and the student's workspace
#       goes in the project directory (default: the current directory).
param(
    [string]$PluginData = "",
    [string]$Project = ""
)

$ErrorActionPreference = "Continue"
$StartDir = (Get-Location).Path
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($PluginData) {
    $Mode = "plugin"
    New-Item -ItemType Directory -Force -Path $PluginData | Out-Null
    $Venv = Join-Path (Resolve-Path $PluginData).Path "venv"
    if (-not $Project) { $Project = $StartDir }
} else {
    $Mode = "clone"
    $Venv = Join-Path $Root ".venv"
    if (-not $Project) { $Project = $Root }
}
$VPy = Join-Path $Venv "Scripts\python.exe"

$Py = $null          # an argument list: the executable, then any launcher flags
$PyVersion = ""
$VenvOk = $false
$DepsOk = $false
$CliOk = $false
$RasterizerOk = $false
$TesseractOk = $false
$OcrEngine = "null"
$OcrVersion = "null"
$Needs = New-Object System.Collections.Generic.List[string]

function Say([string]$Text) { Write-Host $Text }
function JsonBool([bool]$Value) { if ($Value) { "true" } else { "false" } }
function JsonStr([string]$Value) { if ($Value) { '"' + $Value + '"' } else { "null" } }

# Run a candidate interpreter and return "major.minor", or $null. A bare
# python.exe on a stock machine is often the Microsoft Store stub, which opens
# the Store and prints nothing useful, so the version output is what decides.
function Get-PyVersion([string[]]$Cmd) {
    try {
        $exe = $Cmd[0]
        $rest = @()
        if ($Cmd.Length -gt 1) { $rest = $Cmd[1..($Cmd.Length - 1)] }
        $out = & $exe @rest -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$out" -match '^\s*(\d+)\.(\d+)\s*$') { return "$($Matches[1]).$($Matches[2])" }
    } catch { }
    return $null
}

function Test-Supported([string]$Version) {
    if (-not $Version) { return $false }
    $parts = $Version.Split(".")
    return ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)
}

# --- find an interpreter new enough to run this project ---------------------
# 3.10-3.12 first: the OCR engine's current release (1.4.x) ships for those
# only, and on 3.13+ pip can only resolve an older 1.2.x release. The py
# launcher is tried before PATH because it is what python.org installs.
# Plain strings split on a space: nested one-element arrays can be flattened
# by PowerShell, which would turn "python3" into a list of characters.
$Candidates = @(
    "py -3.12", "py -3.11", "py -3.10",
    "python3.12", "python3.11", "python3.10",
    "py -3.13", "py -3.14", "py -3",
    "python3", "python"
)
foreach ($candidate in $Candidates) {
    [string[]]$cmd = $candidate.Split(" ")
    if (-not (Get-Command $cmd[0] -ErrorAction SilentlyContinue)) { continue }
    $v = Get-PyVersion $cmd
    if (Test-Supported $v) { $Py = $cmd; $PyVersion = $v; break }
}

# uv may already hold a 3.12; use it without downloading if the best
# interpreter found is 3.13 or newer.
$HasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
if ($Py -and [int]$PyVersion.Split(".")[1] -ge 13 -and $HasUv) {
    $found = (& uv python find --no-python-downloads 3.12 2>$null)
    if ($LASTEXITCODE -eq 0 -and $found) { [string[]]$Py = @("$found".Trim()); $PyVersion = "3.12" }
}

if (-not $Py -and $HasUv) {
    Say "No Python 3.10+ found, but uv is available. Fetching one."
    & uv python install 3.12 *> $null
    if ($LASTEXITCODE -eq 0) {
        $found = (& uv python find 3.12 2>$null)
        if ($found) { [string[]]$Py = @("$found".Trim()); $PyVersion = "3.12" }
    }
}

# An existing venv keeps its interpreter; report that one, not the candidate.
if (Test-Path $VPy) {
    $existing = Get-PyVersion @($VPy)
    if ($existing) { $PyVersion = $existing }
}

if (-not $Py -and -not (Test-Path $VPy)) {
    Say "Could not find Python 3.10 or newer."
    Say "Install Python 3.12 from https://www.python.org/downloads/ and tick 'Add python.exe to PATH', then run this again."
    $Needs.Add('"python3.10+"')
    Write-Output ""
    Write-Output ('CALVIN_BOOTSTRAP {"mode":"' + $Mode + '","python":null,"venv":false,"deps":false,"cli":false,"pdf_rasterizer":false,"tesseract":false,"ocr_engine":null,"ocr_engine_version":null,"needs":[' + ($Needs -join ",") + ']}')
    exit 1
}
Say "Using Python $PyVersion"

# --- virtual environment ----------------------------------------------------
if (-not (Test-Path $VPy)) {
    Say "Creating the virtual environment."
    $exe = $Py[0]
    $rest = @()
    if ($Py.Length -gt 1) { $rest = $Py[1..($Py.Length - 1)] }
    & $exe @rest -m venv $Venv *> $null
}
if (Test-Path $VPy) { $VenvOk = $true }

if (-not $VenvOk) {
    Say "The virtual environment could not be created."
    $Needs.Add('"venv"')
} else {
    # --- dependencies --------------------------------------------------------
    # Editable, and re-run every time: in plugin mode Root moves on each
    # plugin update, and this re-points the venv at the current copy.
    Say "Installing dependencies. The first time downloads about 250 MB and can take several minutes."
    & $VPy -m pip install --quiet --upgrade pip *> $null
    & $VPy -m pip install --quiet -e "$($Root)[dev,ocr]" *> $null
    if ($LASTEXITCODE -eq 0) {
        $DepsOk = $true
    } else {
        Say "Dependency install failed. Re-run to retry; if it keeps failing, run the same command without --quiet to see why."
        $Needs.Add('"dependencies"')
    }
}

# --- skills, agents, launcher and workspace ---------------------------------
if ($DepsOk) {
    $setupArgs = @((Join-Path $Root "scripts\setup.py"), "--project-root", $Project, "--workspace", "workspace")
    if ($Mode -eq "plugin") { $setupArgs += "--plugin" }
    $setupErr = & $VPy @setupArgs 2>&1 | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] }
    if ($LASTEXITCODE -ne 0 -and $setupErr) { Say "$setupErr" }
    $launcher = Join-Path $Project ".calvin-autonomy\bin\coursework.cmd"
    if (Test-Path $launcher) {
        & $launcher --help *> $null
        if ($LASTEXITCODE -eq 0) { $CliOk = $true }
    }
    if (-not $CliOk) { $Needs.Add('"cli"') }
}

# --- optional capabilities --------------------------------------------------
if ($DepsOk) {
    & $VPy -c "import pypdfium2" *> $null
    if ($LASTEXITCODE -eq 0) { $RasterizerOk = $true }
    # The same probe the CLI uses, so this line and `doctor` cannot disagree.
    # Python re-serializes each value so the fragment below is valid JSON.
    $pick = "import json,subprocess,sys;" +
        "out=subprocess.run([sys.executable,'-m','engineering_assistant.ocr','--engine'],capture_output=True,text=True).stdout.strip().splitlines();" +
        "d=json.loads(out[-1]) if out else {};" +
        "print(json.dumps(d.get('engine')));print(json.dumps(d.get('version')))"
    $picked = @(& $VPy -c $pick 2>$null)
    if ($LASTEXITCODE -eq 0 -and $picked.Length -eq 2) {
        $OcrEngine = "$($picked[0])".Trim()
        $OcrVersion = "$($picked[1])".Trim()
    }
}
if (Get-Command tesseract -ErrorAction SilentlyContinue) { $TesseractOk = $true }

if ($OcrEngine -eq "null") {
    Say ""
    Say "Optional: scanned pages cannot be read automatically; no OCR engine is installed."
    Say "Scanned handouts will wait for you to confirm what they say."
    $Needs.Add('"ocr"')
}

Say ""
if ($CliOk) { Say "Ready." } else { Say "Not ready yet. See above." }

Write-Output ('CALVIN_BOOTSTRAP {"mode":"' + $Mode +
    '","python":' + (JsonStr $PyVersion) +
    ',"venv":' + (JsonBool $VenvOk) +
    ',"deps":' + (JsonBool $DepsOk) +
    ',"cli":' + (JsonBool $CliOk) +
    ',"pdf_rasterizer":' + (JsonBool $RasterizerOk) +
    ',"tesseract":' + (JsonBool $TesseractOk) +
    ',"ocr_engine":' + $OcrEngine +
    ',"ocr_engine_version":' + $OcrVersion +
    ',"needs":[' + ($Needs -join ",") + ']}')

if ($CliOk) { exit 0 } else { exit 1 }
