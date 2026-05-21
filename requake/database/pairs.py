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
import sqlite3
from obspy import UTCDateTime
from .db import execute_with_retry, get_db_connection, get_db_path

EVENT_PAIRS_TABLE = 'event_pairs'
MISSING_EVENT_PAIRS_TABLE = f'no such table: {EVENT_PAIRS_TABLE}'

PAIRS_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {EVENT_PAIRS_TABLE} (
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
            FOREIGN KEY (evid1)
                REFERENCES catalog(evid)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (evid2)
                REFERENCES catalog(evid)
                ON UPDATE CASCADE ON DELETE RESTRICT,
      UNIQUE (evid1, evid2, trace_id)
    )
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_pairs_evid1 '
        f'ON {EVENT_PAIRS_TABLE}(evid1)'
    ),
    (
        'CREATE INDEX IF NOT EXISTS idx_pairs_evid2 '
        f'ON {EVENT_PAIRS_TABLE}(evid2)'
    ),
]


def _ensure_pairs_table(cursor):
    """Create the event pair table and indexes when needed."""
    for statement in PAIRS_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _pair_values(pair):
    """Convert a RequakeEventPair into a row tuple."""
    return (
        pair.event1.evid,
        pair.event2.evid,
        pair.trace_id,
        str(pair.event1.orig_time),
        pair.event1.lon,
        pair.event1.lat,
        pair.event1.depth,
        pair.event1.mag_type,
        pair.event1.mag,
        str(pair.event2.orig_time),
        pair.event2.lon,
        pair.event2.lat,
        pair.event2.depth,
        pair.event2.mag_type,
        pair.event2.mag,
        int(pair.lag_samples),
        pair.lag_sec,
        pair.cc_max,
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
    return RequakeEventPair(
        event1,
        event2,
        row['trace_id'],
        row['lag_samples'],
        row['lag_sec'],
        row['cc_max'],
    )


def write_pairs(pairs, config, append=True):
    """Write event pairs into SQLite."""
    conn = get_db_connection(config, initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_pairs_table(cursor)
        if not append:
            execute_with_retry(
                lambda: cursor.execute(f'DELETE FROM {EVENT_PAIRS_TABLE}'),
                'clear event pairs table',
            )
        if pairs:
            execute_with_retry(
                lambda: cursor.executemany(
                    f'''
                    INSERT OR REPLACE INTO {EVENT_PAIRS_TABLE} (
                      evid1, evid2, trace_id, orig_time1, lon1, lat1,
                      depth_km1, mag_type1, mag1, orig_time2, lon2, lat2,
                      depth_km2, mag_type2, mag2, lag_samples, lag_sec, cc_max
                                        ) VALUES (
                                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                            ?, ?, ?, ?, ?, ?
                                        )
                    ''',
                    (_pair_values(pair) for pair in pairs),
                ),
                'write event pairs batch',
            )
        conn.commit()
    finally:
        conn.close()


def read_pairs(config):
    """Read event pairs from SQLite."""
    conn = get_db_connection(config, initdb=False)
    try:
        cursor = conn.cursor()
        try:
            rows = cursor.execute(
                f'''
                SELECT * FROM {EVENT_PAIRS_TABLE}
                ORDER BY orig_time1, orig_time2, evid1, evid2, trace_id
                '''
            ).fetchall()
        except sqlite3.OperationalError as err:
            if MISSING_EVENT_PAIRS_TABLE in str(err):
                raise FileNotFoundError(
                    'Event pairs not found in db file '
                    f'{get_db_path(config)}'
                ) from err
            raise
    finally:
        conn.close()
    return [_pair_from_row(row) for row in rows]
