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
    rm -rf requake_out maptiles requake_plots
    echo "Clean complete."
    exit 0
fi

# Check if output directory already exists
if [ -d "requake_out" ]; then
    echo "Error: requake_out directory already exists"
    echo "Please run '$0 clean' first to remove it"
    exit 1
fi

# Total number of tests
TOTAL_TESTS=12

# Run the test
echo "========================================"
echo "Running test..."
echo "========================================"
echo ""

echo ""
echo "[1/$TOTAL_TESTS] Reading catalog..."
requake read_catalog
echo "----------------------------------------"

echo ""
echo "[2/$TOTAL_TESTS] Printing catalog..."
requake print_catalog
echo "----------------------------------------"

echo ""
echo "[3/$TOTAL_TESTS] Scanning catalog..."
requake scan_catalog
echo "----------------------------------------"

echo ""
echo "[4/$TOTAL_TESTS] Printing pairs..."
requake print_pairs
echo "----------------------------------------"

echo ""
echo "[5/$TOTAL_TESTS] Building families..."
requake build_families
echo "----------------------------------------"

echo ""
echo "[6/$TOTAL_TESTS] Printing families..."
requake print_families
echo "----------------------------------------"

echo ""
echo "[7/$TOTAL_TESTS] Printing details for family 0..."
requake print_families -d 0
echo "----------------------------------------"

echo ""
echo "[8/$TOTAL_TESTS] Plotting pair..."
requake plot_pair ovsm2022tvpa ovsm2022ukkc -o requake_plots/pair.png
echo "----------------------------------------"

echo ""
echo "[9/$TOTAL_TESTS] Plotting families..."
requake plot_families 0 -o requake_plots/families.png
echo "----------------------------------------"

echo ""
echo "[10/$TOTAL_TESTS] Plotting cumulative..."
requake plot_cumulative -o requake_plots/cumulative.png
echo "----------------------------------------"

echo ""
echo "[11/$TOTAL_TESTS] Plotting timespans..."
requake plot_timespans -o requake_plots/timespans.png
echo "----------------------------------------"

echo ""
echo "[12/$TOTAL_TESTS] Mapping families..."
requake map_families -o requake_plots/map_families.png

echo ""
echo "========================================"
echo "✓ Test succeeded!"
echo "========================================"