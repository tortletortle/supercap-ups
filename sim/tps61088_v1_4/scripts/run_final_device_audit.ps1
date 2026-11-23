param(
    [string]$LtspiceExe = "",
    [string]$Compare25Summary = "",
    [switch]$Skip12p5,
    [switch]$SkipMatrix,
    [switch]$SkipDynamic
)

$ErrorActionPreference = "Stop"
$V14Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $V14Root "..\..")).Path
$DiagnosticsDir = Join-Path $V14Root "diagnostics"
$NetlistsDir = Join-Path $V14Root "netlists"
$ResultsRoot = Join-Path $V14Root "results\final_device_audit"
$ModelPath = Join-Path $V14Root "..\tps61088_v1_3\model\TPS61088_LT.LIB"
$Analyzer = Join-Path $PSScriptRoot "analyze_fsw_internal.py"
$DynamicGenerator = Join-Path $PSScriptRoot "generate_dynamic_cases.py"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunRoot = Join-Path $ResultsRoot $Timestamp

function Resolve-Ltspice {
    param([string]$Requested)
    if ($Requested) {
        if (-not (Test-Path -LiteralPath $Requested -PathType Leaf)) {
            throw "LTspice executable not found: $Requested"
        }
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\ADI\LTspice\LTspice.exe"),
        (Join-Path $env:ProgramFiles "ADI\LTspice\LTspice.exe"),
        (Join-Path ([Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) "ADI\LTspice\LTspice.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    if (-not $candidates) {
        throw "LTspice.exe was not auto-detected. Pass -LtspiceExe <absolute path>."
    }
    return (Resolve-Path -LiteralPath $candidates[0]).Path
}

function Get-Sha256 {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return ""
}

function Read-Measurements {
    param([string]$LogPath)
    $names = @(
        "t90", "t98", "sw_t6001", "sw_t6101", "f_sw_khz",
        "avg_vout", "ripple", "peak_i", "peak_start",
        "iin_avg", "iout_avg", "pin_avg", "pout_avg", "eta_pct",
        "vload_min_step", "vout_min_step", "il_peak_step", "iin_peak_step",
        "vload_recover", "vout_min_short", "il_peak_short",
        "iin_peak_short", "vout_recover"
    )
    $values = [ordered]@{}
    foreach ($name in $names) { $values[$name] = "" }
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
        return [pscustomobject]$values
    }
    $log = Get-Content -LiteralPath $LogPath -Raw
    foreach ($name in $names) {
        $pattern = "(?im)^\s*" + [regex]::Escape($name) +
            "\s*[:=]\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
        $match = [regex]::Match($log, $pattern)
        if ($match.Success) { $values[$name] = $match.Groups[1].Value }
    }
    return [pscustomobject]$values
}

function Invoke-LtspiceCase {
    param(
        [string]$DeckPath,
        [string]$Category,
        [string]$Executable,
        [string]$OutputRoot
    )

    $deckItem = Get-Item -LiteralPath $DeckPath
    $base = [IO.Path]::GetFileNameWithoutExtension($deckItem.Name)
    $sourceDir = $deckItem.DirectoryName
    $caseDir = Join-Path $OutputRoot $base
    New-Item -ItemType Directory -Path $caseDir -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $DeckPath -Destination (Join-Path $caseDir $deckItem.Name)

    $extensions = @(".raw", ".log", ".op.raw", ".db")
    $sourceOutputs = @($extensions | ForEach-Object { Join-Path $sourceDir ($base + $_) })
    $existing = @($sourceOutputs | Where-Object { Test-Path -LiteralPath $_ })
    if ($existing.Count -gt 0) {
        throw "Refusing to overwrite existing LTspice outputs for $base. Move or archive these first: $($existing -join ', ')"
    }

    $exitCode = -1
    Push-Location $sourceDir
    try {
        & $Executable -b ($base + ".cir")
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    $saved = @{}
    foreach ($ext in $extensions) {
        $source = Join-Path $sourceDir ($base + $ext)
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            $destination = Join-Path $caseDir ($base + $ext)
            Move-Item -LiteralPath $source -Destination $destination
            $saved[$ext] = $destination
        }
    }

    $rawPath = $saved[".raw"]
    $logPath = $saved[".log"]
    $status = if ($exitCode -eq 0 -and $rawPath -and $logPath) {
        "LTSPICE_EXIT0_RAW_LOG_SAVED_REVIEW_MEASUREMENTS"
    } else {
        "INCOMPLETE_OR_FAILED"
    }

    $manifestRow = [pscustomobject]@{
        category = $Category
        case = $base
        deck_path = $DeckPath
        deck_sha256 = Get-Sha256 $DeckPath
        model_sha256 = Get-Sha256 $ModelPath
        exit_code = $exitCode
        status = $status
        raw_path = if ($rawPath) { $rawPath } else { "" }
        raw_bytes = if ($rawPath) { (Get-Item -LiteralPath $rawPath).Length } else { 0 }
        raw_sha256 = if ($rawPath) { Get-Sha256 $rawPath } else { "" }
        log_path = if ($logPath) { $logPath } else { "" }
        log_sha256 = if ($logPath) { Get-Sha256 $logPath } else { "" }
        op_raw_sha256 = if ($saved[".op.raw"]) { Get-Sha256 $saved[".op.raw"] } else { "" }
        db_sha256 = if ($saved[".db"]) { Get-Sha256 $saved[".db"] } else { "" }
    }

    $measurements = Read-Measurements -LogPath $logPath
    $measurementRow = [ordered]@{
        category = $Category
        case = $base
    }
    foreach ($property in $measurements.PSObject.Properties) {
        $measurementRow[$property.Name] = $property.Value
    }

    return @{
        manifest = $manifestRow
        measurements = [pscustomobject]$measurementRow
        raw_path = $rawPath
        case_dir = $caseDir
    }
}

$LtspiceExe = Resolve-Ltspice $LtspiceExe
if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "TPS61088 macro-model not found: $ModelPath"
}
New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null
$manifestRows = [System.Collections.Generic.List[object]]::new()
$measurementRows = [System.Collections.Generic.List[object]]::new()

$ltspiceVersion = (Get-Item -LiteralPath $LtspiceExe).VersionInfo.FileVersion
$session = [ordered]@{
    started_local = (Get-Date).ToString("o")
    repository_root = $RepoRoot
    v14_root = $V14Root
    ltspice_executable = $LtspiceExe
    ltspice_file_version = $ltspiceVersion
    model_path = $ModelPath
    model_sha256 = Get-Sha256 $ModelPath
    run_root = $RunRoot
    note = "Local LTspice evidence only. This runner does not approve RILIM, inductor, efficiency, or BOM."
}
$session | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RunRoot "session.json") -Encoding UTF8

if (-not $Skip12p5) {
    $deck = Join-Path $DiagnosticsDir "freq_vin7_rfsw324k_internal_probe_12p5ns.cir"
    if (-not (Test-Path -LiteralPath $deck -PathType Leaf)) {
        throw "12.5 ns convergence deck is missing: $deck"
    }
    $result = Invoke-LtspiceCase -DeckPath $deck -Category "FSW_12p5ns" -Executable $LtspiceExe -OutputRoot $RunRoot
    $manifestRows.Add($result.manifest)
    $measurementRows.Add($result.measurements)

    if ($result.raw_path) {
        $analysisOut = Join-Path $result.case_dir "analysis"
        $python = Get-Command py -ErrorAction SilentlyContinue
        if ($python) {
            if ($Compare25Summary) {
                & $python.Source -3 $Analyzer --raw $result.raw_path --out $analysisOut --max-step-ns 12.5 --solver-label Gear --compare-with $Compare25Summary
            } else {
                & $python.Source -3 $Analyzer --raw $result.raw_path --out $analysisOut --max-step-ns 12.5 --solver-label Gear
            }
            $analysisExit = $LASTEXITCODE
        } else {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if (-not $python) { throw "Python 3 launcher 'py' or 'python' was not found." }
            if ($Compare25Summary) {
                & $python.Source $Analyzer --raw $result.raw_path --out $analysisOut --max-step-ns 12.5 --solver-label Gear --compare-with $Compare25Summary
            } else {
                & $python.Source $Analyzer --raw $result.raw_path --out $analysisOut --max-step-ns 12.5 --solver-label Gear
            }
            $analysisExit = $LASTEXITCODE
        }
        $session["fsw_12p5_analysis_exit_code"] = $analysisExit
    }
}

if (-not $SkipMatrix) {
    $rilimValues = @(100, 160, 174, 180, 200, 220)
    foreach ($vinLabel in @("7", "9p4")) {
        foreach ($rilim in $rilimValues) {
            $name = "ilim_vin" + $vinLabel + "_rilim" + $rilim + "k.cir"
            $deck = Join-Path $NetlistsDir $name
            if (-not (Test-Path -LiteralPath $deck -PathType Leaf)) {
                throw "Required RILIM matrix deck is missing: $deck"
            }
            $result = Invoke-LtspiceCase -DeckPath $deck -Category "RILIM_MATRIX" -Executable $LtspiceExe -OutputRoot $RunRoot
            $manifestRows.Add($result.manifest)
            $measurementRows.Add($result.measurements)
        }
    }
}

if (-not $SkipDynamic) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -3 $DynamicGenerator
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) { throw "Python 3 launcher 'py' or 'python' was not found." }
        & $python.Source $DynamicGenerator
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Dynamic-deck generator failed with exit code $LASTEXITCODE"
    }

    foreach ($vinLabel in @("7", "9p4")) {
        foreach ($rilim in @(160, 174)) {
            foreach ($kind in @("loadstep", "short")) {
                $name = "dynamic_vin" + $vinLabel + "_rilim" + $rilim + "k_" + $kind + ".cir"
                $deck = Join-Path $DiagnosticsDir $name
                if (-not (Test-Path -LiteralPath $deck -PathType Leaf)) {
                    throw "Generated dynamic test deck is missing: $deck"
                }
                $result = Invoke-LtspiceCase -DeckPath $deck -Category ("DYNAMIC_" + $kind.ToUpperInvariant()) -Executable $LtspiceExe -OutputRoot $RunRoot
                $manifestRows.Add($result.manifest)
                $measurementRows.Add($result.measurements)
            }
        }
    }
}

$manifestRows | Export-Csv -LiteralPath (Join-Path $RunRoot "manifest.csv") -NoTypeInformation -Encoding UTF8
$measurementRows | Export-Csv -LiteralPath (Join-Path $RunRoot "measurements.csv") -NoTypeInformation -Encoding UTF8
$session["finished_local"] = (Get-Date).ToString("o")
$session["cases_recorded"] = $manifestRows.Count
$session["run_root"] = $RunRoot
$session | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RunRoot "session.json") -Encoding UTF8

Write-Host "TPS61088 audit run finished. Cases recorded: $($manifestRows.Count)"
Write-Host "Evidence folder: $RunRoot"
Write-Host "Review manifest.csv and measurements.csv. Preserve every RAW, LOG, OP.RAW and DB file."
Write-Host "No RILIM or inductor is approved by this script."
