#!/usr/bin/env bash
set -e

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Require either 'run' or 'clean' option
if [ -z "$1" ] || { [ "$1" != "run" ] && [ "$1" != "clean" ]; }; then
    echo "Error: You must specify either 'run' or 'clean' option"
    echo "Usage: $0 {run|clean}"
    exit 1
fi

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Find all test directories containing run_test.sh
TEST_DIRS=()
while IFS= read -r line; do
    TEST_DIRS+=("$line")
done < <(find . -maxdepth 2 -name "run_test.sh" -type f -print0 | \
    xargs -0 dirname | sort)

if [ ${#TEST_DIRS[@]} -eq 0 ]; then
    echo -e "${RED}Error: No test directories found${NC}"
    exit 1
fi

# Handle clean option
if [ "$1" == "clean" ]; then
    echo -e "${BLUE}========================================"
    echo "Cleaning all tests"
    echo "========================================${NC}"
    echo ""

    for test_dir in "${TEST_DIRS[@]}"; do
        echo -e "${BLUE}>>> Cleaning $test_dir${NC}"
        (cd "$test_dir" && bash run_test.sh clean)
        echo ""
    done

    echo -e "${GREEN}✓ All tests cleaned!${NC}"
    exit 0
fi

echo -e "${BLUE}========================================"
echo "Running all tests"
echo "========================================${NC}"
echo ""

# Run each test
for test_dir in "${TEST_DIRS[@]}"; do
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    TEST_NAME=$(basename "$test_dir")

    echo -e "${BLUE}>>> Running test in $test_dir${NC}"

    if (cd "$test_dir" && bash run_test.sh run); then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "${GREEN}✓ Test $TEST_NAME passed${NC}"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "${RED}✗ Test $TEST_NAME failed${NC}"
    fi

    echo ""
done

# Summary
echo -e "${BLUE}========================================"
echo "Test Summary"
echo "========================================${NC}"
echo "Total tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    exit 1
else
    echo -e "${GREEN}Failed: $FAILED_TESTS${NC}"
    echo ""
    echo -e "${GREEN}✓ All tests succeeded!${NC}"
fi
