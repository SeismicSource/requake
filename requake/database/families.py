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
from .catalog import CATALOG_SCHEMA_STATEMENTS
from .db import execute_with_retry, get_db_connection, get_db_path
from .family_builds import (
    FAMILY_BUILDS_SCHEMA_STATEMENTS,
    FamilyBuildNotFoundError,  # noqa: F401 (re-exported for callers)
    resolve_build_id,
)

FAMILIES_TABLE = 'families'
MISSING_FAMILIES_TABLE = f'no such table: {FAMILIES_TABLE}'


class FamiliesSchemaError(RuntimeError):
    """Raised when the families table uses an incompatible schema."""


FAMILIES_SCHEMA_STATEMENTS = [
    *CATALOG_SCHEMA_STATEMENTS,
    *FAMILY_BUILDS_SCHEMA_STATEMENTS,
    f'''
    CREATE TABLE IF NOT EXISTS {FAMILIES_TABLE} (
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
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_families_number '
        f'ON {FAMILIES_TABLE}(build_id, family_number)'
    ),
]


def _ensure_families_table(cursor):
    """Create the family tables and indexes when needed."""
    for statement in FAMILIES_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _family_row(family, event, build_id, catalog_id):
    """Convert a family event into a database row tuple."""
    return (
        int(build_id),
        int(catalog_id),
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


def write_families(build_id, catalog_id, families):
    """
    Write catalog-scan families into SQLite.

    :param build_id: family build the families belong to
    :type build_id: int
    :param catalog_id: catalog the events belong to
    :type catalog_id: int
    :param families: families to write
    :type families: list of Family
    """
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_families_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {FAMILIES_TABLE} WHERE build_id = ?',
                (int(build_id),),
            ),
            'clear families table',
        )
        families = list(families)
        if families:
            execute_with_retry(
                lambda: cursor.executemany(
                    f'''INSERT INTO {FAMILIES_TABLE} (
                    build_id, catalog_id, evid, trace_id, orig_time, lon,
                    lat, depth_km, mag_type, mag, family_number, valid
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        _family_row(
                            family, event, build_id, catalog_id
                        )
                        for family in families
                        for event in family
                    ),
                ),
                'write family rows',
            )
        conn.commit()
    finally:
        conn.close()


def read_families(build_id=None, family_numbers=None):
    """
    Read catalog-scan families from SQLite.

    :param build_id: build to read; defaults to the latest one
    :type build_id: int or None
    :param family_numbers: If given, only read families with these numbers.
    :type family_numbers: iterable of int or None
    :return: List of families.
    :rtype: list of Family

    :raises FileNotFoundError: if no family is stored
    """
    from ..catalog import RequakeEvent
    from ..families.families import Family

    try:
        build_id = resolve_build_id(build_id)
    except FamilyBuildNotFoundError as err:
        raise FileNotFoundError(str(err)) from err
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
                    WHERE build_id = ?
                    AND family_number IN ({placeholders})
                    ORDER BY family_number, orig_time, evid, trace_id
                    ''',
                    [int(build_id), *family_numbers],
                ).fetchall()
            else:
                rows = cursor.execute(
                    f'''
                    SELECT * FROM {FAMILIES_TABLE}
                    WHERE build_id = ?
                    ORDER BY family_number, orig_time, evid, trace_id
                    ''',
                    (int(build_id),),
                ).fetchall()
        except sqlite3.OperationalError as err:
            if MISSING_FAMILIES_TABLE in str(err):
                raise FileNotFoundError(
                    f'Families not found in db file {get_db_path()}'
                ) from err
            if 'no such column: build_id' in str(err):
                raise FamiliesSchemaError(
                    'The stored families predate the multi-build schema '
                    f'in db file {get_db_path()}'
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


def update_family_valid(build_id, family_number, is_valid):
    """Update the validity flag for all events in one family."""
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        try:
            execute_with_retry(
                lambda: cursor.execute(
                    (
                        f'UPDATE {FAMILIES_TABLE} '
                        'SET valid = ? '
                        'WHERE build_id = ? AND family_number = ?'
                    ),
                    (int(is_valid), int(build_id), int(family_number)),
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
