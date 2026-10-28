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
from .catalogs import (
    CATALOGS_SCHEMA_STATEMENTS,
    resolve_catalog_id,
)
from .db import execute_with_retry, get_db_connection, get_db_path

CATALOG_TABLE = 'catalog'
MISSING_CATALOG_TABLE = f'no such table: {CATALOG_TABLE}'
# Conservative bound on the number of SQL variables per statement.
_MAX_SQL_VARIABLES = 900


class CatalogSchemaError(RuntimeError):
    """Raised when the stored catalog uses an incompatible schema."""


CATALOG_SCHEMA_STATEMENTS = [
    *CATALOGS_SCHEMA_STATEMENTS,
    (
        f'CREATE TABLE IF NOT EXISTS {CATALOG_TABLE} (\n'
        '  catalog_id      INTEGER NOT NULL,\n'
        '  evid            TEXT NOT NULL,\n'
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
        '  duplicate       INTEGER NOT NULL DEFAULT 0,\n'
        '  PRIMARY KEY (catalog_id, evid),\n'
        '  FOREIGN KEY (catalog_id)\n'
        '    REFERENCES catalogs(catalog_id)\n'
        '    ON UPDATE CASCADE ON DELETE CASCADE\n'
        ')'
    ),
    (
        'CREATE INDEX IF NOT EXISTS idx_catalog_orig_time '
        f'ON {CATALOG_TABLE}(catalog_id, orig_time)'
    ),
]


def _ensure_catalog_table(cursor):
    """Create the catalog tables when needed."""
    for statement in CATALOG_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _event_row(event, catalog_id):
    """Convert a RequakeEvent into a database row tuple."""
    return (
        int(catalog_id),
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


def write_catalog(catalog, catalog_id, append=False, db_path=None):
    """
    Write a catalog into SQLite under the given catalog id.

    :param catalog: catalog to write
    :type catalog: RequakeCatalog
    :param catalog_id: id the events belong to
    :type catalog_id: int
    :param append: if False, replace the events of this catalog
    :type append: bool
    :param db_path: path to the database file
    :type db_path: str or None
    """
    catalog = list(catalog)
    conn = get_db_connection(initdb=True, db_path=db_path)
    try:
        cursor = conn.cursor()
        _ensure_catalog_table(cursor)
        if not append:
            execute_with_retry(
                lambda: cursor.execute(
                    f'DELETE FROM {CATALOG_TABLE} WHERE catalog_id = ?',
                    (int(catalog_id),),
                ),
                'clear catalog table',
            )
        execute_with_retry(
            lambda: cursor.executemany(
                f'''INSERT {'OR REPLACE ' if append else ''}INTO
                {CATALOG_TABLE} (
                catalog_id, evid, orig_time, lat, lon, depth_km, mag_type,
                mag, mag_author, author, catalog, contributor,
                contributor_id, location_name, trace_id, duplicate
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )''',
                (_event_row(event, catalog_id) for event in catalog),
            ),
            'write catalog rows',
        )
        execute_with_retry(
            lambda: cursor.execute(
                'UPDATE catalogs SET nevents = ? WHERE catalog_id = ?',
                (len(catalog), int(catalog_id)),
            ),
            'update catalog event count',
        )
        conn.commit()
    finally:
        conn.close()


def read_catalog(catalog_id=None, db_path=None):
    """
    Read a stored catalog from SQLite.

    :param catalog_id: catalog to read; defaults to the latest one
    :type catalog_id: int or None
    :param db_path: path to the database file
    :type db_path: str or None
    :return: the stored catalog
    :rtype: RequakeCatalog

    :raises FileNotFoundError: if the catalog is not stored
    """
    from ..catalog.catalog import RequakeCatalog

    catalog_id = resolve_catalog_id(catalog_id)
    conn = get_db_connection(initdb=False, db_path=db_path)
    try:
        rows = conn.execute(
            f'''
            SELECT * FROM {CATALOG_TABLE}
            WHERE catalog_id = ?
            ORDER BY orig_time
            ''',
            (int(catalog_id),),
        ).fetchall()
    except sqlite3.OperationalError as err:
        if MISSING_CATALOG_TABLE in str(err):
            raise FileNotFoundError(
                'Catalog not found in db file '
                f'{get_db_path(db_path=db_path)}'
            ) from err
        if 'no such column: catalog_id' in str(err):
            raise CatalogSchemaError(
                'The stored catalog predates the multi-catalog schema '
                f'in db file {get_db_path(db_path=db_path)}'
            ) from err
        raise
    finally:
        conn.close()
    catalog = RequakeCatalog()
    catalog.extend(_event_from_row(row) for row in rows)
    catalog.deduplicate()
    return catalog


def update_events_duplicate(evids, catalog_id, duplicate=True, db_path=None):
    """
    Set the duplicate flag for the given event IDs.

    :param evids: event IDs to update
    :type evids: iterable of str
    :param catalog_id: catalog the events belong to
    :type catalog_id: int
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
        for start in range(0, len(evids), _MAX_SQL_VARIABLES):
            chunk = evids[start:start + _MAX_SQL_VARIABLES]
            placeholders = ','.join('?' * len(chunk))
            execute_with_retry(
                lambda: cursor.execute(
                    f'UPDATE {CATALOG_TABLE} '
                    f'SET duplicate = ? '
                    f'WHERE catalog_id = ? '
                    f'AND evid IN ({placeholders}) AND duplicate != ?',
                    (int(duplicate), int(catalog_id), *chunk, int(duplicate)),
                ),
                'update event duplicate flag',
            )
            changed += cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return changed


def reset_duplicate_flags(catalog_id, db_path=None):
    """
    Clear the duplicate flag for all the events in a catalog.

    :param catalog_id: catalog to reset
    :type catalog_id: int
    :param db_path: path to the database file
    :type db_path: str or None
    :return: number of catalog rows changed
    :rtype: int
    """
    conn = get_db_connection(initdb=False, db_path=db_path)
    try:
        cursor = conn.cursor()
        try:
            execute_with_retry(
                lambda: cursor.execute(
                    f'UPDATE {CATALOG_TABLE} SET duplicate = 0 '
                    'WHERE duplicate != 0 AND catalog_id = ?',
                    (int(catalog_id),),
                ),
                'reset event duplicate flags',
            )
            changed = cursor.rowcount
        except sqlite3.OperationalError as err:
            if MISSING_CATALOG_TABLE in str(err):
                return 0
            raise
        conn.commit()
    finally:
        conn.close()
    return changed


def count_duplicate_events(catalog_id, db_path=None):
    """
    Return the number of events flagged as duplicate in a catalog.

    :param catalog_id: catalog to inspect
    :type catalog_id: int
    :param db_path: path to the database file
    :type db_path: str or None
    :return: number of duplicated events
    :rtype: int
    """
    conn = get_db_connection(initdb=False, db_path=db_path)
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT COUNT(*) FROM {CATALOG_TABLE} '
                'WHERE duplicate != 0 AND catalog_id = ?',
                (int(catalog_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if MISSING_CATALOG_TABLE in str(err):
                return 0
            raise
        return row[0]
    finally:
        conn.close()
