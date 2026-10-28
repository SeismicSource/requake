.. _pairs:

###########
Event Pairs
###########

Every couple of events compared by :doc:`requake scan_catalog
<scan_catalog>` is stored as an *event pair* in the ``event_pairs``
table of the output database (see :doc:`database_schemas`).  Pairs are
the building blocks of repeating-earthquake families: events connected
by pairs with similar waveforms are grouped into families by
``requake build_families``.

Requake provides three commands to inspect and curate the event pairs:

.. code-block:: text

   requake print_pairs     print pairs to screen
   requake plot_pair       plot traces for a given event pair
   requake dedup_events    detect and flag duplicate events in the
                           catalog from close event pairs

All of them read the output directory (``OUTDIR``) and the parameters
from the :doc:`configuration file <configuration_file>`.
Use ``requake <command> -h`` to get the full list of options of each
command.

The pairs belong to a catalog scan: ``print_pairs`` and
``dedup_events`` use the latest scan, unless another one is selected
with ``--scan-id``.  See :doc:`catalogs_scans_builds`.


print_pairs
-----------

``requake print_pairs`` prints one row per successfully cross-correlated
pair, with the ID, origin time, coordinates, depth, magnitude type and
magnitude of both events, plus the trace ID, the lag and the maximum
cross-correlation coefficient :math:`CC_\mathrm{max}`.  Pairs that could
not be analysed are stored in the database but not listed:

.. code-block::

   requake print_pairs

``-c``/``--cc_min`` and ``-C``/``--cc_max`` restrict the selection to a
:math:`CC_\mathrm{max}` range.  Pairs flagged as invalid by
`dedup_events`_ are hidden unless ``--include-invalid`` is used, which
adds an ``invalid`` column to the table.

In the interactive pager (see :doc:`the interactive pager <pager>`) the
table can be sorted on any column, and pressing ``c`` copies the event
IDs of the selected pair.  Use ``--no-pager`` for plain-text output, or
``-f``/``--format`` to select ``simple`` (default), ``markdown`` or
``csv``; requesting a format implies ``--no-pager``.

When more than 10,000 pairs match the selection, a confirmation prompt
is shown; use ``--force`` to skip it.  For example:

.. code-block::

   requake print_pairs -c 0.95 -f csv > pairs.csv


plot_pair
---------

``requake plot_pair`` plots the waveforms of two events, aligned and
processed as in the scan, and logs their lag and cross-correlation
coefficient:

.. code-block::

   requake plot_pair EVID1 EVID2

Waveforms come from the :doc:`waveform cache <wfcache>` when available
and are downloaded otherwise, using the same trace ID selection as the
scan.  The waveform window and the processing parameters are those of
the scan (see the :doc:`configuration file <configuration_file>`).
Use ``-t``/``--traceid`` to force a trace ID and ``-F``/``--freq_band``
(``FREQ_MIN FREQ_MAX`` in Hz) to force the frequency band.

Use ``-o``/``--output`` to save the plot instead of displaying it: give
a file name (e.g. ``pair.png``), a format (``png``, ``pdf``, ``svg``,
``jpg``, ``jpeg``) to generate the default file name, or no value to
write a PNG with the default name.  For example:

.. code-block::

   requake plot_pair 12345 67890 -o pdf

To plot all the events of a family, use ``requake plot_families``.


dedup_events
------------

Event catalogs often contain the same earthquake more than once, for
example when the same event is reported by different agencies or with
slightly different origin times.  Since duplicates would artificially
inflate families, they can be flagged before building families:

.. code-block::

   requake dedup_events

The command works on the stored event pairs, so
:doc:`requake scan_catalog <scan_catalog>` must have been run first.  A
pair is a duplicate candidate when :math:`CC_\mathrm{max} \ge`
``cc_min`` (default ``0.98``), the origin-time difference is at most
``max_time_diff`` seconds (default ``60``) and the horizontal distance
is at most ``max_distance`` km (default ``2``).  These thresholds are
set with ``-c``/``--cc_min``, ``-t``/``--max-time-diff`` and
``-d``/``--max-distance``.

Candidate pairs are merged into groups, and within each group one event
is kept (preferring events not already flagged, higher magnitude, more
complete metadata, earlier origin time and smaller ID) while the others
are flagged as duplicates.

Duplicate events are flagged in the :doc:`catalog <database_schemas>`
(``duplicate`` column), and all the pairs involving them are flagged as
invalid (``invalid`` column); invalid pairs are ignored by
``requake build_families`` and hidden by ``requake print_pairs``.  A
compact report with the duplicate pairs and groups is printed at the
end.

``-n``/``--dry-run`` prints the report without modifying the database.
``--reset`` clears both flags and exits without performing detection
(combine with ``-n`` to only report what would be cleared).  Long steps
show a progress indicator and can be interrupted with ``Ctrl+C``
(press it twice to confirm).

.. note::

   Duplicate flags belong to the catalog, invalid flags to the scan.
   Rerunning ``requake scan_catalog`` on the same catalog keeps the
   duplicate flags but creates a new scan whose pairs are all valid:
   run ``requake dedup_events`` again after the new scan.
