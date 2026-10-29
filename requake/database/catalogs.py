# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed registry of the catalogs stored in the database.

Every catalog read by ``requake read_catalog`` gets its own
``catalog_id`` and its own ``catalog`` rows, so that reading a new
catalog never replaces an existing one.
"""
import logging
import sqlite3
from obspy import UTCDateTime
from .._version import get_versions
from .db import execute_with_retry, get_db_connection, get_db_path

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

CATALOGS_TABLE = 'catalogs'
MISSING_CATALOGS_TABLE = f'no such table: {CATALOGS_TABLE}'


class CatalogNotFoundError(LookupError):
    """Raised when the requested catalog id is not in the database."""


class CatalogsSchemaError(RuntimeError):
    """Raised when the catalog registry uses an incompatible schema."""


CATALOGS_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {CATALOGS_TABLE} (
      catalog_id      INTEGER PRIMARY KEY AUTOINCREMENT,
      label           TEXT,
      created_at      TEXT NOT NULL,
      source          TEXT,
      params_hash     TEXT NOT NULL,
      params_json     TEXT NOT NULL,
      requake_version TEXT,
      nevents         INTEGER
    )
    ''',
]


def _ensure_catalogs_table(cursor):
    """Create the catalog registry table when needed."""
    for statement in CATALOGS_SCHEMA_STATEMENTS:
        cursor.execute(statement)


def _is_missing_catalogs_table_error(err):
    """Return True when a sqlite error means the registry is absent."""
    return MISSING_CATALOGS_TABLE in str(err)


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


def _describe(row):
    """Return a short human-readable description of a catalog row."""
    details = []
    label = row['label']
    if label:
        details.append(f'label "{label}"')
    nevents = row['nevents']
    if nevents is not None:
        details.append(f'{int(nevents)} events')
    return f' ({", ".join(details)})' if details else ''


def describe_catalog_row(row):
    """
    Return a short human-readable description of a catalog row.

    :param row: a ``catalogs`` row
    :type row: sqlite3.Row
    :return: description, or an empty string
    :rtype: str
    """
    return _describe(row)


def create_catalog(params_hash, params_json, source=None, label=None,
                   nevents=None):
    """
    Store a new catalog and return its id.

    :param params_hash: hash of the parameters used to read the catalog
    :type params_hash: str
    :param params_json: full parameter snapshot, as JSON
    :type params_json: str
    :param source: description of the catalog source
    :type source: str or None
    :param label: user-provided label
    :type label: str or None
    :param nevents: number of events in the catalog
    :type nevents: int or None
    :return: the new catalog id
    :rtype: int
    """
    conn = get_db_connection(initdb=True)
    try:
        cursor = conn.cursor()
        _ensure_catalogs_table(cursor)
        execute_with_retry(
            lambda: cursor.execute(
                f'''
                INSERT INTO {CATALOGS_TABLE} (
                  label, created_at, source, params_hash, params_json,
                  requake_version, nevents
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    label, _now(), source, params_hash, params_json,
                    _requake_version(), nevents,
                ),
            ),
            'create catalog row',
        )
        catalog_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    logger.debug(f'Created catalog {catalog_id}')
    return catalog_id


def update_catalog_nevents(catalog_id, nevents):
    """
    Store the number of events of a catalog.

    :param catalog_id: catalog id
    :type catalog_id: int
    :param nevents: number of events
    :type nevents: int
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                f'UPDATE {CATALOGS_TABLE} SET nevents = ? '
                'WHERE catalog_id = ?',
                (int(nevents), int(catalog_id)),
            ),
            'update catalog event count',
        )
        conn.commit()
    finally:
        conn.close()


def update_catalog_label(catalog_id, label):
    """
    Store the label of a catalog.

    :param catalog_id: catalog id
    :type catalog_id: int
    :param label: new label, or None to remove it
    :type label: str or None
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                f'UPDATE {CATALOGS_TABLE} SET label = ? '
                'WHERE catalog_id = ?',
                (label, int(catalog_id)),
            ),
            'update catalog label',
        )
        conn.commit()
    finally:
        conn.close()


def read_catalogs():
    """
    Return all stored catalogs, ordered by id.

    :return: catalog rows; empty when no catalog was ever stored
    :rtype: list of sqlite3.Row
    """
    conn = _connect_or_none()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        try:
            return cursor.execute(
                f'SELECT * FROM {CATALOGS_TABLE} ORDER BY catalog_id'
            ).fetchall()
        except sqlite3.OperationalError as err:
            if _is_missing_catalogs_table_error(err):
                return []
            raise
    finally:
        conn.close()


def read_catalog_row(catalog_id):
    """
    Return the row for one catalog.

    :param catalog_id: catalog id
    :type catalog_id: int
    :return: the catalog row
    :rtype: sqlite3.Row

    :raises CatalogNotFoundError: if the catalog is not stored
    """
    conn = _connect_or_none()
    if conn is None:
        raise CatalogNotFoundError(
            f'Catalog {catalog_id} not found in db file {get_db_path()}'
        )
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT * FROM {CATALOGS_TABLE} WHERE catalog_id = ?',
                (int(catalog_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_catalogs_table_error(err):
                raise CatalogNotFoundError(
                    f'Catalog {catalog_id} not found in db file '
                    f'{get_db_path()}'
                ) from err
            raise
    finally:
        conn.close()
    if row is None:
        raise CatalogNotFoundError(
            f'Catalog {catalog_id} not found in db file {get_db_path()}'
        )
    return row


def latest_catalog_id():
    """
    Return the id of the most recently created catalog.

    :return: catalog id, or None when no catalog is stored
    :rtype: int or None
    """
    conn = _connect_or_none()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                f'SELECT MAX(catalog_id) FROM {CATALOGS_TABLE}'
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_catalogs_table_error(err):
                return None
            raise
    finally:
        conn.close()
    return None if row is None or row[0] is None else int(row[0])


def find_catalog_by_hash(params_hash):
    """
    Return the most recent catalog read with the given parameters.

    :param params_hash: hash of the catalog parameters
    :type params_hash: str
    :return: the catalog row, or None
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
                SELECT * FROM {CATALOGS_TABLE}
                WHERE params_hash = ?
                ORDER BY catalog_id DESC
                LIMIT 1
                ''',
                (params_hash,),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if _is_missing_catalogs_table_error(err):
                return None
            raise
    finally:
        conn.close()


def resolve_catalog_id(requested=None):
    """
    Return the catalog id to use, defaulting to the latest one.

    :param requested: catalog id requested on the command line
    :type requested: int or None
    :return: catalog id
    :rtype: int

    :raises CatalogNotFoundError: if no catalog is available
    """
    if requested is not None:
        read_catalog_row(requested)
        return int(requested)
    catalog_id = latest_catalog_id()
    if catalog_id is None:
        raise CatalogNotFoundError(
            f'No catalog found in db file {get_db_path()}. '
            'Run "requake read_catalog" first.'
        )
    row = read_catalog_row(catalog_id)
    logger.info(f'Using catalog {catalog_id}{_describe(row)}')
    return catalog_id


def count_catalog_scans(catalog_id):
    """
    Return the number of scans performed on a catalog.

    :param catalog_id: catalog id
    :type catalog_id: int
    :return: number of scans
    :rtype: int
    """
    conn = _connect_or_none()
    if conn is None:
        return 0
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                'SELECT COUNT(*) FROM scans WHERE catalog_id = ?',
                (int(catalog_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if 'no such table: scans' in str(err):
                return 0
            raise
        return int(row[0])
    finally:
        conn.close()


def count_stored_events(catalog_id):
    """
    Return the number of event rows stored for a catalog.

    :param catalog_id: catalog id
    :type catalog_id: int
    :return: number of stored events
    :rtype: int
    """
    conn = _connect_or_none()
    if conn is None:
        return 0
    try:
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                'SELECT COUNT(*) FROM catalog WHERE catalog_id = ?',
                (int(catalog_id),),
            ).fetchone()
        except sqlite3.OperationalError as err:
            if 'no such table: catalog' in str(err):
                return 0
            if 'no such column: catalog_id' in str(err):
                raise CatalogsSchemaError(
                    'The stored catalog predates the multi-catalog '
                    f'schema in db file {get_db_path()}'
                ) from err
            raise
        return int(row[0])
    finally:
        conn.close()


def summarize_catalog_delete(catalog_id):
    """
    Describe what deleting a catalog would remove.

    :param catalog_id: catalog id
    :type catalog_id: int
    :return: counts of dependent rows
    :rtype: dict

    :raises CatalogNotFoundError: if the catalog is not stored
    """
    from .scans import read_scans, summarize_scan_delete

    row = read_catalog_row(catalog_id)
    summary = {
        'catalog_id': int(catalog_id),
        'label': row['label'],
        'events': count_stored_events(catalog_id),
        'scans': 0,
        'builds': 0,
        'pairs': 0,
        'families': 0,
        'detections': 0,
    }
    for scan in read_scans(catalog_id=catalog_id):
        scan_summary = summarize_scan_delete(int(scan['scan_id']))
        summary['scans'] += 1
        summary['builds'] += scan_summary['builds']
        summary['pairs'] += scan_summary['pairs']
        summary['families'] += scan_summary['families']
        summary['detections'] += scan_summary['detections']
    return summary


def delete_catalog_row(catalog_id):
    """
    Delete a catalog and everything built from it.

    :param catalog_id: catalog id
    :type catalog_id: int
    :return: counts of the removed rows
    :rtype: dict

    :raises CatalogNotFoundError: if the catalog is not stored
    """
    from .scans import delete_scan_row, read_scans

    summary = summarize_catalog_delete(catalog_id)
    for scan in read_scans(catalog_id=catalog_id):
        delete_scan_row(int(scan['scan_id']))
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        execute_with_retry(
            lambda: cursor.execute(
                'DELETE FROM catalog WHERE catalog_id = ?',
                (int(catalog_id),),
            ),
            'delete catalog events',
        )
        execute_with_retry(
            lambda: cursor.execute(
                f'DELETE FROM {CATALOGS_TABLE} WHERE catalog_id = ?',
                (int(catalog_id),),
            ),
            'delete catalog row',
        )
        conn.commit()
    finally:
        conn.close()
    return summary
