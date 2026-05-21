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
import sqlite3

DB_VERSION = 1
DB_FILENAME = 'requake.sqlite'


def get_db_path(config, db_path=None):
    """Return the SQLite path."""
    if db_path is not None:
        return db_path
    outdir = getattr(config, 'outdir', None) or getattr(
        getattr(config, 'args', None), 'outdir', None
    )
    if not outdir:
        raise ValueError('Output directory is not configured')
    return os.path.join(outdir, DB_FILENAME)


def check_db_exists(config, initdb=False, db_path=None):
    """Validate the configured database path for read or init mode."""
    db_path = get_db_path(config, db_path=db_path)
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


def get_db_connection(config, initdb=False, db_path=None):
    """Open a SQLite connection for the configured database file."""
    db_path = check_db_exists(config, initdb=initdb, db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if initdb:
        initialize_database(cursor)
        conn.commit()
    check_db_version(cursor)
    return conn
