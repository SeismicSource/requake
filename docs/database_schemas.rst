Database Schemas
----------------

Requake stores scan outputs in a SQLite database named ``requake.sqlite`` in
the selected output directory.

The database currently contains seven domain tables:

- ``catalog``
- ``event_keys``
- ``trace_keys``
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

The ``catalog`` table stores events read by ``requake read_catalog``.

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

Event Keys Table
^^^^^^^^^^^^^^^^

The ``event_keys`` table maps event IDs to integer keys.

.. code-block:: sql

   CREATE TABLE event_keys (
     event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
     evid            TEXT NOT NULL UNIQUE
   )

Trace Keys Table
^^^^^^^^^^^^^^^^

The ``trace_keys`` table maps trace IDs to integer keys.

.. code-block:: sql

   CREATE TABLE trace_keys (
     trace_key_id    INTEGER PRIMARY KEY AUTOINCREMENT,
     trace_id        TEXT NOT NULL UNIQUE
   )

Event Pairs Table
^^^^^^^^^^^^^^^^^

The ``event_pairs`` table stores cross-correlation results from
``requake scan_catalog`` and is optimized for storage efficiency:

- repeated text identifiers are replaced by integer lookup keys;
- cross-correlation is encoded as ``cc_x100``;
- lag is stored as ``lag_samples``.

Lag in seconds is reconstructed at read time from ``lag_samples`` and
``trace_metadata.sampling_rate_hz``.

.. code-block:: sql

   CREATE TABLE event_pairs (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     event1_id       INTEGER NOT NULL,
     event2_id       INTEGER NOT NULL,
     trace_key_id    INTEGER NOT NULL,
     lag_samples     INTEGER,
     cc_x100         INTEGER NOT NULL,
     FOREIGN KEY (event1_id)
       REFERENCES event_keys(event_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     FOREIGN KEY (event2_id)
       REFERENCES event_keys(event_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     FOREIGN KEY (trace_key_id)
       REFERENCES trace_keys(trace_key_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     UNIQUE (event1_id, event2_id, trace_key_id)
   )

``cc_x100`` stores ``cc_max`` with 0.01 precision using
``round(cc_max * 100)``.

Trace Metadata Table
^^^^^^^^^^^^^^^^^^^^

The ``trace_metadata`` table stores sampling rate and coordinates using
time-valid intervals per ``trace_id``.

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

The ``families`` table stores event-family assignments produced by
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

The ``template_detections`` table stores detections produced by
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
