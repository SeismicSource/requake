# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for SQLite database helper utilities.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import os
import sqlite3
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

from obspy import UTCDateTime

from requake.catalog import RequakeEvent
from requake.config.config import config
from requake.database.catalog import read_catalog, write_catalog
from requake.database.db import (
    check_db_exists,
    check_db_version,
    execute_with_retry,
    get_db_connection,
    get_db_path,
    set_db_version,
)
from requake.database.pairs import DatabaseCorruptError, read_pairs


class TestDatabaseDbHelpers(unittest.TestCase):
    """Test SQLite helper functions in requake.database.db."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _patch_runtime_config(self):
        """Return a patch that points the global config to a temp database."""
        args = Namespace(outdir=self.test_dir.name)
        return patch.dict(
            config,
            {
                'args': args,
                'outdir': self.test_dir.name,
            },
            clear=False,
        )

    def test_get_db_path_uses_outdir(self):
        """Database path should be resolved under configured outdir."""
        with self._patch_runtime_config():
            db_path = get_db_path()
        self.assertTrue(db_path.startswith(self.test_dir.name))
        self.assertTrue(db_path.endswith('requake.sqlite'))

    def test_check_db_exists_init_and_runtime(self):
        """Init mode creates parent dir, runtime mode requires db file."""
        with self._patch_runtime_config():
            db_path = check_db_exists(initdb=True)
            self.assertEqual(db_path, get_db_path())
            self.assertTrue(os.path.isdir(os.path.dirname(db_path)))

            with self.assertRaises(FileNotFoundError):
                check_db_exists(initdb=False)

            conn = sqlite3.connect(db_path)
            conn.close()
            self.assertEqual(check_db_exists(initdb=False), db_path)

    def test_db_version_check(self):
        """Version checker should accept current version and reject others."""
        with self._patch_runtime_config():
            db_path = check_db_exists(initdb=True)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            set_db_version(cursor)
            conn.commit()
            check_db_version(cursor)

            cursor.execute('PRAGMA user_version = 999')
            conn.commit()
            with self.assertRaises(RuntimeError):
                check_db_version(cursor)
            conn.close()

    def test_get_db_connection_enables_foreign_keys(self):
        """Connections should enforce foreign keys via pragma."""
        with self._patch_runtime_config():
            conn = get_db_connection(initdb=True)
            try:
                cursor = conn.cursor()
                cursor.execute('PRAGMA foreign_keys')
                row = cursor.fetchone()
                self.assertEqual(row[0], 1)
            finally:
                conn.close()

    def test_execute_with_retry_non_retryable_error(self):
        """Non-retryable sqlite errors should surface immediately."""

        def operation():
            raise sqlite3.OperationalError('no such table: missing')

        with self.assertRaises(sqlite3.OperationalError):
            execute_with_retry(operation, 'non-retryable op')

    def test_parameterized_queries_for_runtime_values(self):
        """Runtime SQL values must not alter schema."""
        event = RequakeEvent(
            evid="ev_1'; DROP TABLE catalog; --",
            trace_id='XX.TEST.00.BHZ',
            orig_time=UTCDateTime('2020-01-01T00:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=4.0,
        )

        with self._patch_runtime_config():
            write_catalog([event])
            catalog = read_catalog()
            self.assertEqual(catalog[0].evid, event.evid)

    def test_read_pairs_raises_corruption_error(self):
        """Malformed pairs databases should raise a dedicated error."""

        class _FakeCursor:
            def execute(self, *args, **kwargs):
                raise sqlite3.DatabaseError(
                    'database disk image is malformed'
                )

        class _FakeConnection:
            def cursor(self):
                return _FakeCursor()

            def close(self):
                return None

        with self._patch_runtime_config():
            with patch(
                'requake.database.pairs.get_db_connection',
                return_value=_FakeConnection(),
            ):
                with self.assertRaises(DatabaseCorruptError) as ctx:
                    read_pairs()
        self.assertIn("sqlite3 requake.sqlite '.recover'", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
