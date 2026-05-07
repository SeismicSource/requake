#!/usr/bin/env bash
set -e

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Require action and optional suite selector
if [ -z "$1" ] || { [ "$1" != "run" ] && [ "$1" != "clean" ]; }; then
    echo "Error: You must specify either 'run' or 'clean' option"
    echo "Usage: $0 {run|clean} [all|unit|integration]"
    exit 1
fi

SUITE="${2:-all}"
if [ "$SUITE" != "all" ] && [ "$SUITE" != "unit" ] && [ "$SUITE" != "integration" ]; then
    echo "Error: suite must be one of: all, unit, integration"
    echo "Usage: $0 {run|clean} [all|unit|integration]"
    exit 1
fi

# Always run relative to this script's directory so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

run_unit_tests() {
    echo -e "${BLUE}========================================"
    echo "Running unit tests"
    echo -e "========================================${NC}"
    python -m unittest discover -s unit -p "test_*.py" -v
    echo -e "${GREEN}✓ Unit tests passed${NC}"
    echo ""
}

find_integration_test_dirs() {
    find integration -maxdepth 3 -name "run_test.sh" -type f -exec dirname {} \; | sort -u
}

run_integration_tests() {
    local test_dirs=()
    while IFS= read -r line; do
        test_dirs+=("$line")
    done < <(find_integration_test_dirs)

    if [ ${#test_dirs[@]} -eq 0 ]; then
        echo -e "${RED}Error: No integration test directories found${NC}"
        exit 1
    fi

    echo -e "${BLUE}========================================"
    echo "Running integration tests"
    echo -e "========================================${NC}"
    echo ""

    local total_tests=0
    local passed_tests=0
    local failed_tests=0

    for test_dir in "${test_dirs[@]}"; do
        total_tests=$((total_tests + 1))
        local test_name
        test_name=$(basename "$test_dir")

        echo -e "${BLUE}>>> Running integration test in $test_dir${NC}"
        if (cd "$test_dir" && bash run_test.sh run); then
            passed_tests=$((passed_tests + 1))
            echo -e "${GREEN}✓ Integration test $test_name passed${NC}"
        else
            failed_tests=$((failed_tests + 1))
            echo -e "${RED}✗ Integration test $test_name failed${NC}"
        fi
        echo ""
    done

    echo -e "${BLUE}========================================"
    echo "Integration Test Summary"
    echo -e "========================================${NC}"
    echo "Total tests: $total_tests"
    echo -e "${GREEN}Passed: $passed_tests${NC}"
    if [ $failed_tests -gt 0 ]; then
        echo -e "${RED}Failed: $failed_tests${NC}"
        exit 1
    fi
    echo -e "${GREEN}Failed: $failed_tests${NC}"
    echo -e "${GREEN}✓ Integration tests succeeded!${NC}"
    echo ""
}

clean_integration_tests() {
    local test_dirs=()
    while IFS= read -r line; do
        test_dirs+=("$line")
    done < <(find_integration_test_dirs)

    if [ ${#test_dirs[@]} -eq 0 ]; then
        echo -e "${RED}Error: No integration test directories found${NC}"
        exit 1
    fi

    echo -e "${BLUE}========================================"
    echo "Cleaning integration tests"
    echo -e "========================================${NC}"
    echo ""

    for test_dir in "${test_dirs[@]}"; do
        echo -e "${BLUE}>>> Cleaning $test_dir${NC}"
        (cd "$test_dir" && bash run_test.sh clean)
        echo ""
    done

    echo -e "${GREEN}✓ Integration tests cleaned${NC}"
}

if [ "$1" == "clean" ]; then
    if [ "$SUITE" == "all" ] || [ "$SUITE" == "integration" ]; then
        clean_integration_tests
    fi
    if [ "$SUITE" == "unit" ]; then
        echo "No unit test artifacts to clean."
    fi
    exit 0
fi

if [ "$SUITE" == "all" ] || [ "$SUITE" == "unit" ]; then
    run_unit_tests
fi

if [ "$SUITE" == "all" ] || [ "$SUITE" == "integration" ]; then
    run_integration_tests
fi

echo -e "${GREEN}✓ Selected test suites succeeded${NC}"
