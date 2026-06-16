.. _scan_catalog:

############
Catalog Scan
############

The command ``requake scan_catalog`` is the core of Requake's
catalog-based repeater search.  It compares every event in an earthquake
:doc:`catalog <read_catalog>` against its neighbours and identifies
pairs with highly similar waveforms — the building blocks of
repeating-earthquake families.

The scan is *single-station*: each event pair is compared using one
seismic trace at a time (``catalog_trace_id``).  If multiple trace IDs
are configured, the station closest to the event pair is selected.

The scan is parallelized across multiple CPU cores to handle large
catalogs efficiently.

This page describes how the scan works, what configuration parameters
control it, and how to get the best performance out of it.


Overview
--------

Given a :doc:`catalog <read_catalog>` of :math:`N` events, the scan
proceeds in three stages:

1. **Spatial grouping** — events are compared only if their epicentres
   lie within a configurable search radius (``catalog_search_range``).
   This reduces the naive :math:`\mathcal{O}(N^2)` pair count to a much
   smaller set of candidates.

2. **Waveform retrieval** — for each candidate pair, the required
   waveform windows are fetched (from FDSN web services, a local archive,
   or the on-disk cache) and cut around the P arrival.

3. **Cross-correlation** — the two waveforms are band-pass filtered
   between ``cc_freq_min`` and ``cc_freq_max`` Hz to isolate the
   frequency band of interest, then cross-correlated in the time domain.
   The maximum correlation coefficient :math:`CC_\mathrm{max}` is
   computed.  The result, together with the optimal lag, trace ID, and
   inter-event distance, is stored for every candidate pair in the
   :doc:`output database <database_schemas>`.

All the parameters mentioned above are described in the
:doc:`configuration file <configuration_file>`.


Spatial grouping
----------------

For each event in the catalog, Requake builds a list of neighbouring
events whose epicentral distance is within ``catalog_search_range``
kilometres.  Only these candidate pairs are passed to the waveform stage.

The spatial search uses a
`k-d tree <https://en.wikipedia.org/wiki/K-d_tree>`_ (implemented via
`scipy.spatial.cKDTree <https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html>`_)
over the 3‑D Cartesian coordinates of the events on the unit sphere,
which makes the neighbour lookup very fast even for large catalogs.

If ``catalog_search_range`` is set to zero (or negative), *every*
possible event pair is considered — useful for small catalogs, but
impractical for large ones.


Waveform retrieval
------------------

For each candidate pair, Requake retrieves a short waveform window
around the P‑wave arrival for one or more seismic traces
(``catalog_trace_id``).  The window starts ``cc_pre_P`` seconds before
the theoretical P arrival and lasts ``cc_trace_length`` seconds.

Waveforms can come from three sources, in order of priority:

1. **On-disk SQLite cache** (``OUTDIR/waveform_cache.sqlite``) —
   if ``catalog_waveform_disk_cache_enabled`` is ``true``, previously
   fetched waveforms are reused.  Use
   :doc:`requake wfcache prefetch <wfcache>` to populate this cache
   before the scan.

2. **In-memory cache** (sized by ``catalog_waveform_cache_size``) —
   waveforms for recently processed events are kept in RAM to avoid
   repeated fetches.

3. **FDSN web services** or **local archives** — if a waveform is not
   found in either cache, it is downloaded from the configured FDSN
   dataselect service or read from a local SDS directory or per-event
   data folder.

If multiple trace IDs are configured (comma-separated), Requake selects
the station closest to the event pair for each comparison.


Cross-correlation and pair selection
-------------------------------------

The cross-correlation step is controlled by the ``Processing parameters``
section of the :doc:`configuration file <configuration_file>`.  The
relevant parameters are:

``cc_pre_P``
  seconds of signal before the P arrival

``cc_trace_length``
  total waveform window length in seconds

``cc_freq_min``, ``cc_freq_max``
  band-pass filter corners in Hz

``cc_max_shift``
  maximum allowed lag in seconds

``cc_allow_negative``
  when ``true``, the largest absolute value of the correlation function
  is returned — be it positive (correlation) or negative
  (anti-correlation)

Each waveform pair undergoes the following processing:

- Both traces are band-pass filtered between ``cc_freq_min`` and
  ``cc_freq_max`` Hz.
- They are cross-correlated in the time domain using
  `obspy.signal.cross_correlation.correlate
  <https://docs.obspy.org/packages/autogen/obspy.signal.cross_correlation.correlate.html>`_,
  allowing a maximum lag of ``cc_max_shift`` seconds to account for
  travel-time differences.
- The maximum normalised cross-correlation coefficient
  :math:`CC_\mathrm{max}` is extracted with
  `obspy.signal.cross_correlation.xcorr_max
  <https://docs.obspy.org/packages/autogen/obspy.signal.cross_correlation.xcorr_max.html>`_.

Every candidate pair is written to the :doc:`output database
<database_schemas>` with its :math:`CC_\mathrm{max}`, optimal lag,
trace ID, and inter-event distance.

When ``cc_allow_negative`` is ``true``, the largest value — positive or
negative — of the cross-correlation function is stored, so both
correlated and anti-correlated pairs are recorded.


Parallel execution
------------------

The scan uses multiple worker processes to process pairs in parallel.
The number of workers is controlled by ``catalog_scan_nprocs``:
set it to ``0`` (the default) for automatic selection — one fewer than
the number of available CPU cores, ``1`` to run serially, or to a
specific number.

Each worker maintains its own in-memory waveform cache (sized by
``catalog_waveform_cache_size_parallel``, or derived automatically)
to minimise inter-process communication.


Resuming an interrupted scan
----------------------------

If the scan is interrupted (e.g., by a network outage or a user
pressing Ctrl‑C), running ``requake scan_catalog`` again will detect
the existing pairs in the database and offer to resume from where it
stopped.  Use ``--force-continue`` to skip the prompt in scripts.


Slurm clusters
--------------

Requake automatically detects when it is running inside a
`Slurm <https://en.wikipedia.org/wiki/Slurm_Workload_Manager>`_ job
(via the ``SLURM_JOB_ID`` environment variable) and adapts its
behaviour:

* **Worker count.**  When ``catalog_scan_nprocs`` is set to ``0``
  (automatic) and Slurm is detected, the number of workers is taken
  from the Slurm allocation (``SLURM_CPUS_PER_TASK``,
  ``SLURM_CPUS_ON_NODE``, or ``SLURM_JOB_CPUS_PER_NODE``, checked in
  that order).  Unlike local runs, the full allocated count is used
  without subtracting one.

* **Progress logging.**  Progress messages include the Slurm job ID,
  process ID, and node list, making it easier to monitor jobs in
  cluster logs.

* **Non-interactive mode.**  If a scan is interrupted on a cluster,
  Requake will not prompt for input (since ``stdin`` is typically not
  available).  Use ``--force`` to overwrite an existing scan or
  ``--force-continue`` to resume it.

.. note::

   Slurm integration has been developed and tested on the
   `IPGP S-CAPAD <https://www.ipgp.fr/la-recherche/services-communs/s-capad/>`_
   platform, which we gratefully acknowledge.


Performance tips
----------------

* **Prefetch waveforms.**  For large catalogs relying on FDSN sources,
  run :doc:`requake wfcache prefetch <wfcache>` before the scan.  This
  downloads all required waveform windows once and stores them in the
  local SQLite cache, letting the scan read from disk instead of the
  network.

* **Tune the search radius.**  A larger ``catalog_search_range`` finds
  more candidate pairs but increases runtime.  Choose a value that
  reflects the maximum expected distance between repeating events in
  your study area.

* **Limit memory.**  If you hit memory limits, reduce
  ``catalog_waveform_cache_size`` and let the on-disk cache handle
  persistence instead.
