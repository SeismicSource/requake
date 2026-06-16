.. _read_catalog:

##################
Reading a Catalog
##################

The command ``requake read_catalog`` imports an earthquake catalog into
Requake's output database, ready for scanning.  It can fetch events from
an FDSN event web service or read them from a local file.


Sources
-------

FDSN web service
^^^^^^^^^^^^^^^^

If no file is given on the command line:

.. code-block::

   requake read_catalog

Requake downloads the catalog from the FDSN event service configured in
the :doc:`configuration file <configuration_file>` (``catalog_fdsn_event_url``
and, optionally, up to three additional URLs for different time intervals).
The selection is narrowed by the geographic, depth, magnitude, and time
filters defined in the same configuration file.

Local file
^^^^^^^^^^

A local catalog file can be provided directly:

.. code-block::

   requake read_catalog CATALOG_FILE

Requake auto-detects the format from the file content, supporting:

* **QuakeML** — the standard XML-based seismological catalog format.
* **FDSN text** — the plain-text format returned by FDSN event web
  services (one line per event, ``#`` for comments).
* **CSV** — comma-separated values.  Requake guesses column names
  automatically by matching the CSV header against common field names
  (e.g., ``time``, ``lat``, ``lon``, ``depth``, ``magnitude``) and
  their common variants (``origin_time``, ``latitude``, ``depth_km``,
  ``mag``, etc.).  If no event ID column is present, Requake generates
  one automatically from the origin time, in the form ``reqk`` + year +
  six-letter suffix (e.g., ``reqk2023ltrqbk``).

.. note::

   If Requake cannot parse your CSV file — for example because the
   columns are in an unexpected format or contain mixed data types —
   don't despair!  I also wrote
   `SeisCat <https://seiscat.readthedocs.io>`_, a friendly companion
   tool for reading, filtering, plotting, and exporting earthquake
   catalogs.  You can use it to inspect your catalog visually, clean it
   up, and export a tidy CSV that Requake will happily digest.  I warmly
   encourage you to give it a try 😊.

When reading from a local file, the catalog is still filtered using the
geographic, depth, magnitude, and time criteria from the configuration
file.  To bypass filtering, set the relevant bounds wide enough to
include all events.


Filtering and deduplication
---------------------------

Regardless of the source, the catalog is filtered using the following
configuration parameters:

* ``catalog_start_time`` / ``catalog_end_time`` (+ optional intervals 1–3)
* ``catalog_lat_min`` / ``catalog_lat_max``
* ``catalog_lon_min`` / ``catalog_lon_max``
* ``catalog_depth_min`` / ``catalog_depth_max``
* ``catalog_mag_min`` / ``catalog_mag_max``

Duplicate events (same event ID) are automatically removed, and the
catalog is sorted by origin time before being written to the database.


Appending to an existing catalog
--------------------------------

Use ``--append`` to add new events to an already stored catalog:

.. code-block::

   requake read_catalog --append

Existing events are kept; only new events (by event ID) are added.


Output
------

The catalog is stored in the ``catalog`` table of the
:doc:`output database <database_schemas>`.  Once the catalog is ready,
proceed with the :doc:`catalog scan <scan_catalog>`.


Minimal catalog: origin times only
----------------------------------

Requake can work with a minimal catalog containing nothing but origin
times — no location, magnitude, or even event ID is strictly required.

If an event has no latitude or longitude, it is placed at the same
location as the configured station (``catalog_trace_id``) during the
:doc:`catalog scan <scan_catalog>`.  This is
useful for analysing lists of unlocated events, such as template-matching
detections or manually picked arrival times.
