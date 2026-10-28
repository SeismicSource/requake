Performances
------------

* ``requake scan catalog`` is designed to fully utilize available CPU cores by
  processing earthquake pairs in parallel. On an M2 MacBook Air, scanning
  95,034 earthquake pairs downloaded via FDSNWS took approximately 5 minutes
  using 7 worker processes, yielding ~19,000 pairs per minute. When repeating
  the same scan with a fully cached set of waveforms, runtime dropped to 84
  seconds (~68,000 pairs per minute). These results indicate that overall
  performance is typically dominated by waveform download latency rather than
  computation.

* For large FDSN-based runs, use ``requake wfcache prefetch`` before
  ``requake scan catalog`` to download all waveforms upfront into a local
  SQLite cache.  This eliminates repeated downloads, lets the scan read
  exclusively from disk, and is the single most effective way to speed up
  catalog scanning.

* ``requake build families`` is fast™ with the default ``shared``
  method, whose time and memory grow with the number of stored pairs
  above ``cc_min``.  The ``UPGMA`` method instead needs a distance
  matrix over the events linked by those pairs, so its memory use
  grows with the square of their number: what counts is how many
  events have a pair above ``cc_min``, not the catalog size.  For
  reference, ``UPGMA`` completed on a catalog of 93,000 events in
  which about 15,000 were linked by pairs above ``cc_min``, that is a
  matrix of about 109 million distances (see
  :doc:`build_families`).
