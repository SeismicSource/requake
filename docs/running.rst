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


Interactive pager
^^^^^^^^^^^^^^^^^

All ``print_`` commands (``print_catalog``, ``print_pairs``,
``print_families``) open an interactive `curses <https://en.wikipedia.org/wiki/Curses_(programming_library)>`_ pager when the output is
a terminal.  Use ``--no-pager`` to fall back to plain-text output
(e.g., for piping to ``wc`` or ``grep``).

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

