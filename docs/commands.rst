.. _commands_page:

########
Commands
########

A Requake command is made of a verb, or of a namespace, followed by the
object the verb acts on:

.. code-block:: text

   requake <verb> <object> [options]

Typing ``requake`` with no arguments lists the verbs and what they are
for:

.. code-block:: text

   config              write or update the configuration file
   read                read a data set into the output database
   scan                search data already in the output database or new
                       waveforms
   build               build derived data from the output database
   print               print data to screen
   list                list the entries stored in the output database
   plot                plot data to screen or file
   flag                flag entries of the output database
   delete              delete a catalog, a catalog scan or a family build
   wfcache             manage the persistent waveform cache

Typing a verb alone lists the objects it can act on, together with what
the verb is for:

.. code-block:: text

   requake plot

To see the options of a command, add ``-h`` after its object:

.. code-block:: text

   requake plot map -h

Most commands act on the latest catalog, catalog scan or family build
stored in the output database; ``--catalog-id``, ``--scan-id`` and
``--build-id`` select a different one (see
:doc:`catalogs_scans_builds`).


Config Commands
---------------

``config sample``
   Write a sample :ref:`configuration file <configuration_file>` to the
   current directory and exit.

``config update [CONFIG_FILE]``
   Update an existing configuration file to the latest version.  The
   file is the positional argument, or the one given with
   ``-c``/``--configfile``.


Read Commands
-------------

``read catalog [CATALOG_FILE]``
   Read an event catalog from FDSN web services or from a local file
   and store it in the output database (see :doc:`read_catalog`).


Scan Commands
-------------

``scan catalog``
   Compare the catalog events with each other and store the similar
   event pairs (see :doc:`scan_catalog`); for the runtime, see
   :doc:`performances`.

``scan templates``
   Scan a continuous waveform stream with the templates, to detect new
   events by template matching.


Build Commands
--------------

``build families``
   Group the event pairs into families of repeating earthquakes.

``build templates``
   Build waveform templates from one or more families.


Print Commands
--------------

``print catalog``
   Print the stored catalog to screen, in the interactive
   :doc:`pager` or in plain text.

``print pairs``
   Print the event pairs to screen, optionally filtering them by
   cross-correlation coefficient (see :doc:`pairs`).

``print families``
   Print one row per family, or one row per event, as a table or in
   CSV or Markdown format.


List Commands
-------------

``list catalogs [CATALOG_ID]``
   List the catalogs stored in the database, with their source and
   their parameters, or show the details of a single one (see
   :doc:`catalogs_scans_builds`).

``list scans [SCAN_ID]``
   List the catalog scans stored in the database, with their status and
   their pair counts, or show the details of a single one (see
   :doc:`catalogs_scans_builds`).

``list builds [BUILD_ID]``
   List the family builds stored in the database, with the scan and the
   clustering method each of them used, or show the details of a single
   one (see :doc:`catalogs_scans_builds`).


Plot Commands
-------------

``plot pair``
   Plot the waveforms of a single event pair (see :doc:`pairs`).

``plot families``
   Plot the aligned waveforms of each family, with the family average.

``plot timespans``
   Plot the time span of each family, with one family per row.

``plot cumulative``
   Plot the cumulative slip, moment or number of events of the
   families over time.

``plot map``
   Plot the families on a map, as a static image or as an interactive
   HTML map.


Flag Commands
-------------

``flag family``
   Flag a family of repeating earthquakes as valid or not valid.

``flag duplicates``
   Detect and flag duplicate events in the catalog from close event
   pairs, so that they do not inflate the families (see
   :doc:`pairs`).


Delete Commands
---------------

``delete catalog``, ``delete scan``, ``delete build``
   Delete a catalog, a catalog scan or a family build.  The deletion is
   cascading and asks for confirmation; ``-n``/``--dry-run`` shows what
   would be removed without touching the database (see
   :doc:`catalogs_scans_builds`).


Wfcache Commands
----------------

``wfcache``
   Manage the persistent waveform cache, with the ``prefetch``,
   ``print``, ``inspect``, ``extract`` and ``reset-failures``
   subcommands (see :doc:`wfcache`).


Reading Tables
--------------

The ``print`` commands open an interactive pager on the terminal, to
scroll, sort and copy the table rows; ``--no-pager`` prints the table as
plain text instead (see :doc:`pager`).  The ``list`` commands always
print plain text.
