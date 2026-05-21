Database Schemas
----------------

Requake stores scan outputs in a SQLite database named ``requake.db`` inside
the selected output directory.

The database currently contains four domain tables:

- ``catalog``
- ``event_pairs``
- ``families``
- ``template_detections``

Schema Version
^^^^^^^^^^^^^^

The SQLite ``PRAGMA user_version`` field is used to track schema version.
The current version is ``1``.

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
     orig_time1      TEXT NOT NULL,
     lon1            REAL,
     lat1            REAL,
     depth_km1       REAL,
     mag_type1       TEXT,
     mag1            REAL,
     orig_time2      TEXT NOT NULL,
     lon2            REAL,
     lat2            REAL,
     depth_km2       REAL,
     mag_type2       TEXT,
     mag2            REAL,
     lag_samples     INTEGER,
     lag_sec         REAL,
     cc_max          REAL NOT NULL,
     UNIQUE (evid1, evid2, trace_id)
   )

Indexes:

- ``idx_pairs_evid1`` on ``event_pairs(evid1)``
- ``idx_pairs_evid2`` on ``event_pairs(evid2)``

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
