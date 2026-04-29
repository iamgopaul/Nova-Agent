# GAAIA — Windows PowerShell launcher
# Auto-installs Python 3.12+, pnpm, and project dependencies on first run.
# Usage:  ./run.ps1
#
# Why "Continue" and not "Stop": Windows PowerShell 5.1 wraps every line a
# native command writes to stderr in a NativeCommandError record, even on
# exit code 0. Combined with `Stop`, that halts the script on harmless
# informational output (e.g. python's `# total=23 models` summary). The
# script already checks `$LASTEXITCODE` after each native call, so explicit
# failure handling is unaffected.
$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $RootDir

$VenvPy = Join-Path $RootDir ".venv\Scripts\python.exe"

function Log([string]$msg) { Write-Host "[GAAIA] $msg" }
function Err([string]$msg) { Write-Host "[GAAIA] ERROR: $msg" -ForegroundColor Red }

# ── Cross-platform port killer ────────────────────────────────────────────────
function Stop-Port([int]$port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
    } catch {
        return
    }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { return }
    Log "Clearing port $port (PID: $($pids -join ', '))"
    foreach ($procId in $pids) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
    }
}

8765, 3000, 3001, 3002 | ForEach-Object { Stop-Port $_ }

# ── Find Python 3.12+ (install via winget if missing) ─────────────────────────
function Test-Python312Plus([string]$exe) {
    if (-not $exe) { return $false }
    try {
        $ver = & $exe -c "import sys; print(sys.version_info[0]*100 + sys.version_info[1])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $ver) { return $false }
        return ([int]$ver -ge 312)
    } catch { return $false }
}

function Find-Python {
    $candidates = @(
        "$env:USERPROFILE\AppData\Local\Programs\Python\Python313\python.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python313\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($c in $candidates) {
        if ((Test-Path $c) -and (Test-Python312Plus $c)) { return $c }
    }
    # Try PATH
    foreach ($name in @("python3.13", "python3.12", "python3", "python")) {
        $found = (Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1).Source
        if ($found -and (Test-Python312Plus $found)) { return $found }
    }
    # Try py launcher
    $py = (Get-Command py -ErrorAction SilentlyContinue).Source
    if ($py) {
        foreach ($v in @("-3.13", "-3.12")) {
            try {
                $real = & $py $v -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $real -and (Test-Python312Plus $real)) { return $real }
            } catch {}
        }
    }
    return $null
}

function Install-Python {
    Log "Python 3.12+ not found — installing via winget..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Err "winget unavailable. Install Python 3.12 manually: https://www.python.org/downloads/"
        exit 1
    }
    # winget exits non-zero when the package is already installed; tolerate it.
    & winget install --id Python.Python.3.12 --silent `
        --accept-package-agreements --accept-source-agreements --scope user
    $global:LASTEXITCODE = 0
}

$PyCmd = Find-Python
if (-not $PyCmd) {
    Install-Python
    $PyCmd = Find-Python
    if (-not $PyCmd) {
        Err "Python 3.12+ install completed but interpreter not found. Open a new terminal and re-run."
        exit 1
    }
}
$pyVerOut = & $PyCmd -c "import sys; print(sys.version.split()[0])"
Log "Using Python: $PyCmd ($pyVerOut)"

# ── Create / refresh venv ─────────────────────────────────────────────────────
$needsRecreate = $true
if (Test-Path $VenvPy) {
    if (Test-Python312Plus $VenvPy) { $needsRecreate = $false }
    else { Log "Existing venv is older than Python 3.12 — recreating." }
}
if ($needsRecreate) {
    if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
    Log "Creating Python virtual environment..."
    & $PyCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) { Err "venv creation failed."; exit 1 }
}

# ── Install Python deps if pyproject.toml changed since last install ──────────
$Stamp = Join-Path $RootDir ".venv\.gaaia_install_stamp"
$Pyproject = Join-Path $RootDir "pyproject.toml"
$needsInstall = $true
if (Test-Path $Stamp) {
    $stampTime = (Get-Item $Stamp).LastWriteTime
    $pyTime = (Get-Item $Pyproject).LastWriteTime
    if ($pyTime -le $stampTime) { $needsInstall = $false }
}
if ($needsInstall) {
    Log "Installing Python dependencies (this can take 5-15 min on first run)..."
    & $VenvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Err "pip upgrade failed."; exit 1 }
    & $VenvPy -m pip install -e ".[imagegen,docgen,musicgen]"
    if ($LASTEXITCODE -ne 0) { Err "Python dependency install failed."; exit 1 }
    New-Item -ItemType File -Path $Stamp -Force | Out-Null
    Log "Python dependencies ready."
}

# ── Upgrade torch to a CUDA build if an NVIDIA GPU is present ────────────────
# pip ships the CPU build by default on Windows; if a CUDA GPU exists, swap once
# so SDXL image gen and any future torch-backed inference use the GPU.
function Initialize-CudaTorch {
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { return }
    try { & nvidia-smi -L | Out-Null } catch { return }
    if ($LASTEXITCODE -ne 0) { $global:LASTEXITCODE = 0; return }

    $cudaCheck = & $VenvPy -c "import torch; print('ok' if torch.cuda.is_available() else 'no')" 2>$null
    $global:LASTEXITCODE = 0
    if ($cudaCheck -and $cudaCheck.Trim() -eq "ok") { return }

    Log "NVIDIA GPU detected but torch is CPU-only - swapping to CUDA build (~2.5 GB download)..."
    & $VenvPy -m pip install --upgrade --force-reinstall `
        torch torchvision torchaudio `
        --index-url https://download.pytorch.org/whl/cu124
    if ($LASTEXITCODE -ne 0) {
        Log "Warning: CUDA torch install failed - image gen will stay on CPU. (Try cu118 if your driver is old.)"
        $global:LASTEXITCODE = 0
    }
}
Initialize-CudaTorch

# ── Frontend: pnpm (matches scripts/run_local_app.py) ─────────────────────────
function Initialize-Pnpm {
    if (Get-Command pnpm -ErrorAction SilentlyContinue) { return }
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Log "pnpm not found — installing via npm..."
        & npm install -g pnpm
        if ($LASTEXITCODE -ne 0) { Err "pnpm install failed."; exit 1 }
        return
    }
    Err "Node.js not installed. Install Node 20+ from https://nodejs.org, then re-run."
    exit 1
}
Initialize-Pnpm

$PkgJson = Join-Path $RootDir "frontend\package.json"
$NodeStamp = Join-Path $RootDir "frontend\node_modules\.gaaia_install_stamp"
$needsFrontend = $true
if ((Test-Path $NodeStamp) -and (Test-Path (Join-Path $RootDir "frontend\node_modules"))) {
    if ((Get-Item $PkgJson).LastWriteTime -le (Get-Item $NodeStamp).LastWriteTime) {
        $needsFrontend = $false
    }
}
if ($needsFrontend) {
    Log "Installing frontend dependencies..."
    Push-Location (Join-Path $RootDir "frontend")
    try {
        & pnpm install
        if ($LASTEXITCODE -ne 0) { Err "pnpm install failed."; exit 1 }
    } finally { Pop-Location }
    New-Item -ItemType File -Path $NodeStamp -Force | Out-Null
    Log "Frontend dependencies ready."
}

# ── Unified memory tier (RAM + VRAM) for Ollama tuning ───────────────────────
# Probe RAM via psutil and VRAM via gaaia.services.hardware so the launcher's
# tier picker matches what the in-process model router will compute.
# NOTE: keep all string literals inside this script SINGLE-QUOTED. Windows
# PowerShell's native-command parser strips double quotes when forwarding a
# multi-line `-c` argument to python.exe, which would turn `"."` into `.` and
# crash with `SyntaxError: invalid syntax`.
$probeScript = @'
import psutil, sys
sys.path.insert(0, '.')
from gaaia.services.hardware import is_apple_silicon, nvidia_vram_gb, amd_vram_gb
m = psutil.virtual_memory()
apple = is_apple_silicon()
vram = 0.0 if apple else (nvidia_vram_gb() + amd_vram_gb())
print(int(m.available/1024**3), int(m.total/1024**3), int(vram), int(apple))
'@
$ramOut = & $VenvPy -c $probeScript 2>$null
if (-not $ramOut) { $ramOut = "8 16 0 0" }
$ramParts = $ramOut.Trim().Split()
$AvailRamGb = [int]$ramParts[0]
$TotalRamGb = [int]$ramParts[1]
$VramGb     = [int]$ramParts[2]
$Apple      = [int]$ramParts[3]

if ($Apple -eq 1) {
    $BudgetGb = $AvailRamGb
    Log "Memory: $AvailRamGb GB available / $TotalRamGb GB total (Apple Silicon unified)"
} else {
    $BudgetGb = $AvailRamGb + $VramGb
    if ($VramGb -gt 0) {
        Log "Memory: $AvailRamGb GB RAM available + $VramGb GB VRAM = $BudgetGb GB budget"
    } else {
        Log "Memory: $AvailRamGb GB RAM available (no GPU detected)"
    }
}

if     ($BudgetGb -lt 3)  { $RamTier = "critical"; $MaxModels = 1; $NumParallel = 1 }
elseif ($BudgetGb -lt 7)  { $RamTier = "moderate"; $MaxModels = 2; $NumParallel = 1 }
elseif ($BudgetGb -lt 24) { $RamTier = "ok";       $MaxModels = 3; $NumParallel = 2 }
else                      { $RamTier = "generous"; $MaxModels = 4; $NumParallel = 4 }
Log "Memory tier: $RamTier"

# Silence the harmless HuggingFace warning about Windows lacking symlinks (Kokoro cache).
if (-not $env:HF_HUB_DISABLE_SYMLINKS_WARNING) { $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1" }

if (-not $env:OLLAMA_NUM_PARALLEL)       { $env:OLLAMA_NUM_PARALLEL = "$NumParallel" }
if (-not $env:OLLAMA_MAX_LOADED_MODELS)  { $env:OLLAMA_MAX_LOADED_MODELS = "$MaxModels" }
if (-not $env:OLLAMA_FLASH_ATTENTION)    { $env:OLLAMA_FLASH_ATTENTION = "1" }
# KV-cache quantization halves the per-token KV memory at near-zero quality
# cost (q8_0). Critical for tight-VRAM systems running long contexts.
# Requires OLLAMA_FLASH_ATTENTION=1.
if (-not $env:OLLAMA_KV_CACHE_TYPE)      { $env:OLLAMA_KV_CACHE_TYPE = "q8_0" }
if (-not $env:OLLAMA_GPU_OVERHEAD)       { $env:OLLAMA_GPU_OVERHEAD = "0" }
if (-not $env:OLLAMA_NOPRUNE)            { $env:OLLAMA_NOPRUNE = "0" }
Log "Ollama: parallel=$($env:OLLAMA_NUM_PARALLEL)  max_models=$($env:OLLAMA_MAX_LOADED_MODELS)  flash_attn=$($env:OLLAMA_FLASH_ATTENTION)  kv_cache=$($env:OLLAMA_KV_CACHE_TYPE)  memory_tier=$RamTier"

# ── Ollama: install, start, and pull a starter model if none exist ────────────
function Test-OllamaApi {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

function Initialize-Ollama {
    $ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if (Test-Path $ollamaDir) { $env:PATH = "$ollamaDir;$env:PATH" }

    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Log "Ollama not found — installing via winget..."
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Err "winget unavailable. Install Ollama from https://ollama.com/download"
            return
        }
        & winget install --id Ollama.Ollama --silent `
            --accept-package-agreements --accept-source-agreements --scope user
        $global:LASTEXITCODE = 0
        if (Test-Path $ollamaDir) { $env:PATH = "$ollamaDir;$env:PATH" }
    }
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Err "Ollama installed but not on PATH. Open a new terminal and re-run."
        return
    }

    if (-not (Test-OllamaApi)) {
        Log "Starting Ollama service..."
        $trayApp = Join-Path $ollamaDir "ollama app.exe"
        if (Test-Path $trayApp) {
            Start-Process -FilePath $trayApp -WindowStyle Hidden | Out-Null
        } else {
            Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        }
        for ($i = 0; $i -lt 15; $i++) {
            if (Test-OllamaApi) { break }
            Start-Sleep -Seconds 1
        }
    }
    if (-not (Test-OllamaApi)) {
        Log "Warning: Ollama did not respond on 127.0.0.1:11434 — chat may not work."
        return
    }

    # Pull only the models that fit this host's memory budget. The router auto-promotes
    # to bigger models if they later become available — so upgrading RAM/GPU and re-running
    # this script will pull the additional models without any other config changes.
    # Override with $env:GAAIA_PULL_ALL = "1" to pull every model regardless of fit (archival).
    $modelStamp = Join-Path $RootDir ".venv\.gaaia_models_stamp"
    $modeFlag  = $null
    $modeLabel = "adaptive - only models that fit this host"
    if ($env:GAAIA_PULL_ALL -eq "1") {
        $modeFlag  = "--no-ram-filter"
        $modeLabel = "all models (GAAIA_PULL_ALL=1) - includes models too big for this host"
    }

    # Compute desired set. Stamp stores this list so re-runs re-pull when either the
    # hardware budget grows OR _ROLE_FALLBACKS changes.
    $listScript = Join-Path $RootDir "scripts\list_pullable_models.py"
    $desired = if ($modeFlag) {
        & $VenvPy $listScript $modeFlag 2>$null
    } else {
        & $VenvPy $listScript 2>$null
    }
    $desiredText = (($desired | Where-Object { $_ }) -join "`n")

    $stampText = ""
    if (Test-Path $modelStamp) {
        $stampText = (Get-Content $modelStamp -Raw -ErrorAction SilentlyContinue).Trim()
    }

    if ($stampText -eq $desiredText -and $stampText) {
        Log "Models up to date with host budget (mode: $modeLabel)."
    } else {
        Log "Pulling models - mode: $modeLabel"
        $failures = 0
        foreach ($m in $desired) {
            $m = $m.Trim()
            if (-not $m) { continue }
            Log "  -> ollama pull $m"
            & ollama pull $m
            if ($LASTEXITCODE -ne 0) { $failures++; Log "  x failed: $m" }
        }
        if ($failures -eq 0) {
            $desiredText | Set-Content -Path $modelStamp -Encoding utf8 -NoNewline
            Log "All models pulled."
        } else {
            Log "Done with $failures failed pull(s); stamp not written so we'll retry next run."
        }
    }
}
Initialize-Ollama

# ── Prefetch MediaPipe asset so the first camera frame is instant ─────────────
Log "Prefetching vision models..."
& $VenvPy (Join-Path $RootDir "scripts\ensure_models.py")
if ($LASTEXITCODE -ne 0) { Log "Warning: model prefetch failed — will retry when the camera runs." }

# ── Launch backend + frontend ─────────────────────────────────────────────────
& $VenvPy (Join-Path $RootDir "scripts\run_local_app.py")
exit $LASTEXITCODE
