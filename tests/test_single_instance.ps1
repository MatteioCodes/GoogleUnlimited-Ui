# =====================================================================
# Regression Test Suite: Single-Instance Mutex Protection (PowerShell)
# =====================================================================
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $scriptDir
$watchScript = Join-Path $repoDir "WatchAndUpload.ps1"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TEST SUITE: Single-Instance Mutex Protection"             -ForegroundColor Green
Write-Host "  Target Script: $watchScript"                              -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

$passed = 0
$failed = 0

function Assert-Condition([string]$testName, [bool]$condition, [string]$detail = "") {
    if ($condition) {
        Write-Host "  [PASS] $testName" -ForegroundColor Green
        $script:passed++
    } else {
        Write-Host "  [FAIL] $testName $(if ($detail) { "($detail)" })" -ForegroundColor Red
        $script:failed++
    }
}

# Determine PowerShell executable to use for child processes
$psExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell.exe" }

# Clean up any leftover processes before starting
$priorProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*WatchAndUpload.ps1*" }
foreach ($p in $priorProcesses) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 500

try {
    # -------------------------------------------------------------
    # Test 1: First instance starts and acquires mutex
    # -------------------------------------------------------------
    Write-Host "`n>>> [Test 1] Launching primary background instance..." -ForegroundColor Yellow
    $psi1 = New-Object System.Diagnostics.ProcessStartInfo
    $psi1.FileName = $psExe
    $psi1.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$watchScript`""
    $psi1.WorkingDirectory = $repoDir
    $psi1.UseShellExecute = $false
    $psi1.RedirectStandardOutput = $true
    $psi1.RedirectStandardError = $true
    $proc1 = [System.Diagnostics.Process]::Start($psi1)

    # Allow instance 1 time to initialize and acquire mutex
    Start-Sleep -Seconds 2
    Assert-Condition "Instance 1 is running and owns process ID" (-not $proc1.HasExited) "PID: $($proc1.Id)"

    # Verify mutex actually exists in the local namespace
    $cleanBase = $repoDir.ToLower().Replace("\", "_").Replace(":", "").Replace(" ", "_")
    $expectedMutexName = "Local\GoogleUnlimited_Watcher_$cleanBase"

    $mutexFound = $false
    try {
        $testMutex = [System.Threading.Mutex]::OpenExisting($expectedMutexName)
        $mutexFound = $null -ne $testMutex
        if ($testMutex) { $testMutex.Dispose() }
    } catch {
        $mutexFound = $false
    }
    Assert-Condition "Named mutex '$expectedMutexName' exists in session" $mutexFound

    # -------------------------------------------------------------
    # Test 2: Second instance exits immediately with required message
    # -------------------------------------------------------------
    Write-Host "`n>>> [Test 2] Launching second concurrent instance..." -ForegroundColor Yellow
    $psi2 = New-Object System.Diagnostics.ProcessStartInfo
    $psi2.FileName = $psExe
    $psi2.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$watchScript`""
    $psi2.WorkingDirectory = $repoDir
    $psi2.UseShellExecute = $false
    $psi2.RedirectStandardOutput = $true
    $psi2.RedirectStandardError = $true
    $proc2 = [System.Diagnostics.Process]::Start($psi2)

    $proc2Output = $proc2.StandardOutput.ReadToEnd()
    $proc2Error = $proc2.StandardError.ReadToEnd()
    [void]$proc2.WaitForExit(5000)

    Assert-Condition "Instance 2 exited promptly" $proc2.HasExited
    Assert-Condition "Instance 2 output contains 'Another instance is already running. Exiting.'" `
        ($proc2Output -like "*Another instance is already running. Exiting.*") "Output: $proc2Output"
    Assert-Condition "Instance 2 exit code is 0 (graceful exit)" ($proc2.ExitCode -eq 0) "ExitCode: $($proc2.ExitCode)"

    # -------------------------------------------------------------
    # Test 3: Instance 1 continues working undisturbed
    # -------------------------------------------------------------
    Write-Host "`n>>> [Test 3] Verifying primary instance remains alive..." -ForegroundColor Yellow
    Assert-Condition "Instance 1 continues running normally after instance 2 exited" (-not $proc1.HasExited)

    # -------------------------------------------------------------
    # Test 4: Management/diagnostic flags bypass single-instance lock
    # -------------------------------------------------------------
    Write-Host "`n>>> [Test 4] Verifying -StatusOnly is allowed while watcher is running..." -ForegroundColor Yellow
    $psiStatus = New-Object System.Diagnostics.ProcessStartInfo
    $psiStatus.FileName = $psExe
    $psiStatus.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$watchScript`" -StatusOnly"
    $psiStatus.WorkingDirectory = $repoDir
    $psiStatus.UseShellExecute = $false
    $psiStatus.RedirectStandardOutput = $true
    $psiStatus.RedirectStandardError = $true
    $procStatus = [System.Diagnostics.Process]::Start($psiStatus)

    $statusOutput = $procStatus.StandardOutput.ReadToEnd()
    [void]$procStatus.WaitForExit(5000)

    Assert-Condition "-StatusOnly ran successfully while watcher active" ($procStatus.ExitCode -eq 0)
    Assert-Condition "-StatusOnly was not blocked by mutex" ($statusOutput -notlike "*Another instance is already running*")

    # -------------------------------------------------------------
    # Test 5: Abrupt process kill & AbandonedMutexException recovery
    # -------------------------------------------------------------
    Write-Host "`n>>> [Test 5] Simulating crash / abrupt kill of instance 1..." -ForegroundColor Yellow
    $proc1.Kill()
    [void]$proc1.WaitForExit(3000)
    Assert-Condition "Instance 1 terminated" $proc1.HasExited

    Start-Sleep -Milliseconds 500

    Write-Host ">>> Launching replacement instance after crash..." -ForegroundColor Yellow
    $psi3 = New-Object System.Diagnostics.ProcessStartInfo
    $psi3.FileName = $psExe
    $psi3.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$watchScript`""
    $psi3.WorkingDirectory = $repoDir
    $psi3.UseShellExecute = $false
    $psi3.RedirectStandardOutput = $true
    $psi3.RedirectStandardError = $true
    $proc3 = [System.Diagnostics.Process]::Start($psi3)

    Start-Sleep -Seconds 2
    Assert-Condition "Replacement instance acquired abandoned mutex and is running" (-not $proc3.HasExited)

    # Clean up instance 3
    $proc3.Kill()
    [void]$proc3.WaitForExit(2000)

} finally {
    # Ensure all test child processes are cleanly stopped
    if ($proc1 -and -not $proc1.HasExited) { $proc1.Kill() }
    if ($proc2 -and -not $proc2.HasExited) { $proc2.Kill() }
    if ($proc3 -and -not $proc3.HasExited) { $proc3.Kill() }
    if ($procStatus -and -not $procStatus.HasExited) { $procStatus.Kill() }
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  RESULTS: $passed Passed, $failed Failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host "==========================================================" -ForegroundColor Cyan

if ($failed -gt 0) { exit 1 } else { exit 0 }
