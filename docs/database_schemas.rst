Database Schemas
----------------

Requake stores scan outputs in a SQLite database named ``requake.sqlite`` in
the selected output directory.  A separate ``waveform_cache.sqlite`` file in
the same directory holds the persistent waveform cache.

The main database contains ten tables, organized in three levels:
read catalogs, catalog scans, and family builds.

- ``catalogs``: one row per catalog read
- ``catalog``: event rows, scoped by ``catalog_id``
- ``scans``: one row per catalog scan
- ``event_keys``
- ``trace_keys``
- ``event_pairs``: scoped by ``scan_id``
- ``trace_metadata``: scoped by ``scan_id``
- ``family_builds``: one row per family build
- ``families``: scoped by ``build_id``
- ``template_detections``: scoped by ``build_id``

Each level owns its rows, so several catalogs, several scans per
catalog and several family builds per scan can coexist in the same
database file.  See :doc:`catalogs_scans_builds` for the commands that
list, select and delete them.

Schema Version
^^^^^^^^^^^^^^

The SQLite ``PRAGMA user_version`` field is used to track schema version.
The current version is ``1``.

.. warning::

   The database layout changed during the 0.8.x development series
   without a version bump: the version number alone cannot tell an old
   database from a new one.  A database written by an earlier release
   must be migrated, or recreated from scratch.  Requake reports an
   explicit error when it detects the old layout.

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

Catalogs Table
^^^^^^^^^^^^^^

The ``catalogs`` table registers every catalog read by
``requake read catalog``.  Reading a catalog always creates a new row,
so an existing catalog is never replaced.

.. code-block:: sql

   CREATE TABLE catalogs (
     catalog_id      INTEGER PRIMARY KEY AUTOINCREMENT,
     label           TEXT,
     created_at      TEXT NOT NULL,
     source          TEXT,
     params_hash     TEXT NOT NULL,
     params_json     TEXT NOT NULL,
     requake_version TEXT,
     nevents         INTEGER
   )

``params_hash`` identifies the catalog selection parameters; it is used
to warn when the same catalog is read twice.  ``params_json`` stores
the full parameter snapshot.

Catalog Table
^^^^^^^^^^^^^

The ``catalog`` table stores the events of every catalog read by
``requake read catalog``.

.. code-block:: sql

   CREATE TABLE catalog (
     catalog_id      INTEGER NOT NULL,
     evid            TEXT NOT NULL,
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
     trace_id        TEXT,
     duplicate       INTEGER NOT NULL DEFAULT 0,
     PRIMARY KEY (catalog_id, evid),
     FOREIGN KEY (catalog_id)
       REFERENCES catalogs(catalog_id)
       ON UPDATE CASCADE ON DELETE CASCADE
   )

Index:

- ``idx_catalog_orig_time`` on ``catalog(catalog_id, orig_time)``

The ``duplicate`` column is set to ``1`` by ``requake flag duplicates``
for events that are considered duplicates of another catalog event,
within the catalog of the selected scan.

Scans Table
^^^^^^^^^^^

The ``scans`` table registers every execution of
``requake scan catalog``, with the parameters it used.

.. code-block:: sql

   CREATE TABLE scans (
     scan_id          INTEGER PRIMARY KEY AUTOINCREMENT,
     catalog_id       INTEGER NOT NULL,
     label            TEXT,
     created_at       TEXT NOT NULL,
     finished_at      TEXT,
     status           TEXT NOT NULL DEFAULT 'running',
     params_hash      TEXT NOT NULL,
     params_json      TEXT NOT NULL,
     requake_version  TEXT,
     nevents          INTEGER,
     npairs_stored    INTEGER,
     npairs_analyzed  INTEGER,
     FOREIGN KEY (catalog_id)
       REFERENCES catalogs(catalog_id)
       ON UPDATE CASCADE ON DELETE CASCADE
   )

Index:

- ``idx_scans_catalog`` on ``scans(catalog_id)``

``status`` is ``running`` while the scan is in progress, then
``complete`` or ``failed``.  A scan that is still ``running`` can be
resumed with ``requake scan catalog --resume``.

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
``requake scan catalog`` and is optimized for storage efficiency:

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
     scan_id         INTEGER NOT NULL,
     event1_id       INTEGER NOT NULL,
     event2_id       INTEGER NOT NULL,
     trace_key_id    INTEGER NOT NULL,
     lag_samples     INTEGER,
     cc_x100         INTEGER,
     invalid         INTEGER NOT NULL DEFAULT 0,
     FOREIGN KEY (scan_id)
       REFERENCES scans(scan_id)
       ON UPDATE CASCADE ON DELETE CASCADE,
     FOREIGN KEY (event1_id)
       REFERENCES event_keys(event_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     FOREIGN KEY (event2_id)
       REFERENCES event_keys(event_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     FOREIGN KEY (trace_key_id)
       REFERENCES trace_keys(trace_key_id)
       ON UPDATE CASCADE ON DELETE RESTRICT,
     UNIQUE (scan_id, event1_id, event2_id, trace_key_id)
   )

``cc_x100`` stores ``cc_max`` with 0.01 precision using
``round(cc_max * 100)``.

The ``invalid`` column is set to ``1`` by ``requake flag duplicates``
for all the pairs involving a duplicated event.  Invalid pairs are
ignored when families are built and when pairs are printed.

Trace Metadata Table
^^^^^^^^^^^^^^^^^^^^

The ``trace_metadata`` table stores sampling rate, coordinates, and
elevation/depth using time-valid intervals per ``trace_id``.  Rows
belong to the scan that stored them.

.. code-block:: sql

   CREATE TABLE trace_metadata (
     scan_id           INTEGER NOT NULL,
     trace_id          TEXT NOT NULL,
     valid_from_utc    TEXT NOT NULL,
     valid_to_utc      TEXT,
     sampling_rate_hz  REAL NOT NULL,
     trace_lon         REAL,
     trace_lat         REAL,
     elevation         REAL,
     local_depth       REAL,
     updated_at        TEXT,
     PRIMARY KEY (scan_id, trace_id, valid_from_utc),
     FOREIGN KEY (scan_id)
       REFERENCES scans(scan_id)
       ON UPDATE CASCADE ON DELETE CASCADE
   )

Index:

- ``idx_trace_metadata_lookup`` on
  ``trace_metadata(scan_id, trace_id, valid_from_utc, valid_to_utc)``

Family Builds Table
^^^^^^^^^^^^^^^^^^^

The ``family_builds`` table registers every execution of
``requake build families``, together with the scan used as input and
the clustering method.

.. code-block:: sql

   CREATE TABLE family_builds (
     build_id         INTEGER PRIMARY KEY AUTOINCREMENT,
     scan_id          INTEGER NOT NULL,
     label            TEXT,
     created_at       TEXT NOT NULL,
     finished_at      TEXT,
     status           TEXT NOT NULL DEFAULT 'running',
     method           TEXT NOT NULL,
     cc_min           REAL,
     params_hash      TEXT NOT NULL,
     params_json      TEXT NOT NULL,
     requake_version  TEXT,
     nfamilies        INTEGER,
     nevents          INTEGER,
     FOREIGN KEY (scan_id)
       REFERENCES scans(scan_id)
       ON UPDATE CASCADE ON DELETE CASCADE
   )

Index:

- ``idx_family_builds_scan`` on ``family_builds(scan_id)``

``method`` stores the ``clustering_algorithm`` value (``shared`` or
``UPGMA``): the same pair set can produce several builds with
different methods and thresholds.

Families Table
^^^^^^^^^^^^^^

The ``families`` table stores event-family assignments produced by
``requake build families``.

.. code-block:: sql

   CREATE TABLE families (
     build_id        INTEGER NOT NULL,
     catalog_id      INTEGER NOT NULL,
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
     FOREIGN KEY (build_id)
       REFERENCES family_builds(build_id)
       ON UPDATE CASCADE ON DELETE CASCADE,
     FOREIGN KEY (catalog_id, evid)
       REFERENCES catalog(catalog_id, evid)
       ON UPDATE CASCADE ON DELETE CASCADE,
     PRIMARY KEY (build_id, family_number, evid, trace_id)
   )

Index:

- ``idx_families_number`` on ``families(build_id, family_number)``

``family_number`` is meaningful only within its build: the same pair
set clustered with a different method produces a different numbering.

Template Detections Table
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``template_detections`` table stores detections produced by
``requake scan templates``, for the family build used as reference.

.. code-block:: sql

   CREATE TABLE template_detections (
     id              INTEGER PRIMARY KEY AUTOINCREMENT,
     build_id        INTEGER NOT NULL,
     family_number   INTEGER NOT NULL,
     trace_id        TEXT NOT NULL,
     evid            TEXT NOT NULL,
     orig_time       TEXT NOT NULL,
     lon             REAL,
     lat             REAL,
     depth_km        REAL,
     cc_max          REAL,
     FOREIGN KEY (build_id)
       REFERENCES family_builds(build_id)
       ON UPDATE CASCADE ON DELETE CASCADE,
     UNIQUE (build_id, family_number, trace_id, evid)
   )

Indexes:

- ``idx_template_detections_family`` on
  ``template_detections(build_id, family_number)``
- ``idx_template_detections_trace`` on
  ``template_detections(build_id, trace_id)``

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
  ``wfcache prefetch`` and consumed by ``scan catalog`` to produce
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
