# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for prefetch claims and concurrent cache writes.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sqlite3
import tempfile
import threading
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from obspy import UTCDateTime

from requake.config import config
from requake.wfcache import storage as storage_mod

MISSING = object()
TRACE_ID = 'IV.ATFO..HHZ'
START = UTCDateTime('2020-01-01T00:00:00')
END = UTCDateTime('2020-01-01T01:00:00')


class _ConnectionPool:
    """Hand each thread its own connection to the same cache file."""

    def __init__(self, path):
        self.path = str(path)
        self._local = threading.local()
        self._connections = []

    def get(self):
        """Return the calling thread's connection, creating it if needed."""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            # check_same_thread=False only so that close() can run in the
            # main thread; each connection is still used by one thread.
            conn = sqlite3.connect(
                self.path, timeout=30.0, check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=30000')
            conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn = conn
            self._connections.append(conn)
        return conn

    def close(self):
        """Close every connection opened by the pool."""
        for conn in self._connections:
            conn.close()
        self._connections = []


class TestPrefetchClaims(unittest.TestCase):
    """Validate claim acquisition, leases and crash recovery."""

    def setUp(self):
        """Point the cache at a temporary directory."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_args = config.get('args', MISSING)
        config['args'] = Namespace(outdir=self.tmpdir.name)
        self.cache_path = Path(self.tmpdir.name) / 'waveform_cache.sqlite'
        # Create the schema now, before tests wrap the module.
        storage_mod._close_cached_connection()  # noqa: SLF001
        storage_mod._get_cache_connection(  # noqa: SLF001
            self.cache_path
        )

    def tearDown(self):
        """Restore the config and close cached connections."""
        storage_mod._close_cached_connection()  # noqa: SLF001
        if self.original_args is MISSING:
            config.pop('args', None)
        else:
            config['args'] = self.original_args

    def _set_owner(self, owner):
        """Return a patch making this thread claim as *owner*."""
        return patch.object(
            storage_mod,
            '_claim_owner_token',
            lambda: owner,
        )

    def _expire_all_claims(self):
        """Move every claim expiry into the past."""
        conn = storage_mod._get_cache_connection(  # noqa: SLF001
            self.cache_path
        )
        conn.execute(
            'UPDATE prefetch_claims SET expires_at_ns = 0'
        )
        conn.commit()

    def test_claim_is_exclusive(self):
        """A group already claimed cannot be claimed again."""
        with self._set_owner('owner-a'):
            self.assertTrue(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
        with self._set_owner('owner-b'):
            self.assertFalse(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
        self.assertEqual(len(storage_mod.list_prefetch_claims()), 1)

    def test_expired_claim_can_be_taken_over(self):
        """A claim left by a crashed process is taken over."""
        with self._set_owner('dead-owner'):
            storage_mod.claim_prefetch_group(
                TRACE_ID, START, END, ttl_s=60
            )
        self._expire_all_claims()
        with self._set_owner('owner-b'):
            self.assertTrue(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
        claims = storage_mod.list_prefetch_claims()
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['owner'], 'owner-b')

    def test_release_and_renew_respect_ownership(self):
        """Only the owning process can renew or release a claim."""
        with self._set_owner('owner-a'):
            storage_mod.claim_prefetch_group(
                TRACE_ID, START, END, ttl_s=60
            )
        with self._set_owner('owner-b'):
            self.assertFalse(
                storage_mod.renew_prefetch_claim(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
            storage_mod.release_prefetch_claim(TRACE_ID, START, END)
        self.assertEqual(len(storage_mod.list_prefetch_claims()), 1)
        with self._set_owner('owner-a'):
            self.assertTrue(
                storage_mod.renew_prefetch_claim(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
            storage_mod.release_prefetch_claim(TRACE_ID, START, END)
        self.assertEqual(storage_mod.list_prefetch_claims(), [])

    def test_reclaiming_own_group_renews_lease(self):
        """Re-claiming a group already owned by us succeeds."""
        with self._set_owner('owner-a'):
            self.assertTrue(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
            self.assertTrue(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
        self.assertEqual(len(storage_mod.list_prefetch_claims()), 1)

    def test_concurrent_claim_exactly_one_winner(self):
        """Two threads claiming the same group: only one wins."""
        pool = _ConnectionPool(self.cache_path)
        self.addCleanup(pool.close)
        owners = threading.local()
        barrier = threading.Barrier(2)
        results = {}
        errors = []

        def worker(name):
            owners.value = name
            barrier.wait()
            try:
                results[name] = storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            except Exception as err:  # pylint: disable=broad-except
                errors.append(err)

        def owner():
            return owners.value

        with patch.object(
            storage_mod, '_claim_owner_token', owner
        ), patch.object(
            storage_mod, '_get_cache_connection',
            lambda _path: pool.get(),
        ):
            first = threading.Thread(target=worker, args=('owner-a',))
            second = threading.Thread(target=worker, args=('owner-b',))
            first.start()
            second.start()
            first.join()
            second.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(results.values()), [False, True])
        self.assertEqual(len(storage_mod.list_prefetch_claims()), 1)

    def test_clear_claims_removes_everything(self):
        """clear_prefetch_claims() empties the table."""
        with self._set_owner('owner-a'):
            storage_mod.claim_prefetch_group(
                TRACE_ID, START, END, ttl_s=60
            )
        self.assertEqual(storage_mod.clear_prefetch_claims(), 1)
        self.assertEqual(storage_mod.list_prefetch_claims(), [])

    def test_summary_reports_claim_state(self):
        """The cache summary exposes active claims and their owners."""
        with self._set_owner('owner-a'):
            storage_mod.claim_prefetch_group(
                TRACE_ID, START, END, ttl_s=60
            )
        summary = storage_mod.read_waveform_cache_summary()
        self.assertEqual(summary['claim_rows'], 1)
        self.assertEqual(summary['claim_active_rows'], 1)
        self.assertEqual(summary['claim_expired_rows'], 0)
        self.assertEqual(summary['claim_owners'][0]['owner'], 'owner-a')

    def test_claims_are_trivial_without_disk_cache(self):
        """With the disk cache disabled there is nothing to coordinate."""
        original = config.get(
            'catalog_waveform_disk_cache_enabled', True
        )
        config['catalog_waveform_disk_cache_enabled'] = False
        try:
            self.assertTrue(
                storage_mod.claim_prefetch_group(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
            self.assertTrue(
                storage_mod.renew_prefetch_claim(
                    TRACE_ID, START, END, ttl_s=60
                )
            )
        finally:
            config['catalog_waveform_disk_cache_enabled'] = original


class TestLazyMigration(unittest.TestCase):
    """Validate that old cache files gain the claims table in place."""

    def setUp(self):
        """Create a cache file with the pre-claims schema."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_args = config.get('args', MISSING)
        config['args'] = Namespace(outdir=self.tmpdir.name)
        self.cache_path = Path(self.tmpdir.name) / 'waveform_cache.sqlite'
        conn = sqlite3.connect(str(self.cache_path))
        old_schema = [
            statement for statement in storage_mod.WAVEFORM_CACHE_SCHEMA
            if 'prefetch_claims' not in statement
        ]
        for statement in old_schema:
            conn.execute(statement)
        conn.execute('PRAGMA user_version=1')
        conn.execute(
            '''
            INSERT INTO waveform_cache VALUES (
                'ev1', 'IV.ATFO..HHZ', 1, 2, 100.0, 10, X'00', 3, 4
            )
            '''
        )
        conn.execute(
            '''
            INSERT INTO waveform_failures VALUES (
                'ev2', 'IV.ATFO..HHZ', 1, 2, 2, 3, 'boom', 5, 6, NULL
            )
            '''
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        """Restore the config and close cached connections."""
        storage_mod._close_cached_connection()  # noqa: SLF001
        if self.original_args is MISSING:
            config.pop('args', None)
        else:
            config['args'] = self.original_args

    def test_existing_cache_gains_claims_table(self):
        """Opening an old cache adds the table, keeping version and rows."""
        conn = storage_mod._get_cache_connection(  # noqa: SLF001
            self.cache_path
        )
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertIn('prefetch_claims', tables)
        self.assertEqual(
            int(conn.execute('PRAGMA user_version').fetchone()[0]), 1
        )
        self.assertEqual(
            int(conn.execute(
                'SELECT COUNT(*) FROM waveform_cache'
            ).fetchone()[0]),
            1,
        )
        self.assertEqual(
            int(conn.execute(
                'SELECT COUNT(*) FROM waveform_failures'
            ).fetchone()[0]),
            1,
        )


class TestFailureCacheWrites(unittest.TestCase):
    """Validate atomic failure-cache updates."""

    def setUp(self):
        """Point the cache at a temporary directory."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_args = config.get('args', MISSING)
        self.original_limits = storage_mod._FAILURE_LIMITS  # noqa: SLF001
        config['args'] = Namespace(outdir=self.tmpdir.name)
        storage_mod._FAILURE_LIMITS = (3, 600.0)  # noqa: SLF001
        self.cache_path = Path(self.tmpdir.name) / 'waveform_cache.sqlite'

    def tearDown(self):
        """Restore the config and close cached connections."""
        storage_mod._FAILURE_LIMITS = self.original_limits  # noqa: SLF001
        storage_mod._close_cached_connection()  # noqa: SLF001
        if self.original_args is MISSING:
            config.pop('args', None)
        else:
            config['args'] = self.original_args

    def _failure_row(self):
        conn = storage_mod._get_cache_connection(  # noqa: SLF001
            self.cache_path
        )
        return conn.execute(
            'SELECT retry_count, first_failure_ns FROM waveform_failures'
        ).fetchone()

    def test_failures_increment_without_losing_history(self):
        """Each failure increments the count and keeps the first failure."""
        storage_mod.register_waveform_failure(
            'ev1', TRACE_ID, START, END, 'boom'
        )
        first = self._failure_row()
        storage_mod.register_waveform_failure(
            'ev1', TRACE_ID, START, END, 'boom again'
        )
        second = self._failure_row()
        self.assertEqual(int(first['retry_count']), 1)
        self.assertEqual(int(second['retry_count']), 2)
        self.assertEqual(
            int(first['first_failure_ns']),
            int(second['first_failure_ns']),
        )

    def test_clear_failure_inside_batch_defers_commit(self):
        """Failure rows are cleared in the enclosing batch transaction."""
        storage_mod.register_waveform_failure(
            'ev1', TRACE_ID, START, END, 'boom'
        )
        storage_mod.begin_cache_write_batch()
        try:
            storage_mod.clear_waveform_failure(
                'ev1', TRACE_ID, START, END
            )
        finally:
            storage_mod.commit_cache_write_batch()
        self.assertIsNone(self._failure_row())


if __name__ == '__main__':
    unittest.main()
