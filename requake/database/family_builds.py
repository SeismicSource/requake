# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed registry of the family builds stored in the database.

A family build is one execution of ``requake build_families`` on a scan
with a given clustering method and parameters.  It owns its rows in the
``families`` table, so that several builds from the same pair set can
coexist.
"""
import logging
import sqlite3
from obspy import UTCDateTime
from .._version import get_versions
from .db import execute_with_retry, get_db_connection, get_db_path
from .scans import SCANS_SCHEMA_STATEMENTS

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

FAMILY_BUILDS_TABLE = 'family_builds'
MISSING_FAMILY_BUILDS_TABLE = f'no such table: {FAMILY_BUILDS_TABLE}'
BUILD_STATUS_RUNNING = 'running'
BUILD_STATUS_COMPLETE = 'complete'
BUILD_STATUS_FAILED = 'failed'


class FamilyBuildNotFoundError(LookupError):
    """Raised when the requested build id is not in the database."""


class FamilyBuildsSchemaError(RuntimeError):
    """Raised when the build registry uses an incompatible schema."""


FAMILY_BUILDS_SCHEMA_STATEMENTS = [
    *SCANS_SCHEMA_STATEMENTS,
    f'''
    CREATE TABLE IF NOT EXISTS {FAMILY_BUILDS_TABLE} (
      build_id         INTEGER PRIMARY KEY AUTOINCREMENT,
      scan_id          INTEGER NOT NULL,
      label            TEXT,
      created_at       TEXT NOT NULL,
      finished_at      TEXT,
      status           TEXT NOT NULL DEFAULT '{BUILD_STATUS_RUNNING}',
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
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_family_builds_scan '
        f'ON {FAMILY_BUILDS_TABLE}(scan_id)'
    ),
]


def _ensure_family_builds_table(cursor):
    """Create the family build registry table when needed."""
    for statement in FAMILY_BUILDS_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _is_missing_family_builds_table_error(err):
    """Return True when a sqlite error means the registry is absent."""
    return MISSING_FAMILY_BUILDS_TABLE in str(err)


def _connect_or_none():
    """Open a read connection, or return None when no database exists."""
    try:
        return get_db_connection(initdb=False)
    except FileNotFoundError:
        return None


def _now():
    """Return the current UTC time as a compact string."""
    return str(UTCDateTime())[:19]


def _requake_version():
    """Return the running Requake version, if it can be determined."""
    try:
        return get_versions()['version']
    except Exception:  # pylint: disable=broad-except
        return None


def describe_build_row(row):
    """
    Return a short human-readable description of a build row.

    :param row: a ``family_builds`` row
    :type row: sqlite3.Row
    :return: description, or an empty string
    :rtype: str
    """
    details = []
    label = row['label']
    if label:
        details.append(f'label "{label}"')
    method = row['method']
    if method:
        details.append(f'method {method}')
    nfamilies = row['nfamilies']
    if nfamilies is not None:
        details.append(f'{int(nfamilies)} families')
    return f' ({", ".join(details)})' if details else ''


def create_family_build(scan_id, method, cc_min, params_hash, params_json,
                        label=None, nevents=None):
    """
    Store a new family build and return its id.

    :param scan_id: scan whose pairs are used
    :type scan_id: int
    :param method: clustering method (the ``clustering_algorithm`` value)
    :type method: str
    :param cc_min: minimum cross-correlation used by the build
    :type cc_min: float or None
    :param params_hash: hash of the build parameters
    :type params_hash: str
    :param params_json: full parameter snapshot, as JSON
    :type params_json: str
    :param label: user-provided label
    :type label: str or None
    :param nevents: number of events in the scan pair set
    :type nevents: int or None
    :return: the new build id
    :rtype: int
    """
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_family_builds_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                INSERT INTO {FAMILY_BUILDS_TABLE} (
                  scan_id, label, created_at, status, method, cc_min,
                  params_hash, params_json, requake_version, nevents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    int(scan_id), label, _now(), BUILD_STATUS_RUNNING,
                    method, cc_min, params_hash, params_json,
                    _requake_version(), nevents,
                ),
            ),
            'create family build row',
        )
        build_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    logger.debug(f'Created family build {build_id}')
    return build_id


def finish_family_build(build_id, nfamilies=None, nevents=None,
                        status=BUILD_STATUS_COMPLETE):
    """
    Mark a family build as finished and store its counters.

    :param build_id: build id
    :type build_id: int
    :param nfamilies: number of families written
    :type nfamilies: int or None
    :param nevents: number of events assigned to families
    :type nevents: int or None
    :param status: final status of the build
    :type status: str
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                UPDATE {FAMILY_BUILDS_TABLE} SET
                  status = ?,
                  finished_at = ?,
                  nfamilies = COALESCE(?, nfamilies),
                  nevents = COALESCE(?, nevents)
                WHERE build_id = ?
                ''',
                (status, _now(), nfamilies, nevents, int(build_id)),
            ),
            'finish family build row',
        )
        conn.commit()
    finally:
        conn.close()


def update_family_build_label(build_id, label):
    """
    Store the label of a family build.

    :param build_id: family build id
    :type build_id: int
    :param label: new label, or None to remove it
    :type label: str or None
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                f'UPDATE {FAMILY_BUILDS_TABLE} SET label = ? '
                'WHERE build_id = ?',
                (label, int(build_id)),
            ),
            'update family build label',
        )
        conn.commit()
    finally:
        conn.close()


def read_family_builds(scan_id=None):
    """
    Return stored family builds, ordered by id.

    :param scan_id: if given, only return builds of this scan
    :type scan_id: int or None
    :return: build rows
    :rtype: list of sqlite3.Row
    """
    conn = _connect_or_none()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        try:
            if scan_id is None:
                return cursor.execute(
                    f'SELECT * FROM {FAMILY_BUILDS_TABLE} ORDER BY build_id'
                ).fetchall()
            return cursor.execute(
                f'''
                SELECT * FROM {FAMILY_BUILDS_TABLE}
                WHERE scan_id = ?
                ORDER BY build_id
                ''',
                (int(scan_id),),
            ).fetchall()
        except sqlite3.OperationalError as err:
            if _is_missing_family_builds_table_error(err):
                return []
            raise
    finally:
        conn.close()


def read_family_build(build_id):
    """
    Return the row for one family build.

    :param build_id: build id
    :type build_id: int
    :return: the build row
    :rtype: sqlite3.Row

    :raises FamilyBuildNotFoundError: if the build is not stored
    """
    conn = _connect_or_none()
    if conn is None:
        raise FamilyBuildNotFoundError(
            f'Family build {build_id} not found in db file '
            f'{get_db_path()}'
        )
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT * FROM {FAMILY_BUILDS_TABLE} WHERE build_id = ?',
                (int(build_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_family_builds_table_error(err):
                raise FamilyBuildNotFoundError(
                    f'Family build {build_id} not found in db file '
                    f'{get_db_path()}'
                ) from err
            raise
    finally:
        conn.close()
    if row is None:
        raise FamilyBuildNotFoundError(
            f'Family build {build_id} not found in db file '
            f'{get_db_path()}'
        )
    return row


def latest_build_id(scan_id=None):
    """
    Return the id of the most recent family build.

    :param scan_id: if given, only consider builds of this scan
    :type scan_id: int or None
    :return: build id, or None when no build is stored
    :rtype: int or None
    """
    conn = _connect_or_none()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        try:
            if scan_id is None:
                row = cursor.execute(
                    f'SELECT MAX(build_id) FROM {FAMILY_BUILDS_TABLE}'
                ).fetchone()
            else:
                row = cursor.execute(
                    f'SELECT MAX(build_id) FROM {FAMILY_BUILDS_TABLE} '
                    'WHERE scan_id = ?',
                    (int(scan_id),),
                ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_family_builds_table_error(err):
                return None
            raise
    finally:
        conn.close()
    return None if row is None or row[0] is None else int(row[0])


def find_family_build_by_hash(scan_id, method, params_hash):
    """
    Return the most recent build with the given scan and parameters.

    :param scan_id: scan id
    :type scan_id: int
    :param method: clustering method
    :type method: str
    :param params_hash: hash of the build parameters
    :type params_hash: str
    :return: the build row, or None
    :rtype: sqlite3.Row or None
    """
    conn = _connect_or_none()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        try:
            return cursor.execute(
                f'''
                SELECT * FROM {FAMILY_BUILDS_TABLE}
                WHERE scan_id = ? AND method = ? AND params_hash = ?
                ORDER BY build_id DESC
                LIMIT 1
                ''',
                (int(scan_id), method, params_hash),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_family_builds_table_error(err):
                return None
            raise
    finally:
        conn.close()


def resolve_build_id(requested=None, scan_id=None):
    """
    Return the family build id to use, defaulting to the latest one.

    :param requested: build id requested on the command line
    :type requested: int or None
    :param scan_id: if given, restrict the default to this scan
    :type scan_id: int or None
    :return: build id
    :rtype: int

    :raises FamilyBuildNotFoundError: if no build is available
    """
    if requested is not None:
        read_family_build(requested)
        return int(requested)
    build_id = latest_build_id(scan_id=scan_id)
    if build_id is None:
        raise FamilyBuildNotFoundError(
            f'No family build found in db file {get_db_path()}. '
            'Run "requake build_families" first.'
        )
    row = read_family_build(build_id)
    logger.info(
        f'Using family build {build_id}{describe_build_row(row)} '
        f'from scan {int(row["scan_id"])}'
    )
    return build_id


def summarize_family_build_delete(build_id):
    """
    Describe what deleting a family build would remove.

    :param build_id: build id
    :type build_id: int
    :return: counts of dependent rows
    :rtype: dict

    :raises FamilyBuildNotFoundError: if the build is not stored
    """
    row = read_family_build(build_id)
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        families = _count_or_zero(
            cursor,
            'SELECT COUNT(*) FROM families WHERE build_id = ?',
            (int(build_id),),
        )
        detections = _count_or_zero(
            cursor,
            'SELECT COUNT(*) FROM template_detections WHERE build_id = ?',
            (int(build_id),),
        )
    finally:
        conn.close()
    return {
        'build_id': int(build_id),
        'label': row['label'],
        'scan_id': int(row['scan_id']),
        'method': row['method'],
        'families': families,
        'detections': detections,
    }


def _count_or_zero(cursor, sql, params=()):
    """Run a COUNT query, returning 0 when the table does not exist."""
    try:
        return int(cursor.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError as err:
        if 'no such table' in str(err):
            return 0
        raise


def reset_family_build(build_id, method, cc_min, params_hash, params_json,
                       label=None, scan_id=None):
    """
    Clear the families of a build and put it back in the running state.

    The build id is kept, so that the build can be replaced in place.

    :param build_id: build id
    :type build_id: int
    :param method: clustering method
    :type method: str
    :param cc_min: minimum cross-correlation used by the build
    :type cc_min: float or None
    :param params_hash: hash of the new build parameters
    :type params_hash: str
    :param params_json: full parameter snapshot, as JSON
    :type params_json: str
    :param label: user-provided label
    :type label: str or None
    :param scan_id: scan whose pairs are used
    :type scan_id: int or None

    :raises FamilyBuildNotFoundError: if the build is not stored
    """
    read_family_build(build_id)
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        for table in ('template_detections', 'families'):
            _delete_from_table(cursor, table, build_id)
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                UPDATE {FAMILY_BUILDS_TABLE} SET
                  scan_id = COALESCE(?, scan_id),
                  label = COALESCE(?, label),
                  created_at = ?,
                  finished_at = NULL,
                  status = ?,
                  method = ?,
                  cc_min = ?,
                  params_hash = ?,
                  params_json = ?,
                  nfamilies = NULL,
                  nevents = NULL
                WHERE build_id = ?
                ''',
                (
                    scan_id, label, _now(), BUILD_STATUS_RUNNING, method,
                    cc_min, params_hash, params_json, int(build_id),
                ),
            ),
            'reset family build row',
        )
        conn.commit()
    finally:
        conn.close()


def _delete_from_table(cursor, table, build_id):
    """Delete the rows of one build, ignoring missing tables."""
    try:
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {table} WHERE build_id = ?',
                (int(build_id),),
            ),
            f'delete build rows from {table}',
        )
    except sqlite3.OperationalError as err:
        if 'no such table' in str(err):
            return
        raise


def delete_family_build_row(build_id):
    """
    Delete a family build and its families and template detections.

    :param build_id: build id
    :type build_id: int
    :return: counts of the removed rows
    :rtype: dict

    :raises FamilyBuildNotFoundError: if the build is not stored
    """
    summary = summarize_family_build_delete(build_id)
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        for table in ('template_detections', 'families'):
            _delete_from_table(cursor, table, build_id)
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {FAMILY_BUILDS_TABLE} WHERE build_id = ?',
                (int(build_id),),
            ),
            'delete family build row',
        )
        conn.commit()
    finally:
        conn.close()
    return summary
