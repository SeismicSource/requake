Performances
------------

* ``requake scan_catalog`` is designed to fully utilize available CPU cores by
  processing earthquake pairs in parallel. On an M2 MacBook Air, scanning
  95,034 earthquake pairs downloaded via FDSNWS took approximately 5 minutes
  using 7 worker processes, yielding ~19,000 pairs per minute. When repeating
  the same scan with a fully cached set of waveforms, runtime dropped to 84
  seconds (~68,000 pairs per minute). These results indicate that overall
  performance is typically dominated by waveform download latency rather than
  computation.

* For large FDSN-based runs, use ``requake wfcache prefetch`` before
  ``requake scan_catalog`` to download all waveforms upfront into a local
  SQLite cache.  This eliminates repeated downloads, lets the scan read
  exclusively from disk, and is the single most effective way to speed up
  catalog scanning.

* ``requake build_families`` is fast™.