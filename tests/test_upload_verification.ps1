# =====================================================================
# Regression Test Suite: CONF-01 (Upload Verification & False Positive Prevention)
# =====================================================================
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TEST SUITE: CONF-01 Upload Success Verification"            -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

$passed = 0
$failed = 0

function Assert-Result([string]$testName, [bool]$actual, [bool]$expected) {
    if ($actual -eq $expected) {
        Write-Host "  [PASS] $testName" -ForegroundColor Green
        $script:passed++
    } else {
        Write-Host "  [FAIL] $testName (Expected: $expected, Got: $actual)" -ForegroundColor Red
        $script:failed++
    }
}

function Evaluate-UploadSuccess([int]$exitCode, [bool]$timedOut, [string]$stdout, [string]$stderr) {
    $mediaKey = ""
    $cliErr = ""

    if ($stdout) {
        if ($stdout -match '"mediaKey":\s*"([^"]+)"') {
            $mediaKey = $matches[1]
        }
        if ($stdout -match '"error":\s*"([^"]+)"') {
            $cliErr = $matches[1]
        } elseif ($stdout -match '"message":\s*"([^"]+)"') {
            $cliErr = $matches[1]
        }
    }
    if (-not $cliErr -and $stderr) {
        $cliErr = $stderr.Trim()
    }

    $hasExplicitSuccess = ($stdout -match '"success":\s*true') -or (-not [string]::IsNullOrEmpty($mediaKey))
    $isSuccess = ($exitCode -eq 0) -and (-not $timedOut) -and (-not $cliErr) -and $hasExplicitSuccess
    return $isSuccess
}

# 1. Successful upload with mediaKey and success: true
$out1 = '{"success": true, "mediaKey": "AF1QipN32abcxyz", "bytes": 1048576}'
Assert-Result "Valid JSON with success: true and mediaKey is marked as SUCCESS" (Evaluate-UploadSuccess 0 $false $out1 "") $true

# 2. Skipped/unsupported format where process exited with code 0 (CONF-01)
$out2 = '{"success": false, "error": "file format not supported for backup"}'
Assert-Result "Process exiting 0 with error in JSON is NOT marked as success (CONF-01)" (Evaluate-UploadSuccess 0 $false $out2 "") $false

# 3. Empty stdout or plain help output exiting with code 0 without mediaKey
$out3 = "gotohp v0.11.0 usage: upload [flags] <file>"
Assert-Result "Process exiting 0 without explicit success or mediaKey is NOT marked as success" (Evaluate-UploadSuccess 0 $false $out3 "") $false

# 4. Process exited with error on stderr
Assert-Result "Process with stderr error is NOT marked as success" (Evaluate-UploadSuccess 1 $false "" "Network timeout connecting to photos API") $false

# 5. Process timed out
Assert-Result "Timed out process is NOT marked as success" (Evaluate-UploadSuccess -1 $true "" "") $false

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  RESULTS: $passed Passed, $failed Failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host "==========================================================" -ForegroundColor Cyan

if ($failed -gt 0) { exit 1 } else { exit 0 }
