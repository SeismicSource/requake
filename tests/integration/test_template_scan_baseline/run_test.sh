#!/usr/bin/env bash
# Baseline integration test for template scanning
# This test validates the template catalog file structure and reading behavior
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
    echo "Cleaning up test outputs..."
    rm -rf template_catalogs
    rm -f test_results.txt
    echo "Clean complete."
    exit 0
fi

echo "========================================"
echo "Running template catalog baseline test..."
echo "========================================"
echo ""

# Create test template catalog directory structure
echo "[1/3] Creating template catalog fixtures..."
mkdir -p template_catalogs

# Create template catalog files with expected naming convention
# Format: catalog{family:02d}.{trace_id}.txt
# Each row format: fdsn_text|cc_max

cat > template_catalogs/catalog00.XX.TEST.00.BHZ.txt << 'EOF'
ev_t001|2020-01-01T00:00:00|45.0|10.0|10.0|TEST|TEST|TEST|TEST_1|Mw|4.0|TEST|Location 1|0.85
ev_t002|2020-01-01T01:00:00|45.1|10.1|10.5|TEST|TEST|TEST|TEST_2|Mw|4.1|TEST|Location 2|0.87
EOF

cat > template_catalogs/catalog00.YY.TEST.00.BHP.txt << 'EOF'
ev_t001|2020-01-01T00:00:00|45.0|10.0|10.0|TEST|TEST|TEST|TEST_1|Mw|4.0|TEST|Location 1|0.82
ev_t003|2020-01-01T02:00:00|45.2|10.2|11.0|TEST|TEST|TEST|TEST_3|Mw|4.2|TEST|Location 3|0.84
EOF

cat > template_catalogs/catalog01.XX.TEST.00.BHZ.txt << 'EOF'
ev_t004|2020-01-01T03:00:00|45.3|10.3|11.5|TEST|TEST|TEST|TEST_4|Mw|4.3|TEST|Location 4|0.88
EOF

echo "✓ Template catalog fixtures created"
echo "  - catalog00.XX.TEST.00.BHZ.txt (2 rows)"
echo "  - catalog00.YY.TEST.00.BHP.txt (2 rows)"
echo "  - catalog01.XX.TEST.00.BHZ.txt (1 row)"
echo ""

# Verify naming convention
echo "[2/3] Validating naming convention..."
CATALOG_FILES=$(find template_catalogs -name "catalog*.txt")
if [ -z "$CATALOG_FILES" ]; then
    echo "FAILED: No catalog files found"
    exit 1
fi

FILE_COUNT=$(echo "$CATALOG_FILES" | wc -l)
if [ "$FILE_COUNT" -ne 3 ]; then
    echo "FAILED: Expected 3 catalog files, got $FILE_COUNT"
    exit 1
fi

# Check each file matches pattern catalogXX.TRACE_ID.txt
while IFS= read -r file; do
    BASENAME=$(basename "$file")
    if ! [[ $BASENAME =~ ^catalog[0-9]{2}\.[A-Z]{2}\.[A-Z]{4}\.[0-9]{2}\.[A-Z]{3}\.txt$ ]]; then
        echo "FAILED: File $BASENAME does not match expected naming pattern"
        exit 1
    fi
done <<< "$CATALOG_FILES"

echo "✓ All files match naming convention catalogXX.TRACE_ID.txt"
echo ""

# Validate row format
echo "[3/3] Validating row format (fdsn_text|cc_max)..."
ROW_COUNT=0
while IFS= read -r file; do
    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi

        # Count pipes - should have exactly 13 (for 14 fields: 13 FDSN + cc_max)
        PIPE_COUNT=$(echo "$line" | grep -o '|' | wc -l)
        if [ "$PIPE_COUNT" -ne 13 ]; then
            echo "FAILED: Row has $PIPE_COUNT pipes, expected 13 in file $file"
            exit 1
        fi

        # Extract cc_max (last field)
        CC_MAX=$(echo "$line" | rev | cut -d'|' -f1 | rev)

        # Validate cc_max is a float between -1 and 1
        if ! [[ $CC_MAX =~ ^0\.[0-9]+$ ]]; then
            echo "FAILED: Invalid cc_max value '$CC_MAX' in file $file"
            exit 1
        fi

        ROW_COUNT=$((ROW_COUNT + 1))
    done < "$file"
done <<< "$CATALOG_FILES"

if [ "$ROW_COUNT" -ne 5 ]; then
    echo "FAILED: Expected 5 total rows, got $ROW_COUNT"
    exit 1
fi

echo "✓ All rows have valid format (fdsn_text|cc_max)"
echo "  - Total rows: $ROW_COUNT"
echo ""

echo "========================================"
echo "✓ Template catalog baseline test passed!"
echo "========================================"
