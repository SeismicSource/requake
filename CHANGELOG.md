# Requake Changelog

Copyright (c) 2021-2026 Claudio Satriano <satriano@ipgp.fr>

## [unreleased]

- New ``dedup_events`` command: detects events that are likely
  duplicates of each other, based on event pairs with high
  cross-correlation coefficient which are also close in time and space.
  One event per duplicate group is kept, the others are flagged as
  duplicated in the catalog (new ``duplicate`` column) and all the pairs
  involving them are flagged as invalid (new ``invalid`` column in
  ``event_pairs``). A compact report is printed at the end, and
  ``-n``/``--dry-run`` only prints the report. ``build_families`` now
  ignores pairs flagged as invalid.
- ``dedup_events --reset`` clears the duplicate and the invalid flags
  and exits, without performing duplicate detection.
- ``print_pairs`` hides pairs flagged as invalid by default; the new
  ``--include-invalid`` option lists them as well, adding an ``invalid``
  column to the table.
- Fixed the non-paged table output (``--no-pager``): when a table was
  printed in more than one batch, all the batches but the last one were
  replaced by their header, so most of the rows were lost.
- Long database operations can now be interrupted with ``Ctrl+C``
  (pressed twice within 2 seconds): the running query is stopped and its
  database connection is closed, so that no stray ``-wal``/``-shm``
  files are left behind.
- Stylized ``◀◀ RƎQuake`` logo, shown in the command line help.
- Colored terminal output for help and usage messages, log messages,
  errors, table headers and waveform-cache diagnostics. Colors are used
  only on interactive terminals, and are therefore automatically removed
  when the output is piped or redirected. The ``NO_COLOR`` and
  ``FORCE_COLOR`` environment variables can be used to force colors off
  or on.
- New interactive curses pager for all ``print_`` commands
  (``print_catalog``, ``print_pairs``, ``print_families``).
  Automatically activated when output is a terminal; use ``--no-pager``
  to fall back to plain-text output. Requesting a specific output format
  with ``-f``/``--format`` implies ``--no-pager``.
- New ``-b/--backend`` option for ``map_families``, to plot families on
  an interactive HTML map using
  [folium](https://python-visualization.github.io/folium/), instead of
  the default static Cartopy map. Folium is an optional dependency (not
  installed by default): the folium backend is only used if folium is
  installed.
- Family marker size is now scaled with a quantity selected with the new
  ``-s/--sizeby`` option (default: number of events), and a legend on the
  map explains the marker size. This applies to both the Cartopy and the
  Folium map backends.

## [0.8.3] - 2026-06-19

Note: you should run `requake update_config` to update your config file
to the latest version.

The waveform disk cache is now a single SQLite database
(`OUTDIR/waveform_cache.sqlite`) with a persistent negative cache that
remembers failed downloads across runs, eliminating redundant HTTP requests.

- New `wfcache` CLI: `prefetch`, `print`/`inspect`, `extract`,
  `reset-failures`.
- New config: `catalog_waveform_cache_failure_max_retries`,
  `catalog_waveform_cache_failure_backoff_s`,
  `catalog_waveform_require_prefetch`.
- Several optimization for parallel runs in `scan_catalog` (especially on
  Slurm clusters) and for startup time of `scan_catalog -c` (continue an
  interrupted scan).
- Extended documentation for `read_catalog`, `scan_catalog` and `wfcache`.

## [0.8.2] - 2026-06-03

Note: you might want to run `requake update_config` to update your config file
to the latest version.

- Parallel processing of earthquake pairs in `scan_catalog`. On by default
  with automatic detection of the number of worker processes. This can be
  configured with the `catalog_scan_nprocs` config option.

## [0.8.1] - 2026-05-31

- Slimmed-down DB size by optimizing `event_pairs` storage. This allows storing
  also invalid pairs, so that resuming catalog scan is faster.
- Dramatic speedup of event pairs building by using a KD-tree
  spatial index and approximate geodetic distance calculations.
- Dramatic speedup of waveform fetching by improving the caching mechanism.
  A new config option `catalog_waveform_cache_size` allows to set the maximum
  number of waveforms to cache.
- Dramatically faster reading of event pairs with cross-correlation
  filters in large catalogs, thanks to the new SQLite-backed storage.
- Add an optional disk cache, through the `catalog_waveform_disk_cache_enabled`
  config option.
- `scan_catalog`: when running as a batch job, log a progress
  report every minute, instead of showing the progress bar.
- `scan_catalog`: if event pairs already exist in the database,
  ask whether to overwrite or continue from an interrupted run.
  Add `--force` to restart from scratch and `--force-continue`
  (short `-c`) to resume without prompting.
- `print_families`: add horizontal and vertical distance min/max values
  to both summary and detailed (`-d`) outputs.
- `print_families`: add `-f stats` output format for summary family
  statistics.

## [0.8] - 2026-05-22

This release introduces a major storage change.

Requake now stores scan-related data (catalog, event pairs, and families) in a
SQLite database instead of CSV files. This improves storage efficiency and
data access performance, especially for large catalogs.

This change is not backward compatible at the data format level. The
high-level behavior of the command-line interface remains unchanged.

Note: further improvements based on this new storage system will be introduced
throughout the 0.8.x release series.

## [0.7.3] - 2026-04-14

This release is intended to validate the new release workflow.
It introduces no new features or bug fixes.

## [0.7.2] - 2026-04-13

This release is intended to validate the new release workflow.
It introduces no new features or bug fixes.

## [0.7.1] - 2026-04-13

This release is intended to validate the new release workflow.
It introduces no new features or bug fixes.

## [0.7] - 2026-04-10

This version requires at least Python 3.9.

Note: you might want to run `requake update_config` to update your config file
to the latest version.

- New option `--shorterthan` to select families with a duration shorter than a
  given value. For this option and for `--longerthan` it is now possible to
  specify the duration in seconds, minutes, hours, or months, in addition to
  days and years.
- New option `--colorby` for many plot commands, to color families by a
  specific attribute other than the family number
- New option `--colormap` for many plot commands, to select a colormap
  for coloring families. If not specified, a default colormap for each
  attribute specified in `--colorby` is used.
- New option `--range` to manually specify the range of values for the color
  scale
- New option `--force` for commands that write files, to overwrite existing
  files without asking
- New option `--freq_band` for trace plotting commands, to override the
  frequency band specified in the config file
- New option `--detailed` for `print_families`, to print more detailed
  information about each family, including the list of events
- New option `--output` to save plots to files instead of showing them on
  screen
- Config option `waveform_data_path` renamed to `sds_data_path`
- New config option `event_data_path` to specify the path to a local directory
  with waveform files organized per event
- Add missing `street` map style for `map_families`
- Catalog scan: when more than a station is provided and the closest station
  to the event is not available, use the next closest station instead.
- Catalog scan: accurate estimation of the number of event pairs to process
- Initial support for plotting families found with template scan
- Improved reading of CSV catalog files:
  - avoid duplicated column guessing
  - ensure that prefectly matching column field names are correctly guessed
  - warn if an invalid time format is found
- Colored terminal output for warnings and errors

## [0.6] - 2024-05-04

Note: you might want to run `requake update_config` to update your config file
to the latest version.

- Verb `plot_slip` renamed to `plot_cumulative`. This new verb has new options
  to plot cumulative slip, cumulative moment, and cumulative number of events,
  and to make the plot logarithmic.
- New verb `print_catalog`: print the event catalog to screen
- New verb `print_pairs`: print the event pairs to screen
- `print_families`: also print minimum and maximum family magnitudes
- Additional models to convert magnitude to slip. Currently supported models
  are: Nadeau and Johnson (1998), Beeler et al. (2001), Eshelby (1957).
  Model selection is done using the `mag_to_slip_model` config parameter.
- New verb `update_config`: update an existing config file to the latest
  version

## [0.5] - 2024-04-23

- New config options: `station_metadata_path` and `waveform_data_path` to
  read station metadata and waveform data from files. Supports any metadata
  format supported by ObsPy and SDS (SeisComp Data Structure) waveform
  archives.
- Filter catalog files on reading using the criteria in the config file
- Improved time axes in `plot_timespans` and `plot_slip` for short time
  intervals
- `print_families`: autoset duration units based on the average duration
- `plot_timespans`: default sorting changed to `family_number`

## [0.4.1] - 2024-03-11

- Bugfix: `requake` executable was not installed

## [0.4] - 2024-03-11

- Package license changed to GPL-3.0 or later
- New verb: `read_catalog`: read a catalog from web services or from a file
  (FDSN text, QuakeML, or CSV)
- New verb: `scan_templates`: scan a continuous waveform stream using one
  or more templates. Templates can be from families or from file
- New verb: `print_families`: print families to screen
- New verb: `plot_slip`: plot cumulative slip for one or more families
- New config parameter: `clustering_algorithm` to select the algorithm
  for building event families. Currently supported options are `shared` and
  `UPGMA` (default: `shared`)
- `family_numbers` argument is no more mandatory (default: `all`)
  - argument added to `map_families` and `plot_timespans`
- Config parameter `trace_average_from_normalized_traces` renamed to
  `normalize_traces_before_averaging`
- `plot_timespans`: possibility to sort by `family_number`
- New options for `map_families` to select a map style and a zoom level for the
  map tiles
- New option `--minevents` (`-m`) for many verbs, to select families with a
  minimum number of events
- Support for events with no location
- Bugfix: `plot_timespans`: correctly plot x time axis when sort by `time`

## [0.3] - 2021-11-08

- New verb: `build_templates`
- New option: `cc_allow_negative` to search for anticorrelated events
- New progressbar, using `tqdm`
- `plot_families`:
  - show average trace
  - pan/zoom traces using arrows
  - show/hide theoretical arrivals using 'a' (command line option removed)
  - show event origin time as y-label
  - show trace mean CC
  - also shift theoretical arrivals when aligning traces
- Bugfix: last family was not read from family file

## [0.2] - 2021-09-24

Mostly a bugfix release with a slightly improved trace plotting.

- Bugfix: `scan_catalog` could not run properly due to missing variable
- Bugfix: detrend traces before filtering
- `plot_families`: print number of events and station-event distance

## [0.1] - 2021-09-16

- Initial release, not yet feature complete

[unreleased]: https://github.com/SeismicSource/requake/compare/v0.8.3...HEAD
[0.8.3]: https://github.com/SeismicSource/requake/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/SeismicSource/requake/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/SeismicSource/requake/compare/v0.8...v0.8.1
[0.8]: https://github.com/SeismicSource/requake/compare/v0.7.3...v0.8
[0.7.3]: https://github.com/SeismicSource/requake/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/SeismicSource/requake/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/SeismicSource/requake/compare/v0.7...v0.7.1
[0.7]: https://github.com/SeismicSource/requake/compare/v0.6...v0.7
[0.6]: https://github.com/SeismicSource/requake/compare/v0.5...v0.6
[0.5]: https://github.com/SeismicSource/requake/compare/v0.4.1...v0.5
[0.4.1]: https://github.com/SeismicSource/requake/compare/v0.4...v0.4.1
[0.4]: https://github.com/SeismicSource/requake/compare/v0.3...v0.4
[0.3]: https://github.com/SeismicSource/requake/compare/v0.2...v0.3
[0.2]: https://github.com/SeismicSource/requake/compare/v0.1...v0.2
[0.1]: https://github.com/SeismicSource/requake/releases/tag/v0.1
