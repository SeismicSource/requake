# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite connection and schema helpers.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import contextlib
import random
import sqlite3
import time
from ..config.config import config

DB_VERSION = 1
DB_FILENAME = 'requake.sqlite'
BUSY_TIMEOUT_MS = 30000
MAX_RETRIES = 6
RETRY_BASE_DELAY = 0.05
RETRY_MULTIPLIER = 2.0
RETRY_DELAY_CAP = 1.0
RETRY_JITTER = 0.2


class DatabaseBusyError(RuntimeError):
    """Raised when retries for transient SQLite lock errors are exhausted."""


class DatabaseCorruptError(RuntimeError):
    """Raised when the SQLite database file is corrupt or malformed."""


def get_db_path(db_path=None):
    """Return the SQLite path."""
    if db_path is not None:
        return db_path
    args = None
    with contextlib.suppress(KeyError, TypeError):
        args = config['args']
    if args is None:
        args = getattr(config, 'args', None)
    if args is None:
        try:
            args = config.get('args')
        except AttributeError:
            args = None
    outdir = getattr(args, 'outdir', None)
    if not outdir:
        try:
            outdir = config['outdir']
        except (KeyError, TypeError):
            outdir = None
    if not outdir:
        outdir = getattr(config, 'outdir', None)
    if not outdir:
        try:
            outdir = config.get('outdir')
        except AttributeError:
            outdir = None
    if not outdir:
        raise ValueError('Output directory is not configured')
    return os.path.join(outdir, DB_FILENAME)


def check_db_exists(initdb=False, db_path=None):
    """Validate the configured database path for read or init mode."""
    db_path = get_db_path(db_path=db_path)
    if initdb:
        _ensure_parent_dir(db_path)
        return db_path
    if not os.path.exists(db_path):
        raise FileNotFoundError(f'Database file {db_path} not found')
    return db_path


def _ensure_parent_dir(db_path):
    """Create the database parent directory if needed."""
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def set_db_version(cursor):
    """Store the current schema version in the database."""
    cursor.execute(f'PRAGMA user_version = {DB_VERSION}')


def check_db_version(cursor):
    """Validate that the on-disk schema version is supported."""
    version = cursor.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, DB_VERSION):
        raise RuntimeError(
            f'Unsupported database schema version: {version}'
        )


def initialize_database(cursor):
    """Initialize a new database with the supported version marker."""
    set_db_version(cursor)


def _configure_connection(conn):
    """Configure connection pragmas for integrity and concurrency."""
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute(f'PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA journal_mode = WAL')


def _is_retryable_sqlite_error(err):
    """Return True when sqlite error is transient and retryable."""
    message = str(err).lower()
    return (
        'database is locked' in message
        or 'database is busy' in message
        or 'database table is locked' in message
    )


def execute_with_retry(operation, operation_name):
    """Run a sqlite operation with retries on transient lock errors."""
    delay = RETRY_BASE_DELAY
    start = time.time()
    attempt = 0
    while True:
        try:
            return operation()
        except sqlite3.OperationalError as err:
            if not _is_retryable_sqlite_error(err):
                raise
            if attempt >= MAX_RETRIES:
                elapsed = time.time() - start
                raise DatabaseBusyError(
                    f'Operation "{operation_name}" failed after '
                    f'{attempt + 1} attempts in {elapsed:.2f}s: {err}'
                ) from err
            jitter = random.uniform(1.0 - RETRY_JITTER, 1.0 + RETRY_JITTER)
            time.sleep(min(delay, RETRY_DELAY_CAP) * jitter)
            delay *= RETRY_MULTIPLIER
            attempt += 1


def initialize_database_if_needed(db_path=None):
    """Initialize database schema version and pragmas if missing."""
    conn = get_db_connection(initdb=True, db_path=db_path)
    conn.close()


def get_db_connection(initdb=False, db_path=None):
    """Open a SQLite connection for the configured database file."""
    db_path = check_db_exists(initdb=initdb, db_path=db_path)
    conn = sqlite3.connect(db_path)
    _configure_connection(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if initdb:
        initialize_database(cursor)
        conn.commit()
    check_db_version(cursor)
    return conn
