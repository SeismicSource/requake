# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed catalog persistence.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sqlite3
from obspy import UTCDateTime
from .db import execute_with_retry, get_db_connection, get_db_path

CATALOG_TABLE = 'catalog'
MISSING_CATALOG_TABLE = f'no such table: {CATALOG_TABLE}'
# Conservative bound on the number of SQL variables per statement.
_MAX_SQL_VARIABLES = 900

CATALOG_SCHEMA_STATEMENTS = [
    (
        f'CREATE TABLE IF NOT EXISTS {CATALOG_TABLE} (\n'
        '  evid            TEXT PRIMARY KEY,\n'
        '  orig_time       TEXT NOT NULL,\n'
        '  lat             REAL,\n'
        '  lon             REAL,\n'
        '  depth_km        REAL,\n'
        '  mag_type        TEXT,\n'
        '  mag             REAL,\n'
        '  mag_author      TEXT,\n'
        '  author          TEXT,\n'
        '  catalog         TEXT,\n'
        '  contributor     TEXT,\n'
        '  contributor_id  TEXT,\n'
        '  location_name   TEXT,\n'
        '  trace_id        TEXT,\n'
        '  duplicate       INTEGER NOT NULL DEFAULT 0\n'
        ')'
    ),
]


def _ensure_catalog_table(cursor):
    """Create the catalog table when needed."""
    for statement in CATALOG_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _check_catalog_schema(cursor, db_path=None):
    """Ensure the stored catalog table has the expected columns."""
    columns = {
        row[1]
        for row in cursor.execute(f'PRAGMA table_info({CATALOG_TABLE})')
    }
    if 'duplicate' not in columns:
        raise RuntimeError(
            'Stored catalog schema is outdated: missing "duplicate" column '
            f'in db file {get_db_path(db_path=db_path)}. '
            'Please remove the database file and re-run the catalog '
            'pipeline.'
        )


def _event_row(event):
    """Convert a RequakeEvent into a database row tuple."""
    return (
        event.evid,
        str(event.orig_time),
        event.lat,
        event.lon,
        event.depth,
        event.mag_type,
        event.mag,
        event.mag_author,
        event.author,
        event.catalog,
        event.contributor,
        event.contributor_id,
        event.location_name,
        event.trace_id,
        int(bool(getattr(event, 'duplicate', False))),
    )


def _event_from_row(row):
    """Build a RequakeEvent from a SQLite row."""
    from ..catalog.catalog import RequakeEvent

    return RequakeEvent(
        evid=row['evid'],
        orig_time=UTCDateTime(row['orig_time']),
        lon=row['lon'],
        lat=row['lat'],
        depth=row['depth_km'],
        mag_type=row['mag_type'],
        mag=row['mag'],
        author=row['author'],
        catalog=row['catalog'],
        contributor=row['contributor'],
        contributor_id=row['contributor_id'],
        mag_author=row['mag_author'],
        location_name=row['location_name'],
        trace_id=row['trace_id'],
        duplicate=bool(row['duplicate']),
    )


def write_catalog(catalog, db_path=None):
    """Write the stored catalog into SQLite."""
    conn = get_db_connection(initdb=True, db_path=db_path)
    try:
        cursor = conn.cursor()
        _ensure_catalog_table(cursor)
        _check_catalog_schema(cursor)
        execute_with_retry(
            lambda: cursor.execute(f'DELETE FROM {CATALOG_TABLE}'),
            'clear catalog table',
        )
        execute_with_retry(
            lambda: cursor.executemany(
                f'''INSERT INTO {CATALOG_TABLE} (
                evid, orig_time, lat, lon, depth_km, mag_type, mag,
                mag_author, author, catalog, contributor, contributor_id,
                location_name, trace_id, duplicate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (_event_row(event) for event in catalog),
            ),
            'write catalog rows',
        )
        conn.commit()
    finally:
        conn.close()


def read_catalog(db_path=None):
    """Read the stored catalog from SQLite."""
    from ..catalog.catalog import RequakeCatalog

    conn = get_db_connection(initdb=False, db_path=db_path)
    try:
        rows = conn.execute(
            f'SELECT * FROM {CATALOG_TABLE} ORDER BY orig_time'
        ).fetchall()
        _check_catalog_schema(conn.cursor(), db_path=db_path)
    except sqlite3.OperationalError as err:
        if MISSING_CATALOG_TABLE in str(err):
            raise FileNotFoundError(
                'Catalog not found in db file '
                f'{get_db_path(db_path=db_path)}'
            ) from err
        raise
    finally:
        conn.close()
    catalog = RequakeCatalog()
    catalog.extend(_event_from_row(row) for row in rows)
    catalog.deduplicate()
    return catalog


def update_events_duplicate(evids, duplicate=True, db_path=None):
    """
    Set the duplicate flag for the given event IDs.

    :param evids: event IDs to update
    :type evids: iterable of str
    :param duplicate: value for the duplicate flag
    :type duplicate: bool
    :param db_path: path to the database file
    :type db_path: str or None
    :return: number of catalog rows actually changed
    :rtype: int
    """
    evids = list(evids)
    if not evids:
        return 0
    conn = get_db_connection(initdb=False, db_path=db_path)
    changed = 0
    try:
        cursor = conn.cursor()
        _check_catalog_schema(cursor, db_path=db_path)
        for start in range(0, len(evids), _MAX_SQL_VARIABLES):
            chunk = evids[start:start + _MAX_SQL_VARIABLES]
            placeholders = ','.join('?' * len(chunk))
            execute_with_retry(
                lambda: cursor.execute(
                    f'UPDATE {CATALOG_TABLE} '
                    f'SET duplicate = ? '
                    f'WHERE evid IN ({placeholders}) AND duplicate != ?',
                    (int(duplicate), *chunk, int(duplicate)),
                ),
                'update event duplicate flag',
            )
            changed += cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return changed
