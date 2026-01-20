#!/usr/bin/env bash
set -e

# Require either 'run' or 'clean' option
if [ -z "$1" ] || { [ "$1" != "run" ] && [ "$1" != "clean" ]; }; then
    echo "Error: You must specify either 'run' or 'clean' option"
    echo "Usage: $0 {run|clean}"
    exit 1
fi

# Handle clean option
if [ "$1" == "clean" ]; then
    echo "Cleaning up requake_out directory..."
    rm -rf requake_out
    echo "Clean complete."
    exit 0
fi

# Check if output directory already exists
if [ -d "requake_out" ]; then
    echo "Error: requake_out directory already exists"
    echo "Please run '$0 clean' first to remove it"
    exit 1
fi

# Run the test
echo "========================================"
echo "Running test..."
echo "========================================"
echo ""

echo ""
echo "[1/7] Reading catalog..."
requake read_catalog
echo "----------------------------------------"

echo ""
echo "[2/7] Printing catalog..."
requake print_catalog
echo "----------------------------------------"

echo ""
echo "[3/7] Scanning catalog..."
requake scan_catalog
echo "----------------------------------------"

echo ""
echo "[4/7] Printing pairs..."
requake print_pairs
echo "----------------------------------------"

echo ""
echo "[5/7] Building families..."
requake build_families
echo "----------------------------------------"

echo ""
echo "[6/7] Printing families..."
requake print_families
echo "----------------------------------------"

echo ""
echo "[7/7] Printing details for family 0..."
requake print_families -d 0
echo "----------------------------------------"

echo ""
echo "========================================"
echo "✓ Test succeeded!"
echo "========================================"