.. _wfcache:

#########################
Waveform Cache Management
#########################

The ``requake wfcache`` command manages a persistent, on-disk SQLite cache
of waveform windows (``OUTDIR/waveform_cache.sqlite``).  Populating this
cache before a :doc:`catalog scan <scan_catalog>` avoids repeated FDSN
downloads and dramatically speeds up large catalog-based searches.

``wfcache`` provides five subcommands:

.. code-block:: text

   requake wfcache prefetch     pre-download waveform windows into the cache
   requake wfcache inspect      print cache diagnostics and summary
   requake wfcache print        list cached waveform entries
   requake wfcache extract      export cached waveforms to files
   requake wfcache reset-failures
                                reset download-failure records

All subcommands support ``-h`` for detailed help (e.g.,
``requake wfcache prefetch -h``).


prefetch
--------

::

    requake wfcache prefetch

Reads the stored event catalog and downloads, for every event and
configured trace ID, the waveform window that
:doc:`scan_catalog` would need.  Downloaded waveforms are stored in
the persistent SQLite cache and are immediately available to subsequent
scans.

Prefetch also records download failures in a *negative cache* so that
repeated attempts to fetch permanently unavailable data are suppressed.

**Key options:**

``--event-id EVENT_ID`` (repeatable)
  Restrict prefetch to specific event IDs.

``--event-id-file PATH``
  Read event IDs from a text file (one per line, ``#`` for comments).

``--trace-id TRACE_ID`` (repeatable)
  Restrict prefetch to specific trace IDs.  Defaults to
  ``catalog_trace_id`` from the configuration.

``--max-events N``
  Limit prefetch to the first *N* catalog events (useful for testing).

``--batch-size N``
  Progress logging granularity (default: 500).

``--group-window DURATION``
  Maximum time span for grouped FDSN downloads (e.g., ``30m``, ``1h``;
  default: ``1h``).  Larger windows reduce the number of HTTP requests
  but increase individual download size.


inspect
-------

::

    requake wfcache inspect

Prints a summary of the waveform cache: file path, file size, schema
version, number of cached waveform rows, time span, and the most
represented trace IDs.  Also reports the state of the negative cache
(total, exhausted, and retry-pending failure records).

**Key options:**

``--integrity``
  Run ``PRAGMA integrity_check`` on the cache database.

``--json``
  Output the summary as JSON.


print
-----

::

    requake wfcache print

Lists cached waveform entries, one per line.  Each entry includes the
event ID, trace ID, start and end time.

**Key options:**

``--event-id EVENT_ID``, ``--event-id-file PATH``, ``--trace-id TRACE_ID``, ``--start-time TIME``, ``--end-time TIME``, ``--limit N``
  Filter the listed rows.

``--json``
  Output rows as a JSON array.


extract
-------

::

    requake wfcache extract

Exports cached waveform windows to standalone files (miniSEED or SAC),
one per row.  Files are written to the directory specified by
``--output-dir`` (default: ``waveform_cache``).

**Key options:**

``--event-id EVENT_ID``, ``--event-id-file PATH``, ``--trace-id TRACE_ID``, ``--start-time TIME``, ``--end-time TIME``, ``--limit N``
  Filter which rows to extract.

``--format {mseed,sac}``
  Output format (default: ``mseed``).

``--output-dir DIR``
  Output directory (default: ``waveform_cache``).


reset-failures
--------------

::

    requake wfcache reset-failures

Clears records from the negative (failure) cache, allowing Requake to
retry downloads that previously failed — for example after a temporary
network outage.

**Key options:**

``--event-id EVENT_ID``, ``--event-id-file PATH``
  Reset failures only for specific events.

``--older-than DURATION``
  Reset only records older than the given duration (e.g., ``24h``,
  ``7d``).

``--all``
  Reset all failure records regardless of event or age.

``--dry-run``
  Report how many rows would be reset without actually modifying the
  cache.
