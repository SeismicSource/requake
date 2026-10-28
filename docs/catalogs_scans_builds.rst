.. _catalogs_scans_builds:

##################################
Catalogs, Scans And Family Builds
##################################

Requake keeps three levels of results in the output database (see
:doc:`database_schemas`):

- a *catalog*, read by ``requake read fdsn`` or ``requake read file``;
- a *catalog scan*, run by ``requake scan catalog`` on one catalog;
- a *family build*, run by ``requake build families`` on one scan.

Every level owns its rows, so several catalogs, several scans per
catalog and several family builds per scan can coexist in the same
``requake.sqlite`` file.  Each level is identified by an integer, and
the parameters that produced it are stored with it, so that two runs
can be compared afterwards.

When a command needs a catalog, a scan or a build and none is given, it
uses the most recent one and logs which one it picked:

.. code-block::

   INFO Using catalog 2 (label "2020 relocated", 1234 events)
   INFO Using scan 3 (label "band 2-8") on catalog 2
   INFO Using family build 5 (method UPGMA, 42 families) from scan 3

Pass ``--catalog-id``, ``--scan-id`` or ``--build-id`` to select a
different one.


Listing the stored results
--------------------------

Three commands list what is stored in the database:

``requake list catalogs``
   one row per catalog, with its label, creation time, number of
   events, number of scans and source.

``requake list scans``
   one row per scan, with the catalog it used, its status, the number
   of events and the number of stored and analyzed pairs.

``requake list builds``
   one row per family build, with the scan it used, the clustering
   method, ``cc_min`` and the number of families.

Each command also accepts an id as an optional argument, to show the
details of a single entry, including the full list of parameters used:

.. code-block::

   requake list scans 3


Reading Catalogs
----------------

``requake read fdsn`` and ``requake read file`` never replace an
existing catalog: every run writes a new catalog id.  If a catalog read
with the same parameters already exists, Requake only warns, so a scan
that used the previous catalog stays valid.  Use ``-l``/``--label`` to
give the new catalog a memorable name:

.. code-block::

   requake read file -l "2020 relocated" catalog.csv

Use ``-a``/``--append`` to add events to a catalog instead of creating
a new one; ``--catalog-id`` selects the catalog to extend (the latest
one by default).  Appending in place invalidates nothing, but existing
scans will not contain pairs for the added events: rerun
``scan catalog`` to include them.

Reading the same catalog again and again is safe but wastes space; use
``requake delete catalog`` to remove the copies you no longer need.


Scanning a catalog
------------------

``requake scan catalog`` scans the catalog selected with
``--catalog-id`` (the latest one by default) and always stores its
pairs under a new scan id.

When a scan with identical parameters already exists in the selected
catalog, Requake asks whether to replace it, continue it, or add a new
scan.  The same choices are available without a prompt:

``-f``/``--force``
   replace the existing scan with identical parameters.  The scan id is
   kept, and its pairs, trace metadata and family builds are removed.

``-r``/``--resume``
   resume the existing scan with identical parameters, skipping the
   pairs already stored.

``--scan-id``
   work on an explicit scan: continue it, or replace it when
   ``--force`` is also given.

Use ``-l``/``--label`` to name the scan, for example after the trace ID
or the frequency band it used.

Scans with different parameters are independent, so you can, for
example, compare the same catalog scanned on two different stations:

.. code-block::

   requake scan catalog --scan-id 1 -l "station A"
   requake scan catalog -t XX.STAB.00.HHZ -l "station B"
   requake list scans
   requake print pairs --scan-id 1
   requake print pairs --scan-id 2


Deleting Stored Results
-----------------------

One command removes the three kinds of entry:

.. code-block::

   requake delete catalog CATALOG_ID
   requake delete scan SCAN_ID
   requake delete build BUILD_ID

Deleting is cascading: a catalog takes its scans away with it, a scan
takes its pairs, trace metadata and family builds away, and a build
takes its families and template detections away.  Before touching
anything, Requake reports how many rows are involved and asks for
confirmation.

Two options make the command scriptable:

``-n``/``--dry-run``
   only report what would be deleted, without modifying the database.

``-f``/``--force``
   delete without asking for confirmation.

A dry run is the safe way to see the cost of a deletion:

.. code-block::

   requake delete catalog 1 --dry-run

.. note::

   Deleting a catalog does not delete the event lookup tables
   (``event_keys`` and ``trace_keys``): they are shared by all catalogs
   and scans, and are harmless once unreferenced.
