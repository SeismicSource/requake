# Integration Test for Catalog Files

This folder contains a simple test for catalog behavior.

## Purpose

This test records how the program behaves now.
After the SQLite change, behavior should stay the same.

## Contents

- `requake.conf`: test configuration
- `requake.catalog.txt`: small catalog with 3 test events
- `run_test.sh`: script that runs the test

## How To Run

To run the test:

```bash
./run_test.sh run
```

To remove generated files:

```bash
./run_test.sh clean
```

## What This Test Checks

This test checks:

1. **Catalog events**: the catalog contains exactly 3 expected event IDs
   - ev_baseline_001
   - ev_baseline_002
   - ev_baseline_003

2. **Event data**: time, coordinates, and magnitude are preserved when reading and writing

3. **Catalog file format**: output format matches input FDSN text format
   - FDSN is the standard text format used by earthquake catalogs

## Notes

This test focuses only on catalogs.
It does not need waveform data or network access.
For a larger end-to-end test, see `test_fdsnws/`.

This test will be expanded in Phase 2 to include:
- Pair generation and validation
- Family building validation
- Template scanning (if sample waveform files are available)
