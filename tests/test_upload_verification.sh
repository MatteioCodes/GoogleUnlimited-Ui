#!/usr/bin/env bash
# =====================================================================
# Regression Test Suite: CONF-01 (Upload Verification & False Positive Prevention - Unix)
# =====================================================================
set -euo pipefail

echo "=========================================================="
echo "  TEST SUITE: CONF-01 Upload Success Verification (Bash/Unix)"
echo "=========================================================="

PASSED=0
FAILED=0

assert_result() {
    local name="$1"
    local actual="$2"
    local expected="$3"
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  \033[0;32m[PASS]\033[0m $name (Result: $actual)"
        PASSED=$((PASSED + 1))
    else
        echo -e "  \033[0;31m[FAIL]\033[0m $name (Expected: $expected, Got: $actual)"
        FAILED=$((FAILED + 1))
    fi
}

evaluate_upload_success() {
    local exit_code="$1"
    local output="$2"

    local mkey=""
    mkey="$(echo "$output" | grep -o '"mediaKey": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "")"
    local err_msg=""
    err_msg="$(echo "$output" | grep -o '"error": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "")"
    [ -z "$err_msg" ] && err_msg="$(echo "$output" | grep -o '"message": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "")"

    local is_success=0
    if [ "$exit_code" -eq 0 ] && [ -z "$err_msg" ]; then
        if echo "$output" | grep -q '"success": *true' || [ -n "$mkey" ]; then
            is_success=1
        fi
    fi
    echo "$is_success"
}

# 1. Valid JSON with success: true and mediaKey
out1='{"success": true, "mediaKey": "AF1QipN32abcxyz", "bytes": 1048576}'
res1="$(evaluate_upload_success 0 "$out1")"
assert_result "Valid JSON with success: true and mediaKey is marked as SUCCESS" "$res1" 1

# 2. Process exited 0 with error in JSON (CONF-01 skipped format)
out2='{"success": false, "error": "file format not supported for backup"}'
res2="$(evaluate_upload_success 0 "$out2")"
assert_result "Process exiting 0 with error in JSON is NOT marked as success (CONF-01)" "$res2" 0

# 3. Process exited 0 without explicit success or mediaKey
out3="gotohp v0.11.0 usage: upload [flags] <file>"
res3="$(evaluate_upload_success 0 "$out3")"
assert_result "Process exiting 0 without explicit success or mediaKey is NOT marked as success" "$res3" 0

# 4. Process exited with error exit code
out4='{"error": "network failure"}'
res4="$(evaluate_upload_success 1 "$out4")"
assert_result "Process with non-zero exit code is NOT marked as success" "$res4" 0

echo "=========================================================="
echo "  RESULTS: $PASSED Passed, $FAILED Failed"
echo "=========================================================="

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
exit 0
