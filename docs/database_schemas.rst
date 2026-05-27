Database Schemas
----------------

Requake stores scan outputs in a SQLite database named ``requake.sqlite``
inside
the selected output directory.

The database currently contains five domain tables:

- ``catalog``
- ``event_pairs``
- ``trace_metadata``
- ``families``
- ``template_detections``

Schema Version
^^^^^^^^^^^^^^

The SQLite ``PRAGMA user_version`` field is used to track schema version.
The current version is ``1``.

Connection and Concurrency Settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

At connection startup, Requake applies SQLite pragmas to improve integrity and
concurrency:

- ``PRAGMA foreign_keys = ON``
- ``PRAGMA busy_timeout = 30000``
- ``PRAGMA journal_mode = WAL``

Write operations also use a bounded retry policy for transient lock errors
(``SQLITE_BUSY`` and ``SQLITE_LOCKED`` style conditions), with exponential
backoff and jitter.

Catalog Table
^^^^^^^^^^^^^

The ``catalog`` table stores the events read by ``requake read_catalog``.

.. code-block:: sql

   CREATE TABLE catalog (
     evid            TEXT PRIMARY KEY,
     orig_time       TEXT NOT NULL,
     lat             REAL,
     lon             REAL,
     depth_km        REAL,
     mag_type        TEXT,
     mag             REAL,
     mag_author      TEXT,
     author          TEXT,
     catalog         TEXT,
     contributor     TEXT,
     contributor_id  TEXT,
     location_name   TEXT,
     trace_id        TEXT
   )

Event Pairs Table
^^^^^^^^^^^^^^^^^

The ``event_pairs`` table stores cross-correlation results from
``requake scan_catalog``.

.. code-block:: sql

   CREATE TABLE event_pairs (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     evid1           TEXT NOT NULL,
     evid2           TEXT NOT NULL,
     trace_id        TEXT NOT NULL,
     lag_samples     INTEGER,
     cc_x100         INTEGER NOT NULL,
     FOREIGN KEY (evid1)
       REFERENCES catalog(evid)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     FOREIGN KEY (evid2)
       REFERENCES catalog(evid)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     UNIQUE (evid1, evid2, trace_id)
   )

Indexes:

- ``idx_pairs_evid1`` on ``event_pairs(evid1)``
- ``idx_pairs_evid2`` on ``event_pairs(evid2)``

``cc_x100`` stores ``cc_max`` with 0.01 precision using
``round(cc_max * 100)``.

The lag value in seconds is computed at run time using
``lag_samples / sampling_rate_hz`` from ``trace_metadata``.

Trace Metadata Table
^^^^^^^^^^^^^^^^^^^^

The ``trace_metadata`` table stores sampling-rate and coordinates with
time-valid intervals for each ``trace_id``.

.. code-block:: sql

   CREATE TABLE trace_metadata (
     trace_id          TEXT NOT NULL,
     valid_from_utc    TEXT NOT NULL,
     valid_to_utc      TEXT,
     sampling_rate_hz  REAL NOT NULL,
     trace_lon         REAL,
     trace_lat         REAL,
     updated_at        TEXT,
     PRIMARY KEY (trace_id, valid_from_utc)
   )

Index:

- ``idx_trace_metadata_lookup`` on
  ``trace_metadata(trace_id, valid_from_utc, valid_to_utc)``

Families Table
^^^^^^^^^^^^^^

The ``families`` table stores event-family assignments from
``requake build_families``.

.. code-block:: sql

   CREATE TABLE families (
     evid            TEXT NOT NULL,
     trace_id        TEXT NOT NULL,
     orig_time       TEXT NOT NULL,
     lon             REAL,
     lat             REAL,
     depth_km        REAL,
     mag_type        TEXT,
     mag             REAL,
     family_number   INTEGER NOT NULL,
     valid           INTEGER NOT NULL DEFAULT 1,
     FOREIGN KEY (evid)
       REFERENCES catalog(evid)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     PRIMARY KEY (evid, trace_id, family_number)
   )

Index:

- ``idx_families_number`` on ``families(family_number)``

Template Detections Table
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``template_detections`` table stores detections from
``requake scan_templates``.

.. code-block:: sql

   CREATE TABLE template_detections (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     family_number   INTEGER NOT NULL,
     trace_id        TEXT NOT NULL,
     evid            TEXT NOT NULL,
     orig_time       TEXT NOT NULL,
     lon             REAL,
     lat             REAL,
     depth_km        REAL,
     cc_max          REAL,
     UNIQUE (family_number, trace_id, evid)
   )

Indexes:

- ``idx_template_detections_family`` on ``template_detections(family_number)``
- ``idx_template_detections_trace`` on ``template_detections(trace_id)``
