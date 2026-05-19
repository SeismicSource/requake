#!/usr/bin/env bash
# Baseline integration test for Requake
# This test locks in the current behavior of catalog operations
set -e

# Require either 'run' or 'clean' option
if [ -z "$1" ] || { [ "$1" != "run" ] && [ "$1" != "clean" ]; }; then
    echo "Error: You must specify either 'run' or 'clean' option"
    echo "Usage: $0 {run|clean}"
    exit 1
fi

# Get the directory where this script is located
TEST_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$TEST_DIR"

# Handle clean option
if [ "$1" == "clean" ]; then
    echo "Cleaning up requake_out directory..."
    rm -rf requake_out
    rm -f results.json
    echo "Clean complete."
    exit 0
fi

# Check if output directory already exists
if [ -d "requake_out" ]; then
    echo "Error: requake_out directory already exists"
    echo "Please run '$0 clean' first to remove it"
    exit 1
fi

# Total number of steps
TOTAL_STEPS=3

echo "========================================"
echo "Running baseline integration test..."
echo "========================================"
echo ""

# Step 1: Read catalog
echo "[1/$TOTAL_STEPS] Reading catalog..."
requake read_catalog requake.catalog.txt || { echo "FAILED: read_catalog"; exit 1; }
echo "✓ Catalog read complete"
echo "----------------------------------------"
echo ""

# Step 2: Print catalog to verify it was read correctly
echo "[2/$TOTAL_STEPS] Printing catalog..."
requake print_catalog > requake_out/catalog_output.txt 2>&1 || { echo "FAILED: print_catalog"; exit 1; }
echo "✓ Catalog printed"
echo "----------------------------------------"
echo ""

# Step 3: Verify catalog file exists and contains expected data
echo "[3/$TOTAL_STEPS] Validating baseline invariants..."
if [ ! -f "requake_out/requake.catalog.txt" ]; then
    echo "FAILED: requake.catalog.txt not found in requake_out"
    exit 1
fi

# Count lines in catalog (should be 3 events + comments)
CATALOG_LINES=$(grep -v '^#' "requake_out/requake.catalog.txt" | grep -v '^$' | wc -l)
if [ "$CATALOG_LINES" -ne 3 ]; then
    echo "FAILED: Expected 3 events in catalog, got $CATALOG_LINES"
    exit 1
fi

# Verify output includes all expected event IDs
for EVID in "ev_baseline_001" "ev_baseline_002" "ev_baseline_003"; do
    if ! grep -q "$EVID" "requake_out/requake.catalog.txt"; then
        echo "FAILED: Expected event $EVID not found in catalog"
        exit 1
    fi
done

echo "✓ Catalog baseline invariants validated"
echo "  - 3 events in catalog"
echo "  - All expected event IDs present"
echo ""

echo "========================================"
echo "✓ Baseline test succeeded!"
echo "========================================"
