# Requake Changelog

Copyright (c) 2021-2024 Claudio Satriano <satriano@ipgp.fr>

## v0.6 - 2024-05-04

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

## v0.5 - 2024-04-23

- New config options: `station_metadata_path` and `waveform_data_path` to
  read station metadata and waveform data from files. Supports any metadata
  format supported by ObsPy and SDS (SeisComp Data Structure) waveform
  archives.
- Filter catalog files on reading using the criteria in the config file
- Improved time axes in `plot_timespans` and `plot_slip` for short time
  intervals
- `print_families`: autoset duration units based on the average duration
- `plot_timespans`: default sorting changed to `family_number`

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
