# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed family persistence.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sqlite3
from obspy import UTCDateTime
from .db import execute_with_retry, get_db_connection, get_db_path

FAMILIES_TABLE = 'families'
MISSING_FAMILIES_TABLE = f'no such table: {FAMILIES_TABLE}'

FAMILIES_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {FAMILIES_TABLE} (
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
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_families_number '
        f'ON {FAMILIES_TABLE}(family_number)'
    ),
]


def _ensure_families_table(cursor):
    """Create the family table and indexes when needed."""
    for statement in FAMILIES_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _family_row(family, event):
    """Convert a family event into a database row tuple."""
    return (
        event.evid,
        event.trace_id,
        str(event.orig_time),
        event.lon,
        event.lat,
        event.depth,
        event.mag_type,
        event.mag,
        family.number,
        int(family.valid),
    )


def write_families(families):
    """Write catalog-scan families into SQLite."""
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_families_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(f'DELETE FROM {FAMILIES_TABLE}'),
            'clear families table',
        )
        families = list(families)
        if families:
            execute_with_retry(
                lambda: cursor.executemany(
                    f'''INSERT INTO {FAMILIES_TABLE} (
                    evid, trace_id, orig_time, lon, lat, depth_km,
                    mag_type, mag, family_number, valid
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        _family_row(family, event)
                        for family in families
                        for event in family
                    ),
                ),
                'write family rows',
            )
        conn.commit()
    finally:
        conn.close()


def read_families(family_numbers=None):
    """Read catalog-scan families from SQLite.

    :param family_numbers: If given, only read families with these numbers.
    :type family_numbers: iterable of int or None
    :return: List of families.
    :rtype: list of Family
    """
    from ..catalog import RequakeEvent
    from ..families.families import Family

    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        try:
            if family_numbers is not None:
                family_numbers = sorted(set(family_numbers))
                placeholders = ','.join('?' * len(family_numbers))
                rows = cursor.execute(
                    f'''
                    SELECT * FROM {FAMILIES_TABLE}
                    WHERE family_number IN ({placeholders})
                    ORDER BY family_number, orig_time, evid, trace_id
                    ''',
                    family_numbers,
                ).fetchall()
            else:
                rows = cursor.execute(
                    f'''
                    SELECT * FROM {FAMILIES_TABLE}
                    ORDER BY family_number, orig_time, evid, trace_id
                    '''
                ).fetchall()
        except sqlite3.OperationalError as err:
            if MISSING_FAMILIES_TABLE in str(err):
                raise FileNotFoundError(
                    f'Families not found in db file {get_db_path()}'
                ) from err
            raise
    finally:
        conn.close()

    families = []
    old_family_number = None
    family = None
    for row in rows:
        family_number = int(row['family_number'])
        if family_number != old_family_number:
            if family is not None:
                families.append(family)
            family = Family(family_number)
            family.valid = bool(row['valid'])
            old_family_number = family_number
        event = RequakeEvent(
            evid=row['evid'],
            orig_time=UTCDateTime(row['orig_time']),
            lon=row['lon'],
            lat=row['lat'],
            depth=row['depth_km'],
            mag_type=row['mag_type'],
            mag=row['mag'],
            trace_id=row['trace_id'],
        )
        family.append(event)
        family.valid = bool(row['valid'])
    if family is not None:
        families.append(family)
    return families


def update_family_valid(family_number, is_valid):
    """Update the validity flag for all events in one family."""
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        try:
            execute_with_retry(
                lambda: cursor.execute(
                    (
                        f'UPDATE {FAMILIES_TABLE} '
                        'SET valid = ? WHERE family_number = ?'
                    ),
                    (int(is_valid), int(family_number)),
                ),
                'update family valid flag',
            )
        except sqlite3.OperationalError as err:
            if MISSING_FAMILIES_TABLE in str(err):
                raise FileNotFoundError(
                    f'Families not found in db file {get_db_path()}'
                ) from err
            raise
        conn.commit()
    finally:
        conn.close()
