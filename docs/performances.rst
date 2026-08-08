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
* ``requake scan_templates`` cross-correlates each template against the
  continuous data in chunks of ``time_chunk`` seconds. Computation time as a
  function of ``time_chunk`` follows a U-shaped curve: very small chunks issue
  many short data requests, while very large chunks make each
  cross-correlation slow and memory-hungry. On the test datasets a chunk of
  one day to two weeks was a good compromise; values of about one month or
  more were markedly slower.

* The ``decim_factor`` option decimates the template and the continuous data
  before cross-correlation, trading a little resolution for speed. A factor of
  2 left detection cross-correlations essentially unchanged on 100 Hz data.
  Keep the resulting Nyquist frequency (``sampling_rate / (2 * decim_factor)``)
  above ``cc_freq_max``.
