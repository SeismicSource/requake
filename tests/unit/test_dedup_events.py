# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the ``dedup_events`` command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import sqlite3
import importlib
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.config import config
from requake.catalog import RequakeEvent
from requake.database.catalog import read_catalog as read_catalog_from_db
from requake.database.catalog import write_catalog
from requake.database.db import get_db_path
from requake.database.families import read_families
from requake.database.pairs import (
    PairRecord, read_pairs as read_pairs_from_db,
    write_pair_records as write_pairs,
)
from requake.families import build_families
from requake.families.dedup_events import dedup_events
from requake.families.pairs import read_events_from_pairs


dedup_module = importlib.import_module(
    'requake.families.dedup_events'
)


class TestDedupEvents(unittest.TestCase):
    """Test duplicate-event detection and flagging."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    @staticmethod
    def _events():
        """Return a catalog with two duplicates and one unrelated event."""
        orig_time = UTCDateTime('2020-01-01T00:00:00')
        return {
            'ev_a': RequakeEvent(
                evid='ev_a', orig_time=orig_time,
                lon=10.0, lat=45.0, depth=10.0,
                mag_type='Mw', mag=3.0, trace_id='XX.TEST.00.BHZ',
            ),
            'ev_b': RequakeEvent(
                evid='ev_b', orig_time=orig_time + 5,
                lon=10.0001, lat=45.0001, depth=10.0,
                mag_type='Mw', mag=3.2, trace_id='XX.TEST.00.BHZ',
            ),
            'ev_c': RequakeEvent(
                evid='ev_c', orig_time=orig_time + 600,
                lon=10.5, lat=45.5, depth=10.0,
                mag_type='Mw', mag=3.1, trace_id='XX.TEST.00.BHZ',
            ),
        }

    def _seed_db(self, events):
        """Write catalog and event pairs into the temporary database."""
        write_catalog(list(events.values()))
        trace_id = 'XX.TEST.00.BHZ'
        other_trace_id = 'YY.TEST.00.BHZ'
        write_pairs(
            [
                # duplicate pair, on two traces
                PairRecord(
                    events['ev_a'], events['ev_b'], trace_id,
                    100, 0.994, sampling_rate_hz=40.0,
                ),
                PairRecord(
                    events['ev_a'], events['ev_b'], other_trace_id,
                    100, 0.995, sampling_rate_hz=20.0,
                ),
                # high cc, but far in time
                PairRecord(
                    events['ev_a'], events['ev_c'], trace_id,
                    100, 0.99, sampling_rate_hz=40.0,
                ),
                # high cc, but far in space
                PairRecord(
                    events['ev_b'], events['ev_c'], trace_id,
                    100, 0.99, sampling_rate_hz=40.0,
                ),
            ],
            append=False,
        )

    def _patch_config(self, dry_run=False):
        """Patch the global config for the temporary database."""
        args = Namespace(
            outdir=self.test_dir.name,
            cc_min=0.98,
            max_time_diff=60.,
            max_distance=2.,
            dry_run=dry_run,
        )
        return patch.dict(
            config,
            {
                'args': args,
                'outdir': self.test_dir.name,
                'clustering_algorithm': 'shared',
                'cc_min': 0.95,
                'sort_families_by': 'time',
                'distance_from_lon': None,
                'distance_from_lat': None,
                'mag_to_slip_model': 'NJ1998',
            },
            clear=False,
        )

    def _duplicate_flags(self):
        """Return the catalog duplicate flags as a dict."""
        catalog = read_catalog_from_db()
        return {event.evid: bool(event.duplicate) for event in catalog}

    def _invalid_pair_count(self):
        """Return the number of invalid pairs stored in the database."""
        conn = sqlite3.connect(get_db_path())
        try:
            row = conn.execute(
                'SELECT COUNT(*) FROM event_pairs WHERE invalid = 1'
            ).fetchone()
        finally:
            conn.close()
        return row[0]

    def _run_dedup(self):
        """Run dedup_events() with a patched logger."""
        with patch.object(dedup_module, 'logger'):
            dedup_events()

    def test_dedup_events_keeps_highest_magnitude(self):
        """The lowest-magnitude event of a close pair is flagged."""
        events = self._events()
        with self._patch_config():
            self._seed_db(events)
            self._run_dedup()
            flags = self._duplicate_flags()
            remaining = list(read_pairs_from_db())
            n_invalid = self._invalid_pair_count()

        self.assertTrue(flags['ev_a'])
        self.assertFalse(flags['ev_b'])
        self.assertFalse(flags['ev_c'])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(
            {remaining[0].event1.evid, remaining[0].event2.evid},
            {'ev_b', 'ev_c'},
        )
        self.assertEqual(n_invalid, 3)

    def test_dedup_events_dry_run(self):
        """A dry run must not modify the database."""
        events = self._events()
        with self._patch_config(dry_run=True):
            self._seed_db(events)
            self._run_dedup()
            flags = self._duplicate_flags()
            n_invalid = self._invalid_pair_count()
            remaining = list(read_pairs_from_db())

        self.assertFalse(any(flags.values()))
        self.assertEqual(n_invalid, 0)
        self.assertEqual(len(remaining), 4)

    def test_build_families_ignores_invalid_pairs(self):
        """Families must not include duplicated (invalid) events."""
        events = self._events()
        with self._patch_config():
            self._seed_db(events)
            self._run_dedup()
            build_families()
            stored_families = read_families()
            family_evids = {
                event.evid
                for family in stored_families
                for event in family
            }
            pair_evids = set(read_events_from_pairs())

        self.assertEqual(family_evids, {'ev_b', 'ev_c'})
        self.assertNotIn('ev_a', pair_evids)
        self.assertIn('ev_b', pair_evids)

    def test_dedup_events_is_idempotent(self):
        """A second run must not flag additional pairs as invalid."""
        events = self._events()
        with self._patch_config():
            self._seed_db(events)
            self._run_dedup()
            first = self._invalid_pair_count()
            self._run_dedup()
            second = self._invalid_pair_count()

        self.assertEqual(first, second)
        self.assertEqual(second, 3)

    def test_schema_exposes_new_flags(self):
        """The catalog and event_pairs tables must expose the new flags."""
        events = self._events()
        with self._patch_config():
            self._seed_db(events)
            db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        try:
            catalog_columns = {
                row[1]
                for row in conn.execute('PRAGMA table_info(catalog)')
            }
            pair_columns = {
                row[1]
                for row in conn.execute('PRAGMA table_info(event_pairs)')
            }
        finally:
            conn.close()
        self.assertIn('duplicate', catalog_columns)
        self.assertIn('invalid', pair_columns)


if __name__ == '__main__':
    unittest.main()
