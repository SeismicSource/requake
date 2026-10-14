Running
-------

Command line arguments
^^^^^^^^^^^^^^^^^^^^^^

Requake is based on a single executable, aptly named ``requake`` 😉.

To get help, use:

.. code-block::

   requake -h


Different commands are available:

.. code-block:: text

   sample_config       write sample config file to current directory and exit
   update_config       update an existing config file to the latest version
   read_catalog        read an event catalog from web services or from a file
   print_catalog       print the event catalog to screen
   scan_catalog        scan an existing catalog for earthquake pairs
   print_pairs         print pairs to screen
   dedup_events        detect and flag duplicate events in the catalog from
                       close event pairs
   plot_pair           plot traces for a given event pair
   build_families      build families of repeating earthquakes from a catalog
                       of pairs
   print_families      print families to screen
   plot_families       plot traces for one or more event families
   plot_timespans      plot family timespans
   plot_cumulative     cumulative plot for one or more families
   map_families        plot families on a map
   flag_family         flag a family of repeating earthquakes as valid or not
                       valid.
   build_templates     build waveform templates for one or more event
                       families
   scan_templates      scan a continuous waveform stream using one or more
                       templates
   wfcache             manage persistent waveform cache (prefetch, print,
                       inspect, extract, reset_failures)


Certain commands (e.g., ``plot_pair``\ ) require further arguments
(use, e.g., ``requake plot_pair -h`` to get help).

Requake supports command line tab completion for commands and arguments, thanks
to `argcomplete <https://kislyuk.github.io/argcomplete/>`_.
To enable command line tab completion run:

.. code-block::

    activate-global-python-argcomplete


(This is a one-time command that needs to be run only once).

Or, alternatively, add the following line to your ``.bashrc`` or ``.zshrc``:

.. code-block::

    eval "$(register-python-argcomplete requake)"


Colored output
^^^^^^^^^^^^^^

Terminal output (help and usage messages, log messages, tables and
waveform-cache diagnostics) is colored when writing to an interactive
terminal. Colors are automatically removed when the output is
redirected to a file or piped to another command.

The standard `NO_COLOR <https://no-color.org/>`_ environment variable
can be used to disable colors (e.g. when colors are not desired in a
terminal), while setting the ``FORCE_COLOR`` environment variable
forces colors on even when the output is piped.


Typical workflow
^^^^^^^^^^^^^^^^

The first thing you will want to do is to generate a sample
:ref:`configuration_file`:

.. code-block::

   requake sample_config


Edit the :ref:`configuration_file` according to your needs, then read or
download the event catalog:

.. code-block::

   requake read_catalog


or

.. code-block::

   requake read_catalog CATALOG_FILE


When relying on FDSN web services for waveform data, it is strongly
recommended to prefetch all waveform windows before running the scan.
This downloads every required waveform once and stores it in a local
SQLite cache, avoiding repeated downloads and dramatically reducing
overall runtime for large catalogs:

.. code-block::

   requake wfcache prefetch


Now, build the catalog of event pairs with:

.. code-block::

   requake scan_catalog


Once done (:doc:`it will take time! <performances>`),
you are ready to build repeating earthquake families:

.. code-block::

   requake build_families


Flagging duplicate events
^^^^^^^^^^^^^^^^^^^^^^^^^

Event catalogs often contain the same earthquake more than once (for
example, the same event reported by different agencies or with slightly
different origin times).  Since duplicates would artificially inflate
families, they can be flagged before building families:

.. code-block::

   requake dedup_events

The command looks for event pairs with a high cross-correlation
coefficient which are also close in time and space: these are very
likely to be the same earthquake.  The thresholds can be changed from
the command line:

* ``-c``/``--cc_min``: minimum cross-correlation coefficient
  (default: ``0.98``);
* ``-t``/``--max-time-diff``: maximum origin-time difference, in
  seconds (default: ``60``);
* ``-d``/``--max-distance``: maximum horizontal distance, in km
  (default: ``2``).

Within each group of duplicate events, one event is kept and the others
are flagged as duplicated in the :doc:`catalog <database_schemas>`
(the ``duplicate`` column).  All the event pairs involving a duplicated
event are flagged as invalid (the ``invalid`` column of the
``event_pairs`` table), so that they are ignored by
``requake build_families``.

A report of the duplicate pairs and groups found is printed at the end.
The report is intentionally compact for large catalogs: it lists at most
the first 20 duplicate pairs and the first 20 duplicate groups, while the
counts always refer to the whole dataset.  Use ``-n``/``--dry-run`` to
print the report without modifying the database.

The flags can be cleared with ``--reset``, which resets the ``duplicate``
column of the catalog and the ``invalid`` column of the event pairs, and
exits without performing duplicate detection (combine with ``-n`` to only
report what would be cleared).  Since it scans the whole event-pairs
table, it can take a while on large catalogs.  Long database
operations like this one can be interrupted with ``Ctrl+C`` (press it
twice within 2 seconds to confirm): the running query is stopped and
the database is closed cleanly.  For example:

.. code-block::

   requake dedup_events --reset

The invalid pairs are hidden by ``requake print_pairs`` (use
``--include-invalid`` to list them, see below) and ignored by
``requake build_families``.

Note that a full re-scan of the catalog (``requake scan_catalog`` with
overwrite) recreates the event pairs, so ``requake dedup_events``
must be run again afterwards.


Plotting families on a map
^^^^^^^^^^^^^^^^^^^^^^^^^^

Once families are built, they can be plotted on a map with:

.. code-block::

   requake map_families


Two map backends are available, selected with ``-b/--backend``:

``cartopy`` (default)
   Produce a static image, using Matplotlib and Cartopy. The output
   format is determined by the ``-o/--output`` file extension (e.g.,
   ``.png``, ``.pdf``, ``.svg``).

``folium``
   Produce an interactive HTML map. This backend requires the optional
   ``folium`` package (see :doc:`installation`) and the output must be
   an HTML file, e.g.:

   .. code-block::

      requake map_families -b folium -o family_map.html


   Use ``-o html`` to save the map to the default file name
   (``family_map.html``), or omit ``-o`` to open the map in the default
   web browser.

In both cases, the base map style is selected with ``-M/--mapstyle`` and
the families are colored according to ``-c/--colorby``, with the
corresponding colorbar shown on the map. The family marker size is scaled
with the ``-s/--sizeby`` quantity (default: ``number_of_events``), and a
legend on the map explains the marker size. A logarithmic scale is used
when the values span more than one order of magnitude. With the folium
backend, the base map styles can also be switched interactively and
clicking on a family marker shows the family details. The
``stamen_terrain`` map style requires an API key, to be provided with
``-k/--apikey``.


Interactive pager
^^^^^^^^^^^^^^^^^

All ``print_`` commands (``print_catalog``, ``print_pairs``,
``print_families``) open an interactive `curses <https://en.wikipedia.org/wiki/Curses_(programming_library)>`_ pager when the output is
a terminal.  Use ``--no-pager`` to fall back to plain-text output
(e.g., for piping to ``wc`` or ``grep``).  Requesting a specific
output format with ``-f``/``--format`` implies ``--no-pager``, since
the pager draws the table with its own layout and ignores the output
format.

Navigation
""""""""""

============= ===========================================
Key           Action
============= ===========================================
``↓`` ``↑``   Move selection down / up one row
``j`` ``k``   Same as ``↓`` / ``↑`` (vim-style)
``Space``     Page down
``f``         Page down
``b``         Page up
``g``         Jump to first row (home)
``G``         Jump to last row (end)
``Enter``     Show row details in a popup
``←`` ``→``   Scroll horizontally
``⇧←``        Jump to beginning of line
``⇧→``        Jump to end of line
``⇧↑``        Page up
``⇧↓``        Page down
============= ===========================================

Sorting
"""""""

============= ===========================================
Key           Action
============= ===========================================
``1``-``9``   Sort by column (1 = first, 9 = ninth)
``0``         Restore default sort order
``s``         Open interactive sort column selector
============= ===========================================

Clipboard
"""""""""

Pressing ``c`` copies the selected row's identifier(s) to the
system clipboard.  For the pairs table both event IDs are copied
(space-separated).

Pairs large-dataset warning
"""""""""""""""""""""""""""

When more than 10,000 pairs match the current filter, ``print_pairs``
shows a confirmation prompt before opening the pager.  Use
``--cc-min`` / ``--cc-max`` to narrow the selection, or ``--force``
to skip the warning.

Invalid pairs
"""""""""""""

``print_pairs`` shows only valid pairs.  Pairs flagged as invalid (see
`Flagging duplicate events`_), i.e. pairs involving an event marked as
duplicate, are hidden.  Use ``--include-invalid`` to list them as well;
an ``invalid`` column is then added to the table, and the table can be
sorted on it to show the invalid pairs first.

