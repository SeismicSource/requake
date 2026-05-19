# Integration Test for Template Catalog Files

This folder contains a simple test for template catalog files.

## Purpose

This test checks file names and row format used in template scanning.
After SQLite is added, behavior should stay the same.

## Contents

- `run_test.sh`: script that creates small test files and checks their format

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

1. **File names**: files must be named `catalog{family:02d}.{trace_id}.txt`
   - Example: `catalog00.XX.TEST.00.BHZ.txt` for family 0, trace XX.TEST.00.BHZ

2. **Row format**: each row must contain exactly 14 fields separated by `|`
   - Fields 1-13: event information in FDSN text format
   - Field 14: `cc_max` (similarity value between -1 and 1)

3. **Folder structure**: template catalog files are stored in `template_catalogs/`
   - One file per template (family + trace_id)
   - Each file can contain multiple detected events

## Notes

This test creates small sample files and checks the format.
It does not require real waveform data or a full template scan run.

This test is used across migration phases:
- Phase 1: define the expected format
- Phase 2: add SQLite support for that format
- Phase 3: confirm SQLite gives the same results
