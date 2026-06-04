Database Schemas
----------------

Requake stores scan outputs in a SQLite database named ``requake.sqlite`` in
the selected output directory.  A separate ``waveform_cache.sqlite`` file in
the same directory holds the persistent waveform cache.

The main database currently contains seven domain tables:

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

Pairs that cannot be analyzed (for example due to missing waveforms) are
still stored for resume logic, with ``lag_samples`` and ``cc_x100`` set to
``NULL``.

Lag in seconds is reconstructed at read time from ``lag_samples`` and
``trace_metadata.sampling_rate_hz``.

.. code-block:: sql

   CREATE TABLE event_pairs (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     event1_id       INTEGER NOT NULL,
     event2_id       INTEGER NOT NULL,
     trace_key_id    INTEGER NOT NULL,
     lag_samples     INTEGER,
     cc_x100         INTEGER,
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

The ``trace_metadata`` table stores sampling rate, coordinates, and
elevation/depth using time-valid intervals per ``trace_id``.

.. code-block:: sql

   CREATE TABLE trace_metadata (
     trace_id          TEXT NOT NULL,
     valid_from_utc    TEXT NOT NULL,
     valid_to_utc      TEXT,
     sampling_rate_hz  REAL NOT NULL,
     trace_lon         REAL,
     trace_lat         REAL,
     elevation         REAL,
     local_depth       REAL,
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

Waveform Cache Database
^^^^^^^^^^^^^^^^^^^^^^^

The waveform cache is stored in a separate SQLite file,
``waveform_cache.sqlite``, located in the output directory.  It contains
prefetched waveform windows and a persistent record of download failures.

The file uses its own ``PRAGMA user_version`` (currently ``1``) and the
same WAL / ``busy_timeout`` settings as the main database.

cache_meta Table
~~~~~~~~~~~~~~~~

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS cache_meta (
       key TEXT PRIMARY KEY,
       value TEXT NOT NULL
   )

Key-value metadata.  Currently stores:

- ``schema_version`` — cache schema version.
- ``tp_min_{trace_id}``, ``tp_max_{trace_id}`` — standardized waveform
  window offsets (in seconds) for a given trace ID.  Written by
  ``wfcache prefetch`` and consumed by ``scan_catalog`` to produce
  identical cache keys across independent processes.

waveform_cache Table
~~~~~~~~~~~~~~~~~~~~

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS waveform_cache (
       evid TEXT NOT NULL,
       trace_id TEXT NOT NULL,
       start_time_ns INTEGER NOT NULL,
       end_time_ns INTEGER NOT NULL,
       sampling_rate REAL NOT NULL,
       npts INTEGER NOT NULL,
       data_blob BLOB NOT NULL,
       created_at_ns INTEGER NOT NULL,
       accessed_at_ns INTEGER NOT NULL,
       PRIMARY KEY (evid, trace_id, start_time_ns, end_time_ns)
   )

One row per cached waveform window.  ``data_blob`` stores the waveform as
MiniSEED bytes with STEIM2 integer encoding.  ``start_time_ns`` and
``end_time_ns`` use UTC epoch nanoseconds.

Indexes:

- ``idx_waveform_cache_trace_time`` on
  ``waveform_cache(trace_id, start_time_ns, end_time_ns)``

waveform_failures Table
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS waveform_failures (
       evid TEXT NOT NULL,
       trace_id TEXT NOT NULL,
       start_time_ns INTEGER NOT NULL,
       end_time_ns INTEGER NOT NULL,
       retry_count INTEGER NOT NULL,
       max_retries INTEGER NOT NULL,
       last_error TEXT,
       first_failure_ns INTEGER NOT NULL,
       last_failure_ns INTEGER NOT NULL,
       next_retry_after_ns INTEGER,
       PRIMARY KEY (evid, trace_id, start_time_ns, end_time_ns)
   )

Persistent negative cache.  When a waveform download fails, a row is
inserted (or updated via ``ON CONFLICT`` upsert) with an incremented
``retry_count`` and an exponentially-growing ``next_retry_after_ns``
backoff.  Once ``retry_count >= max_retries`` the download is considered
exhausted and skipped by all subsequent runs until the failure is manually
reset via ``wfcache reset-failures``.
