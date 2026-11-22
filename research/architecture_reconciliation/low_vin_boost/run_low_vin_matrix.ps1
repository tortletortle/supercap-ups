[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$LtspiceExe,

    [string[]]$Case = @(),

    [string]$NetlistSubdir = "netlists"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-HashOrBlank([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    }
    return ""
}

function Get-MetadataValue($Metadata, [string]$Name) {
    if ($null -ne $Metadata -and $Metadata.PSObject.Properties.Name -contains $Name) {
        return $Metadata.$Name
    }
    return ""
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$netlistDir = Join-Path $scriptDir $NetlistSubdir
$modelPath = (Resolve-Path -LiteralPath (
    Join-Path $netlistDir "..\..\..\..\sim\tps61088_v1_3\model\TPS61088_LT.LIB"
)).Path

if (-not (Test-Path -LiteralPath $LtspiceExe -PathType Leaf)) {
    throw "LTspice executable not found: $LtspiceExe"
}
if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    throw "TPS61088 model file not found: $modelPath"
}

$decks = @(Get-ChildItem -LiteralPath $netlistDir -Filter "*.cir" -File |
    Sort-Object Name)
if ($Case.Count -gt 0) {
    $decks = @($decks | Where-Object { $Case -contains $_.BaseName })
}
if ($decks.Count -eq 0) {
    throw "No matching netlists found. Check -Case values."
}

$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$resultsRoot = Join-Path $scriptDir (Join-Path "results" $runId)
New-Item -ItemType Directory -Path $resultsRoot -Force | Out-Null

$versionOutput = ""
try {
    $versionOutput = (& $LtspiceExe -version 2>&1 | Out-String).Trim()
} catch {
    $versionOutput = "version query failed: $($_.Exception.Message)"
}

$metadataByCase = @{}
$metadataPath = Join-Path $netlistDir "manifest.csv"
if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
    foreach ($metadata in (Import-Csv -LiteralPath $metadataPath)) {
        if ($metadata.case) {
            $metadataByCase[$metadata.case] = $metadata
        }
    }
}

$records = New-Object System.Collections.Generic.List[object]

foreach ($deck in $decks) {
    $rawPath = [System.IO.Path]::ChangeExtension($deck.FullName, ".raw")
    $logPath = [System.IO.Path]::ChangeExtension($deck.FullName, ".log")

    if ((Test-Path -LiteralPath $rawPath) -or (Test-Path -LiteralPath $logPath)) {
        throw "Refusing to overwrite existing LTspice output for $($deck.Name). Archive or move the old .raw/.log first."
    }

    $caseName = $deck.BaseName
    $metadata = $null
    if ($metadataByCase.ContainsKey($caseName)) {
        $metadata = $metadataByCase[$caseName]
    }
    $caseDir = Join-Path $resultsRoot $caseName
    New-Item -ItemType Directory -Path $caseDir -Force | Out-Null
    Copy-Item -LiteralPath $deck.FullName -Destination $caseDir

    $startTime = (Get-Date).ToString("o")
    $processArgs = @{
        FilePath = $LtspiceExe
        ArgumentList = @("-b", ('"{0}"' -f $deck.FullName))
        WorkingDirectory = $netlistDir
        Wait = $true
        PassThru = $true
        NoNewWindow = $true
    }
    $process = Start-Process @processArgs

    $exitCode = $process.ExitCode
    $hasRaw = Test-Path -LiteralPath $rawPath -PathType Leaf
    $hasLog = Test-Path -LiteralPath $logPath -PathType Leaf

    if ($hasRaw) {
        Move-Item -LiteralPath $rawPath -Destination $caseDir
    }
    if ($hasLog) {
        Move-Item -LiteralPath $logPath -Destination $caseDir
    }

    $savedRaw = Join-Path $caseDir ([System.IO.Path]::GetFileName($rawPath))
    $savedLog = Join-Path $caseDir ([System.IO.Path]::GetFileName($logPath))

    if (($exitCode -eq 0) -and $hasRaw -and $hasLog) {
        $status = "process_exit_0_files_present_review_required"
    } elseif (($exitCode -ne 0) -and ($hasRaw -or $hasLog)) {
        $status = "process_nonzero_partial_files_preserved"
    } else {
        $status = "missing_raw_or_log_review_required"
    }

    $records.Add([PSCustomObject]@{
        case = $caseName
        case_type = Get-MetadataValue $metadata "case_type"
        architecture = Get-MetadataValue $metadata "architecture"
        checkpoint_s = Get-MetadataValue $metadata "checkpoint_s"
        enable_delay_us = Get-MetadataValue $metadata "enable_delay_us"
        initial_pack_ocv_v = Get-MetadataValue $metadata "initial_pack_ocv_v"
        cap_factor = Get-MetadataValue $metadata "cap_factor"
        esr_factor = Get-MetadataValue $metadata "esr_factor"
        expected_pack_ocv_v = Get-MetadataValue $metadata "expected_pack_ocv_v"
        expected_pack_terminal_v = Get-MetadataValue $metadata "expected_pack_terminal_v"
        expected_input_current_a = Get-MetadataValue $metadata "expected_input_current_a"
        vin_source_v = Get-MetadataValue $metadata "vin_source_v"
        rfsw_kohm = Get-MetadataValue $metadata "rfsw_kohm"
        rilim_kohm = Get-MetadataValue $metadata "rilim_kohm"
        mode = Get-MetadataValue $metadata "mode"
        inductor_mpn = Get-MetadataValue $metadata "inductor_mpn"
        inductance_nominal_uH = Get-MetadataValue $metadata "inductance_nominal_uH"
        inductance_min_uH = Get-MetadataValue $metadata "inductance_min_uH"
        dcr_max_mohm = Get-MetadataValue $metadata "dcr_max_mohm"
        isat_typical_a = Get-MetadataValue $metadata "isat_typical_a"
        irms_typical_a = Get-MetadataValue $metadata "irms_typical_a"
        isat_above_programmed_ilim_typical = Get-MetadataValue $metadata "isat_above_programmed_ilim_typical"
        programmed_ilim_typical_a = Get-MetadataValue $metadata "programmed_ilim_typical_a"
        input_deck_sha256 = Get-HashOrBlank $deck.FullName
        model_sha256 = Get-HashOrBlank $modelPath
        exit_code = $exitCode
        raw_present = $hasRaw
        log_present = $hasLog
        raw_sha256 = Get-HashOrBlank $savedRaw
        log_sha256 = Get-HashOrBlank $savedLog
        status = $status
        start_local = $startTime
        end_local = (Get-Date).ToString("o")
        ltspice_executable = $LtspiceExe
        ltspice_version = $versionOutput
        result_directory = $caseDir
    })
}

$manifestPath = Join-Path $resultsRoot "run_manifest.csv"
$records | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8

@(
    "Run ID: $runId"
    "LTspice executable: $LtspiceExe"
    "LTspice version: $versionOutput"
    "Model: $modelPath"
    "Model SHA-256: $(Get-HashOrBlank $modelPath)"
    "Run status is process/file collection only; it is NOT an electrical pass."
    "Review each .log and .raw, then apply the acceptance rules in README.md."
) | Set-Content -LiteralPath (Join-Path $resultsRoot "run_info.txt") -Encoding UTF8

Write-Host "Collected $($records.Count) run(s) under: $resultsRoot"
Write-Host "Manifest: $manifestPath"
