# Requake - Repeating earthquakes search and analysis

(c) 2021-2024 Claudio Satriano <satriano@ipgp.fr>

## v0.4.1 - 2024-03-11

- Bugfix: `requake` executable was not installed

## v0.4 - 2024-03-11

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

## v0.3 - 2021-11-08

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

## v0.2 - 2021-09-24

Mostly a bugfix release with a slightly improved trace plotting.

- Bugfix: `scan_catalog` could not run properly due to missing variable
- Bugfix: detrend traces before filtering
- `plot_families`: print number of events and station-event distance

## v0.1 - 2021-09-16

- Initial release, not yet feature complete
