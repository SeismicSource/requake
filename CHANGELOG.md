# Requake - Repeating earthquakes search and analysis
(c) 2021 Claudio Satriano <satriano@ipgp.fr>

## unreleased
  - New progressbar, using `tqdm`
  - `plot_families`:
    - show event origin time as y-label
    - show trace mean CC
  - Bugfix: last family was not read from family file

## v0.2 - 2021-09-24
Mostly a bugfix release with a slightly improved trace plotting.

  - Bugfix: `scan_catalog` could not run properly due to missing variable
  - Bugfix: detrend traces before filtering
  - `plot_families`: print number of events and station-event distance

## v0.1 - 2021-09-16
  - Initial release, not yet feature complete
