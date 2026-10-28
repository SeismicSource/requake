########
Running
########

Command line arguments
----------------------

Requake is based on a single executable, aptly named ``requake`` 😉.

For a summary of the commands, and for the options of each command,
use:

.. code-block::

   requake -h
   requake COMMAND -h


Requake supports command line tab completion for commands and arguments,
thanks to `argcomplete <https://kislyuk.github.io/argcomplete/>`_.
To enable command line tab completion run:

.. code-block::

   activate-global-python-argcomplete


(This is a one-time command that needs to be run only once).

Or, alternatively, add the following line to your ``.bashrc`` or ``.zshrc``:

.. code-block::

   eval "$(register-python-argcomplete requake)"


Commands
--------

Typing ``requake`` with no arguments lists all the commands:

.. code-block:: text

   sample_config       write sample config file to current directory and exit
   update_config       update an existing config file to the latest version
   read_catalog        read an event catalog from web services or from a file
   print_catalog       print the event catalog to screen
   print_catalogs      list the catalogs stored in the database
   scan_catalog        scan an existing catalog for earthquake pairs
   print_scans         list the catalog scans stored in the database
   print_pairs         print pairs to screen
   dedup_events        detect and flag duplicate events in the catalog from
                       close event pairs
   plot_pair           plot traces for a given event pair
   build_families      build families of repeating earthquakes from a catalog
                       of pairs
   print_families      print families to screen
   print_family_builds
                       list the family builds stored in the database
   plot_families       plot traces for one or more event families
   plot_timespans      plot family timespans
   plot_cumulative     cumulative plot for one or more families
   map_families        plot families on a map
   flag_family         flag a family of repeating earthquakes as valid or not
                       valid
   build_templates     build waveform templates for one or more event
                       families
   scan_templates      scan a continuous waveform stream using one or more
                       templates
   wfcache             manage persistent waveform cache
   delete              delete a catalog, a catalog scan or a family build


The commands are described below by analysis stage; each group links to
the page documenting it in detail, when there is one.  Families and
templates commands will get their own pages in the future.


Setting up
^^^^^^^^^^

``sample_config``
   Write a sample :ref:`configuration file <configuration_file>` to the
   current directory and exit.

``update_config``
   Update an existing configuration file to the latest version.


Reading and inspecting the catalog
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``read_catalog``
   Read an event catalog from FDSN web services or from a local file
   and store it in the output database (see :doc:`read_catalog`).

``print_catalog``
   Print the stored catalog to screen, in the interactive
   :doc:`pager` or in plain text.

``print_catalogs``
   List the catalogs stored in the database, or show the details of a
   single one (see :doc:`catalogs_scans_builds`).


Searching event pairs
^^^^^^^^^^^^^^^^^^^^^

``scan_catalog``
   Compare the catalog events with each other and store the similar
   event pairs (see :doc:`scan_catalog`); for the runtime, see
   :doc:`performances`.

``print_pairs``, ``plot_pair``, ``dedup_events``
   Print the event pairs, plot the waveforms of a single pair, or
   detect and flag duplicate events (see :doc:`pairs`).

``print_scans``
   List the catalog scans stored in the database, with their status and
   pair counts, or show the details of a single one (see
   :doc:`catalogs_scans_builds`).


Building families
^^^^^^^^^^^^^^^^^

``build_families``
   Group the event pairs into families of repeating earthquakes.

``flag_family``
   Flag a family as valid or not valid.

``print_families``
   Print one row per family, or one row per event, as a table or in
   CSV or Markdown format.

``print_family_builds``
   List the family builds stored in the database, with the scan and the
   clustering method each of them used (see
   :doc:`catalogs_scans_builds`).

``plot_families``
   Plot the aligned waveforms of each family, with the family average.

``plot_timespans``
   Plot the time span of each family, with one family per row.

``plot_cumulative``
   Plot the cumulative slip, moment or number of events of the
   families over time.

``map_families``
   Plot the families on a map, as a static image or as an interactive
   HTML map.


Building and scanning templates
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``build_templates``
   Build waveform templates from one or more families.

``scan_templates``
   Scan a continuous waveform stream with the templates, to detect new
   events by template matching.


Waveform cache
^^^^^^^^^^^^^^

``wfcache``
   Manage the persistent waveform cache, with the ``prefetch``,
   ``print``, ``inspect``, ``extract`` and ``reset-failures``
   subcommands (see :doc:`wfcache`).


Deleting results
^^^^^^^^^^^^^^^^

``delete``
   Delete a catalog, a catalog scan or a family build, with the
   ``catalog``, ``scan`` and ``build`` subcommands.  The deletion is
   cascading and asks for confirmation; ``-n``/``--dry-run`` shows
   what would be removed without touching the database (see
   :doc:`catalogs_scans_builds`).

The ``print_`` commands open an interactive pager on the terminal, to
scroll, sort and copy the table rows (see :doc:`pager`).


Typical workflow
----------------

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


Once done (:doc:`it will take time! <performances>`), flag the
duplicate events, if any (see :doc:`pairs`), so that they do not
inflate the families:

.. code-block::

   requake dedup_events


Then, build the repeating earthquake families:

.. code-block::

   requake build_families


Inspect the families with ``print_families``, ``plot_families`` and
``map_families`` (see `Building families`_).
