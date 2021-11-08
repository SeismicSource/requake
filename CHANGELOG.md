# Requake - Repeating earthquakes search and analysis
(c) 2021 Claudio Satriano <satriano@ipgp.fr>


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
