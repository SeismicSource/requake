# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed template detection persistence.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sqlite3
from obspy import UTCDateTime
from .db import execute_with_retry, get_db_connection, get_db_path

TEMPLATE_DETECTIONS_TABLE = 'template_detections'
MISSING_TEMPLATE_DETECTIONS_TABLE = (
    f'no such table: {TEMPLATE_DETECTIONS_TABLE}'
)

TEMPLATES_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {TEMPLATE_DETECTIONS_TABLE} (
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
    ''',
    f'''
    CREATE INDEX IF NOT EXISTS idx_template_detections_family
    ON {TEMPLATE_DETECTIONS_TABLE}(family_number)
    ''',
    f'''
    CREATE INDEX IF NOT EXISTS idx_template_detections_trace
    ON {TEMPLATE_DETECTIONS_TABLE}(trace_id)
    ''',
]


def _ensure_template_detections_table(cursor):
    """Create the template detection table and indexes when needed."""
    for statement in TEMPLATES_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _detection_row(detection):
    """Convert a detection tuple into a database row tuple."""
    family_number, trace_id, event, cc_max = detection
    return (
        family_number,
        trace_id,
        event.evid,
        str(event.orig_time),
        event.lon,
        event.lat,
        event.depth,
        cc_max,
    )


def write_template_detections(detections, append=True):
    """Write template detections into SQLite."""
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_template_detections_table(cursor)
        if not append:
            execute_with_retry(
                lambda: cursor.execute(
                    f'DELETE FROM {TEMPLATE_DETECTIONS_TABLE}'
                ),
                'clear template detections table',
            )
        if detections:
            execute_with_retry(
                lambda: cursor.executemany(
                    f'''
                    INSERT OR REPLACE INTO {TEMPLATE_DETECTIONS_TABLE} (
                      family_number, trace_id, evid, orig_time, lon, lat,
                      depth_km, cc_max
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (_detection_row(detection) for detection in detections),
                ),
                'write template detections',
            )
        conn.commit()
    finally:
        conn.close()


def clear_template_detections():
    """Delete all template detections from SQLite."""
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_template_detections_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(f'DELETE FROM {TEMPLATE_DETECTIONS_TABLE}'),
            'clear template detections',
        )
        conn.commit()
    finally:
        conn.close()


def has_template_detections():
    """Return True when the template detection table contains rows."""
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_template_detections_table(cursor)
        count = cursor.execute(
            f'SELECT COUNT(*) FROM {TEMPLATE_DETECTIONS_TABLE}'
        ).fetchone()[0]
        return count > 0
    finally:
        conn.close()


def read_template_families():
    """Read template detections from SQLite and group them as families."""
    from ..catalog import RequakeEvent
    from ..families.families import Family

    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        try:
            rows = cursor.execute(
                f'''
                SELECT * FROM {TEMPLATE_DETECTIONS_TABLE}
                ORDER BY family_number, trace_id, orig_time, evid
                '''
            ).fetchall()
        except sqlite3.OperationalError as err:
            if MISSING_TEMPLATE_DETECTIONS_TABLE in str(err):
                raise FileNotFoundError(
                    'Template detections not found in db file '
                    f'{get_db_path()}'
                ) from err
            raise
    finally:
        conn.close()

    families = []
    current_key = None
    family = None
    for row in rows:
        key = (int(row['family_number']), row['trace_id'])
        if key != current_key:
            if family is not None:
                families.append(family)
            family = Family(key[0])
            family.trace_id = key[1]
            current_key = key
        event = RequakeEvent(
            evid=row['evid'],
            orig_time=UTCDateTime(row['orig_time']),
            lon=row['lon'],
            lat=row['lat'],
            depth=row['depth_km'],
            trace_id=row['trace_id'],
        )
        family.append(event)
    if family is not None:
        families.append(family)
    return families
