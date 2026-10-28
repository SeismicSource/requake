# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed registry of the catalog scans stored in the database.

A scan is one execution of ``requake scan_catalog`` on a given catalog.
It owns its event pairs and its trace metadata, so that several scans
performed with different parameters can coexist in the same database.
"""
import logging
import sqlite3
from obspy import UTCDateTime
from .._version import get_versions
from .catalogs import (
    CATALOGS_SCHEMA_STATEMENTS,
    count_stored_events,
    describe_catalog_row,
    read_catalog_row,
)
from .db import execute_with_retry, get_db_connection, get_db_path

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

SCANS_TABLE = 'scans'
MISSING_SCANS_TABLE = f'no such table: {SCANS_TABLE}'
SCAN_STATUS_RUNNING = 'running'
SCAN_STATUS_COMPLETE = 'complete'
SCAN_STATUS_FAILED = 'failed'


class ScanNotFoundError(LookupError):
    """Raised when the requested scan id is not in the database."""


class ScansSchemaError(RuntimeError):
    """Raised when the scan registry uses an incompatible schema."""


SCANS_SCHEMA_STATEMENTS = [
    *CATALOGS_SCHEMA_STATEMENTS,
    f'''
    CREATE TABLE IF NOT EXISTS {SCANS_TABLE} (
      scan_id          INTEGER PRIMARY KEY AUTOINCREMENT,
      catalog_id       INTEGER NOT NULL,
      label            TEXT,
      created_at       TEXT NOT NULL,
      finished_at      TEXT,
      status           TEXT NOT NULL DEFAULT '{SCAN_STATUS_RUNNING}',
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
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_scans_catalog '
        f'ON {SCANS_TABLE}(catalog_id)'
    ),
]


def _ensure_scans_table(cursor):
    """Create the scan registry table when needed."""
    for statement in SCANS_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _is_missing_scans_table_error(err):
    """Return True when a sqlite error means the registry is absent."""
    return MISSING_SCANS_TABLE in str(err)


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


def describe_scan_row(row):
    """
    Return a short human-readable description of a scan row.

    :param row: a ``scans`` row
    :type row: sqlite3.Row
    :return: description, or an empty string
    :rtype: str
    """
    details = []
    label = row['label']
    if label:
        details.append(f'label "{label}"')
    npairs = row['npairs_stored']
    if npairs is not None:
        details.append(f'{int(npairs)} pairs')
    return f' ({", ".join(details)})' if details else ''


def create_scan(catalog_id, params_hash, params_json, label=None,
                nevents=None):
    """
    Store a new scan and return its id.

    :param catalog_id: catalog the scan is performed on
    :type catalog_id: int
    :param params_hash: hash of the scan parameters
    :type params_hash: str
    :param params_json: full parameter snapshot, as JSON
    :type params_json: str
    :param label: user-provided label
    :type label: str or None
    :param nevents: number of catalog events seen by the scan
    :type nevents: int or None
    :return: the new scan id
    :rtype: int
    """
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_scans_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                INSERT INTO {SCANS_TABLE} (
                  catalog_id, label, created_at, status, params_hash,
                  params_json, requake_version, nevents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    int(catalog_id), label, _now(), SCAN_STATUS_RUNNING,
                    params_hash, params_json, _requake_version(), nevents,
                ),
            ),
            'create scan row',
        )
        scan_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    logger.debug(f'Created scan {scan_id}')
    return scan_id


def finish_scan(scan_id, npairs_stored=None, npairs_analyzed=None,
                status=SCAN_STATUS_COMPLETE):
    """
    Mark a scan as finished and store its pair counters.

    :param scan_id: scan id
    :type scan_id: int
    :param npairs_stored: number of pair rows written for the scan
    :type npairs_stored: int or None
    :param npairs_analyzed: number of pairs analyzed by the scan
    :type npairs_analyzed: int or None
    :param status: final status of the scan
    :type status: str
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                UPDATE {SCANS_TABLE} SET
                  status = ?,
                  finished_at = ?,
                  npairs_stored = COALESCE(?, npairs_stored),
                  npairs_analyzed = COALESCE(?, npairs_analyzed)
                WHERE scan_id = ?
                ''',
                (
                    status, _now(), npairs_stored, npairs_analyzed,
                    int(scan_id),
                ),
            ),
            'finish scan row',
        )
        conn.commit()
    finally:
        conn.close()


def read_scans(catalog_id=None):
    """
    Return stored scans, ordered by id.

    :param catalog_id: if given, only return scans of this catalog
    :type catalog_id: int or None
    :return: scan rows
    :rtype: list of sqlite3.Row
    """
    conn = _connect_or_none()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        try:
            if catalog_id is None:
                return cursor.execute(
                    f'SELECT * FROM {SCANS_TABLE} ORDER BY scan_id'
                ).fetchall()
            return cursor.execute(
                f'''
                SELECT * FROM {SCANS_TABLE}
                WHERE catalog_id = ?
                ORDER BY scan_id
                ''',
                (int(catalog_id),),
            ).fetchall()
        except sqlite3.OperationalError as err:
            if _is_missing_scans_table_error(err):
                return []
            raise
    finally:
        conn.close()


def read_scan(scan_id):
    """
    Return the row for one scan.

    :param scan_id: scan id
    :type scan_id: int
    :return: the scan row
    :rtype: sqlite3.Row

    :raises ScanNotFoundError: if the scan is not stored
    """
    conn = _connect_or_none()
    if conn is None:
        raise ScanNotFoundError(
            f'Scan {scan_id} not found in db file {get_db_path()}'
        )
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT * FROM {SCANS_TABLE} WHERE scan_id = ?',
                (int(scan_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_scans_table_error(err):
                raise ScanNotFoundError(
                    f'Scan {scan_id} not found in db file {get_db_path()}'
                ) from err
            raise
    finally:
        conn.close()
    if row is None:
        raise ScanNotFoundError(
            f'Scan {scan_id} not found in db file {get_db_path()}'
        )
    return row


def scan_catalog_id(scan_id):
    """
    Return the id of the catalog a scan was performed on.

    :param scan_id: scan id
    :type scan_id: int
    :return: catalog id
    :rtype: int

    :raises ScanNotFoundError: if the scan is not stored
    """
    return int(read_scan(scan_id)['catalog_id'])


def latest_scan_id(catalog_id=None):
    """
    Return the id of the most recent scan.

    :param catalog_id: if given, only consider scans of this catalog
    :type catalog_id: int or None
    :return: scan id, or None when no scan is stored
    :rtype: int or None
    """
    conn = _connect_or_none()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        try:
            if catalog_id is None:
                row = cursor.execute(
                    f'SELECT MAX(scan_id) FROM {SCANS_TABLE}'
                ).fetchone()
            else:
                row = cursor.execute(
                    f'SELECT MAX(scan_id) FROM {SCANS_TABLE} '
                    'WHERE catalog_id = ?',
                    (int(catalog_id),),
                ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_scans_table_error(err):
                return None
            raise
    finally:
        conn.close()
    return None if row is None or row[0] is None else int(row[0])


def find_scan_by_hash(params_hash, catalog_id=None):
    """
    Return the most recent scan with the given parameters.

    :param params_hash: hash of the scan parameters
    :type params_hash: str
    :param catalog_id: if given, only consider scans of this catalog
    :type catalog_id: int or None
    :return: the scan row, or None
    :rtype: sqlite3.Row or None
    """
    conn = _connect_or_none()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        try:
            if catalog_id is None:
                return cursor.execute(
                    f'''
                    SELECT * FROM {SCANS_TABLE}
                    WHERE params_hash = ?
                    ORDER BY scan_id DESC
                    LIMIT 1
                    ''',
                    (params_hash,),
                ).fetchone()
            return cursor.execute(
                f'''
                SELECT * FROM {SCANS_TABLE}
                WHERE params_hash = ? AND catalog_id = ?
                ORDER BY scan_id DESC
                LIMIT 1
                ''',
                (params_hash, int(catalog_id)),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_scans_table_error(err):
                return None
            raise
    finally:
        conn.close()


def _warn_if_catalog_changed(row):
    """Warn when the catalog of a scan changed after the scan."""
    nevents = row['nevents']
    if nevents is None:
        return
    try:
        current = count_stored_events(int(row['catalog_id']))
    except Exception:  # pylint: disable=broad-except
        return
    if current != int(nevents):
        logger.warning(
            f'Catalog {row["catalog_id"]} now has {current} events, '
            f'but scan {row["scan_id"]} was performed on {int(nevents)}'
        )


def resolve_scan_id(requested=None, catalog_id=None):
    """
    Return the scan id to use, defaulting to the latest one.

    :param requested: scan id requested on the command line
    :type requested: int or None
    :param catalog_id: if given, restrict the default to this catalog
    :type catalog_id: int or None
    :return: scan id
    :rtype: int

    :raises ScanNotFoundError: if no scan is available
    """
    if requested is not None:
        read_scan(requested)
        return int(requested)
    scan_id = latest_scan_id(catalog_id=catalog_id)
    if scan_id is None:
        raise ScanNotFoundError(
            f'No catalog scan found in db file {get_db_path()}. '
            'Run "requake scan_catalog" first.'
        )
    row = read_scan(scan_id)
    catalog_row = read_catalog_row(int(row['catalog_id']))
    logger.info(
        f'Using scan {scan_id}{describe_scan_row(row)} on catalog '
        f'{int(row["catalog_id"])}{describe_catalog_row(catalog_row)}'
    )
    _warn_if_catalog_changed(row)
    return scan_id


def _count_or_zero(cursor, sql, params=()):
    """Run a COUNT query, returning 0 when the table does not exist."""
    try:
        return int(cursor.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError as err:
        if 'no such table' in str(err):
            return 0
        raise


def summarize_scan_delete(scan_id):
    """
    Describe what deleting a scan would remove.

    :param scan_id: scan id
    :type scan_id: int
    :return: counts of dependent rows
    :rtype: dict

    :raises ScanNotFoundError: if the scan is not stored
    """
    row = read_scan(scan_id)
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        builds = _count_or_zero(
            cursor,
            'SELECT COUNT(*) FROM family_builds WHERE scan_id = ?',
            (int(scan_id),),
        )
        families = _count_or_zero(
            cursor,
            '''
            SELECT COUNT(*) FROM families WHERE build_id IN (
              SELECT build_id FROM family_builds WHERE scan_id = ?
            )
            ''',
            (int(scan_id),),
        )
        detections = _count_or_zero(
            cursor,
            '''
            SELECT COUNT(*) FROM template_detections WHERE build_id IN (
              SELECT build_id FROM family_builds WHERE scan_id = ?
            )
            ''',
            (int(scan_id),),
        )
        pairs = row['npairs_stored']
        if pairs is None:
            pairs = _count_or_zero(
                cursor,
                'SELECT COUNT(*) FROM event_pairs WHERE scan_id = ?',
                (int(scan_id),),
            )
    finally:
        conn.close()
    return {
        'scan_id': int(scan_id),
        'label': row['label'],
        'catalog_id': int(row['catalog_id']),
        'builds': builds,
        'families': families,
        'detections': detections,
        'pairs': int(pairs),
    }


def reset_scan(scan_id, params_hash, params_json, nevents=None,
               label=None):
    """
    Clear the pairs of a scan and put it back in the running state.

    The scan id is kept, so that the scan can be replaced in place.

    :param scan_id: scan id
    :type scan_id: int
    :param params_hash: hash of the new scan parameters
    :type params_hash: str
    :param params_json: full parameter snapshot, as JSON
    :type params_json: str
    :param nevents: number of catalog events seen by the scan
    :type nevents: int or None
    :param label: user-provided label
    :type label: str or None

    :raises ScanNotFoundError: if the scan is not stored
    """
    from .family_builds import delete_family_build_row, read_family_builds

    read_scan(scan_id)
    for build in read_family_builds(scan_id=scan_id):
        delete_family_build_row(int(build['build_id']))
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        for table in ('event_pairs', 'trace_metadata'):
            _delete_from_table(cursor, table, scan_id)
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                UPDATE {SCANS_TABLE} SET
                  label = COALESCE(?, label),
                  created_at = ?,
                  finished_at = NULL,
                  status = ?,
                  params_hash = ?,
                  params_json = ?,
                  nevents = COALESCE(?, nevents),
                  npairs_stored = NULL,
                  npairs_analyzed = NULL
                WHERE scan_id = ?
                ''',
                (
                    label, _now(), SCAN_STATUS_RUNNING, params_hash,
                    params_json, nevents, int(scan_id),
                ),
            ),
            'reset scan row',
        )
        conn.commit()
    finally:
        conn.close()


def _delete_from_table(cursor, table, scan_id):
    """Delete the rows of one scan, ignoring missing tables."""
    try:
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {table} WHERE scan_id = ?',
                (int(scan_id),),
            ),
            f'delete scan rows from {table}',
        )
    except sqlite3.OperationalError as err:
        if 'no such table' in str(err):
            return
        raise


def delete_scan_row(scan_id):
    """
    Delete a scan and everything built from it.

    :param scan_id: scan id
    :type scan_id: int
    :return: counts of the removed rows
    :rtype: dict

    :raises ScanNotFoundError: if the scan is not stored
    """
    from .family_builds import delete_family_build_row, read_family_builds

    summary = summarize_scan_delete(scan_id)
    for build in read_family_builds(scan_id=scan_id):
        delete_family_build_row(int(build['build_id']))
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        for table in ('event_pairs', 'trace_metadata'):
            _delete_from_table(cursor, table, scan_id)
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {SCANS_TABLE} WHERE scan_id = ?',
                (int(scan_id),),
            ),
            'delete scan row',
        )
        conn.commit()
    finally:
        conn.close()
    return summary
