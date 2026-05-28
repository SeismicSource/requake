# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed event pair persistence.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import math
import sqlite3
from obspy import UTCDateTime
from .db import (
    DatabaseCorruptError,
    execute_with_retry,
    get_db_connection,
    get_db_path,
)
from .trace_metadata import (
    PairsMetadataError,  # noqa: F401 (re-exported for callers)
    TRACE_METADATA_TABLE,
    TRACE_METADATA_SCHEMA_STATEMENTS,
    _is_missing_trace_metadata_table_error,
    _store_trace_metadata,
)

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

EVENT_PAIRS_TABLE = 'event_pairs'
EVENT_KEYS_TABLE = 'event_keys'
TRACE_KEYS_TABLE = 'trace_keys'
MISSING_EVENT_PAIRS_TABLE = f'no such table: {EVENT_PAIRS_TABLE}'


class PairsTableNotFoundError(LookupError):
    """Raised when the event pairs table is missing from the database."""


class PairsSchemaError(RuntimeError):
    """Raised when stored pairs use an incompatible database schema."""


# Combined schema for event_pairs, lookup tables, and trace_metadata.
# Used by _ensure_pairs_table and the local migration helper.
PAIRS_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {EVENT_KEYS_TABLE} (
      event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
      evid            TEXT NOT NULL UNIQUE
    )
    ''',
    f'''
    CREATE TABLE IF NOT EXISTS {TRACE_KEYS_TABLE} (
      trace_key_id    INTEGER PRIMARY KEY AUTOINCREMENT,
      trace_id        TEXT NOT NULL UNIQUE
    )
    ''',
    f'''
    CREATE TABLE IF NOT EXISTS {EVENT_PAIRS_TABLE} (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      event1_id       INTEGER NOT NULL,
      event2_id       INTEGER NOT NULL,
      trace_key_id    INTEGER NOT NULL,
      lag_samples     INTEGER,
      cc_x100         INTEGER NOT NULL,
      FOREIGN KEY (event1_id)
        REFERENCES {EVENT_KEYS_TABLE}(event_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
      FOREIGN KEY (event2_id)
        REFERENCES {EVENT_KEYS_TABLE}(event_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
      FOREIGN KEY (trace_key_id)
        REFERENCES {TRACE_KEYS_TABLE}(trace_key_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
      UNIQUE (event1_id, event2_id, trace_key_id)
    )
    ''',
    *TRACE_METADATA_SCHEMA_STATEMENTS,
]


def _ensure_pairs_table(cursor):
    """Create pair and metadata tables when needed."""
    for statement in PAIRS_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _is_missing_pairs_table_error(err):
    """Return True when sqlite error means pairs table is missing."""
    return MISSING_EVENT_PAIRS_TABLE in str(err)


def _is_incompatible_pairs_schema_error(err):
    """Return True when sqlite error means pairs schema is outdated."""
    message = str(err)
    return (
        'no such column: p.cc_x100' in message
        or 'no such column: cc_x100' in message
        or 'no such column: p.event1_id' in message
        or 'no such column: p.event2_id' in message
        or 'no such column: p.trace_key_id' in message
        or 'has no column named event1_id' in message
        or 'has no column named event2_id' in message
        or 'has no column named trace_key_id' in message
        or f'no such table: {EVENT_KEYS_TABLE}' in message
        or f'no such table: {TRACE_KEYS_TABLE}' in message
        or _is_missing_trace_metadata_table_error(err)
    )


def _encode_cc_max(cc_max):
    """Encode cc_max with 0.01 precision for compact storage."""
    return int(round(cc_max * 100))


def _decode_cc_max(cc_x100):
    """Decode compact cc_max storage to float."""
    return cc_x100 / 100.0


def _cc_filter_clause(cc_min, cc_max):
    """Build SQL filter clause and params for encoded cc values."""
    conditions = []
    params = []
    if cc_min is not None:
        conditions.append('p.cc_x100 >= ?')
        params.append(int(math.ceil(cc_min * 100)))
    if cc_max is not None:
        conditions.append('p.cc_x100 <= ?')
        params.append(int(math.floor(cc_max * 100)))
    where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
    return where, params


def _lookup_id(
    cursor,
    table,
    id_column,
    value_column,
    value,
    cache,
):
    """Return integer key for a lookup-table value, creating row if needed."""
    cached = cache.get(value)
    if cached is not None:
        return cached
    execute_with_retry(
        lambda: cursor.execute(
            f'INSERT OR IGNORE INTO {table} ({value_column}) VALUES (?)',
            (value,),
        ),
        f'ensure lookup row in {table}',
    )
    row = cursor.execute(
        f'SELECT {id_column} AS lookup_id '
        f'FROM {table} '
        f'WHERE {value_column} = ?',
        (value,),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f'Failed to resolve lookup id in {table} for value {value}'
        )
    lookup_id = int(row['lookup_id'])
    cache[value] = lookup_id
    return lookup_id


def _pair_values(pair, cursor, event_cache, trace_cache):
    """Convert a RequakeEventPair into a compact row tuple."""
    event1_id = _lookup_id(
        cursor,
        EVENT_KEYS_TABLE,
        'event_id',
        'evid',
        pair.event1.evid,
        event_cache,
    )
    event2_id = _lookup_id(
        cursor,
        EVENT_KEYS_TABLE,
        'event_id',
        'evid',
        pair.event2.evid,
        event_cache,
    )
    trace_key_id = _lookup_id(
        cursor,
        TRACE_KEYS_TABLE,
        'trace_key_id',
        'trace_id',
        pair.trace_id,
        trace_cache,
    )
    return (
        event1_id,
        event2_id,
        trace_key_id,
        int(pair.lag_samples),
        _encode_cc_max(pair.cc_max),
    )


def _pair_from_row(row):
    """Build a RequakeEventPair from a SQLite row."""
    from ..catalog import RequakeEvent
    from ..families.pairs import RequakeEventPair

    event1 = RequakeEvent(
        evid=row['evid1'],
        orig_time=UTCDateTime(row['orig_time1']),
        lon=row['lon1'],
        lat=row['lat1'],
        depth=row['depth_km1'],
        mag_type=row['mag_type1'],
        mag=row['mag1'],
        trace_id=row['trace_id'],
    )
    event2 = RequakeEvent(
        evid=row['evid2'],
        orig_time=UTCDateTime(row['orig_time2']),
        lon=row['lon2'],
        lat=row['lat2'],
        depth=row['depth_km2'],
        mag_type=row['mag_type2'],
        mag=row['mag2'],
        trace_id=row['trace_id'],
    )
    # lag_sec is reconstructed at read time from lag_samples and the
    # sampling rate resolved at the first event time.
    return RequakeEventPair(
        event1,
        event2,
        row['trace_id'],
        row['lag_samples'],
        row['lag_samples'] / row['sampling_rate_hz'],
        _decode_cc_max(row['cc_x100']),
    )


def write_pairs(pairs, config, append=True):
    """Write event pairs into SQLite."""
    pairs = list(pairs)
    conn = get_db_connection(config, initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_pairs_table(cursor)
        if not append:
            execute_with_retry(
                lambda: cursor.execute(f'DELETE FROM {EVENT_PAIRS_TABLE}'),
                'clear event pairs table',
            )
            execute_with_retry(
                lambda: cursor.execute(f'DELETE FROM {EVENT_KEYS_TABLE}'),
                'clear event keys table',
            )
            execute_with_retry(
                lambda: cursor.execute(f'DELETE FROM {TRACE_KEYS_TABLE}'),
                'clear trace keys table',
            )
            execute_with_retry(
                lambda: cursor.execute(f'DELETE FROM {TRACE_METADATA_TABLE}'),
                'clear trace metadata table',
            )
        if pairs:
            _store_trace_metadata(cursor, pairs, config)
            event_cache = {}
            trace_cache = {}
            pair_rows = [
                _pair_values(
                    pair,
                    cursor,
                    event_cache,
                    trace_cache,
                )
                for pair in pairs
            ]
            execute_with_retry(
                lambda: cursor.executemany(
                    f'''
                    INSERT OR REPLACE INTO {EVENT_PAIRS_TABLE} (
                      event1_id,
                      event2_id,
                      trace_key_id,
                      lag_samples,
                      cc_x100
                    ) VALUES (?, ?, ?, ?, ?)
                    ''',
                    pair_rows,
                ),
                'write event pairs batch',
            )
        conn.commit()
    except sqlite3.OperationalError as err:
        if _is_incompatible_pairs_schema_error(err):
            raise PairsSchemaError(
                'Stored event pairs schema is incompatible with this '
                f'Requake version in db file {get_db_path(config)}'
            ) from err
        raise
    finally:
        conn.close()


def count_pairs(config):
    """Return the number of stored event pairs."""
    conn = get_db_connection(config, initdb=False)
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT COUNT(*) AS npairs FROM {EVENT_PAIRS_TABLE}'
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_pairs_table_error(err):
                return 0
            raise
    finally:
        conn.close()
    return int(row['npairs'])


def read_pair_keys(config):
    """Read stored event-pair keys as (evid1, evid2) tuples."""
    conn = get_db_connection(config, initdb=False)
    try:
        cursor = conn.cursor()
        try:
            rows = cursor.execute(
                f'''
                SELECT e1.evid AS evid1, e2.evid AS evid2
                FROM {EVENT_PAIRS_TABLE} AS p
                JOIN {EVENT_KEYS_TABLE} AS e1
                  ON e1.event_id = p.event1_id
                JOIN {EVENT_KEYS_TABLE} AS e2
                  ON e2.event_id = p.event2_id
                '''
            ).fetchall()
        except sqlite3.OperationalError as err:
            if _is_missing_pairs_table_error(err):
                return set()
            if _is_incompatible_pairs_schema_error(err):
                raise PairsSchemaError(
                    'Stored event pairs schema is incompatible with this '
                    f'Requake version in db file {get_db_path(config)}'
                ) from err
            raise
    finally:
        conn.close()
    return {(row['evid1'], row['evid2']) for row in rows}


def read_pairs(config, cc_min=None, cc_max=None):
    """
    Read event pairs from SQLite, optionally filtering by cc_max.

    :param config: Requake configuration object.
    :param cc_min: If given, only return pairs with cc_max >= cc_min.
    :type cc_min: float or None
    :param cc_max: If given, only return pairs with cc_max <= cc_max.
    :type cc_max: float or None
    :return: list of RequakeEventPair objects
    :rtype: list

    :raise PairsTableNotFoundError: if the stored pairs table is missing
    """
    where, params = _cc_filter_clause(cc_min, cc_max)
    conn = get_db_connection(config, initdb=False)
    try:
        cursor = conn.cursor()
        try:
            rows = cursor.execute(
                f'''
                SELECT
                  e1.evid AS evid1,
                  e2.evid AS evid2,
                  tk.trace_id AS trace_id,
                  p.lag_samples,
                  p.cc_x100,
                  c1.orig_time AS orig_time1,
                  c1.lon AS lon1,
                  c1.lat AS lat1,
                  c1.depth_km AS depth_km1,
                  c1.mag_type AS mag_type1,
                  c1.mag AS mag1,
                  c2.orig_time AS orig_time2,
                  c2.lon AS lon2,
                  c2.lat AS lat2,
                  c2.depth_km AS depth_km2,
                  c2.mag_type AS mag_type2,
                  c2.mag AS mag2,
                  tm.sampling_rate_hz
                FROM {EVENT_PAIRS_TABLE} AS p
                JOIN {EVENT_KEYS_TABLE} AS e1
                  ON e1.event_id = p.event1_id
                JOIN {EVENT_KEYS_TABLE} AS e2
                  ON e2.event_id = p.event2_id
                JOIN {TRACE_KEYS_TABLE} AS tk
                  ON tk.trace_key_id = p.trace_key_id
                JOIN catalog AS c1 ON c1.evid = e1.evid
                JOIN catalog AS c2 ON c2.evid = e2.evid
                LEFT JOIN {TRACE_METADATA_TABLE} AS tm
                  ON tm.trace_id = tk.trace_id
                 AND tm.valid_from_utc <= c1.orig_time
                 AND (
                   tm.valid_to_utc IS NULL OR c1.orig_time < tm.valid_to_utc
                 )
                {where}
                ORDER BY c1.orig_time, c2.orig_time,
                         e1.evid, e2.evid, tk.trace_id
                ''',
                params,
            ).fetchall()
            if any(row['sampling_rate_hz'] is None for row in rows):
                raise PairsMetadataError(
                    'Trace metadata is missing for one or more stored pairs '
                    f'in db file {get_db_path(config)}'
                )
        except sqlite3.OperationalError as err:
            if _is_missing_pairs_table_error(err):
                raise PairsTableNotFoundError(
                    'Event pairs table not found in db file '
                    f'{get_db_path(config)}'
                ) from err
            if _is_incompatible_pairs_schema_error(err):
                raise PairsSchemaError(
                    'Stored event pairs schema is incompatible with this '
                    f'Requake version in db file {get_db_path(config)}'
                ) from err
            raise
        except sqlite3.DatabaseError as err:
            if 'database disk image is malformed' in str(err).lower():
                raise DatabaseCorruptError(
                    'The event pairs database is corrupted or malformed: '
                    f'{get_db_path(config)}\n'
                    'You can try recovering it with:\n'
                    "sqlite3 requake.sqlite '.recover' | "
                    'sqlite3 requake_new.sqlite'
                ) from err
            raise
    finally:
        conn.close()
    return [_pair_from_row(row) for row in rows]
