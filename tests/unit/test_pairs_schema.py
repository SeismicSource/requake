# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for event pairs CSV schema and types.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import os
import sqlite3
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from obspy.core.inventory import Channel, Inventory, Network, Station
from requake.config import config
from requake.database.pairs import PairRecord, read_pairs as read_pairs_from_db
from requake.catalog import RequakeEvent
from requake.database.catalog import write_catalog
from requake.database.db import get_db_path
from requake.database.pairs import write_pair_records as write_pairs


class TestPairsSchema(unittest.TestCase):
    """Test stored event pairs schema and types."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _get_synthetic_pairs_data(self, n_pairs=3):
        """
        Generate synthetic pairs data.

        :param n_pairs: number of pairs to generate
        :type n_pairs: int
        :return: list of pair dictionaries
        :rtype: list
        """
        pairs = []
        for i in range(n_pairs):
            event1 = RequakeEvent(
                evid=f'ev_{i:03d}_a',
                orig_time=UTCDateTime('2020-01-01T00:00:00'),
                lon=10.0 + i * 0.1,
                lat=45.0 + i * 0.1,
                depth=10.0,
                mag_type='Mw',
                mag=4.0,
                trace_id='XX.TEST.00.BHZ',
            )
            event2 = RequakeEvent(
                evid=f'ev_{i:03d}_b',
                orig_time=UTCDateTime('2020-01-01T01:00:00'),
                lon=10.0 + i * 0.1,
                lat=45.0 + i * 0.1,
                depth=10.0,
                mag_type='Mw',
                mag=4.1,
                trace_id='XX.TEST.00.BHZ',
            )
            pairs.append(
                PairRecord(
                    event1,
                    event2,
                    'XX.TEST.00.BHZ',
                    100,
                    0.85,
                    sampling_rate_hz=40.0,
                )
            )
        return pairs

    def _assert_pair_types(self, pair):
        """Assert types and ranges for one RequakeEventPair."""
        self.assertIsInstance(pair.event1.evid, str)
        self.assertIsInstance(pair.event1.orig_time, UTCDateTime)
        self.assertIsInstance(pair.event2.evid, str)
        self.assertIsInstance(pair.event2.orig_time, UTCDateTime)
        self.assertIsInstance(pair.trace_id, str)
        self.assertIsInstance(pair.lag_sec, float)
        self.assertIsInstance(pair.cc_max, float)
        self.assertGreaterEqual(pair.cc_max, -1.0, 'cc_max should be >= -1')
        self.assertLessEqual(pair.cc_max, 1.0, 'cc_max should be <= 1')
        self.assertGreaterEqual(
            pair.lag_sec, 0.0, 'lag_sec should be non-negative')

    def _patch_runtime_config(self):
        """Return a patch that points the global config to a temp database."""
        args = Namespace(outdir=self.test_dir.name)
        return patch.dict(
            config,
            {
                'args': args,
                'outdir': self.test_dir.name,
                'scan_catalog_pairs_file': os.path.join(
                    self.test_dir.name, 'requake.event_pairs.csv'
                ),
            },
            clear=False,
        )

    @staticmethod
    def _seed_catalog_for_pairs(pairs_data):
        """Write catalog rows required by pair foreign-key constraints."""
        catalog_rows = {}
        for pair in pairs_data:
            catalog_rows[pair.event1.evid] = pair.event1
            catalog_rows[pair.event2.evid] = pair.event2
        write_catalog(list(catalog_rows.values()))

    def test_pairs_roundtrip_preserves_fields(self):
        """Stored pairs should preserve the same values when read back."""
        pairs_data = self._get_synthetic_pairs_data(2)

        with self._patch_runtime_config():
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            pairs = list(read_pairs_from_db())

        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0].event1.evid, pairs_data[0].event1.evid)
        self.assertEqual(pairs[0].event2.evid, pairs_data[0].event2.evid)
        self.assertEqual(pairs[0].trace_id, pairs_data[0].trace_id)
        self.assertEqual(pairs[0].lag_samples, pairs_data[0].lag_samples)
        expected_lag_sec = (
            pairs_data[0].lag_samples / pairs_data[0].sampling_rate_hz
        )
        self.assertAlmostEqual(pairs[0].lag_sec, expected_lag_sec)
        self.assertEqual(pairs[0].cc_max, pairs_data[0].cc_max)

    def test_pairs_row_types(self):
        """
        Read a written CSV and assert column types.

        Verify that:
        - evid1/evid2 are strings
        - cc_max is float in [-1, 1]
        - lag_sec is float
        - orig_time1/orig_time2 are valid UTC datetimes
        """
        pairs_data = self._get_synthetic_pairs_data(2)

        with self._patch_runtime_config():
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            pairs = list(read_pairs_from_db())

        self.assertEqual(len(pairs), 2, 'Should have 2 pairs')

        self._assert_pair_types(pairs[0])
        self._assert_pair_types(pairs[1])

    def test_pairs_uniqueness(self):
        """
        Verify no duplicate (evid1, evid2, trace_id) tuples.

        Create pairs with potential duplicates and ensure each unique
        tuple appears only once.
        """
        event1 = RequakeEvent(
            evid='ev_a',
            orig_time=UTCDateTime('2020-01-01T00:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=4.0,
            trace_id='XX.TEST.00.BHZ',
        )
        event2 = RequakeEvent(
            evid='ev_b',
            orig_time=UTCDateTime('2020-01-01T01:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=4.1,
            trace_id='XX.TEST.00.BHZ',
        )
        pairs_data = [
            PairRecord(
                event1,
                event2,
                'XX.TEST.00.BHZ',
                100,
                0.85,
                sampling_rate_hz=40.0,
            ),
            PairRecord(
                event1,
                event2,
                'XX.TEST.00.BHZ',
                100,
                0.86,
                sampling_rate_hz=40.0,
            ),
        ]

        with self._patch_runtime_config():
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            pairs = list(read_pairs_from_db())

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].event1.evid, 'ev_a')
        self.assertEqual(pairs[0].event2.evid, 'ev_b')
        self.assertEqual(pairs[0].cc_max, 0.86)

    def test_pairs_use_compact_schema_and_trace_metadata(self):
        """Stored pairs should use compact columns plus trace metadata."""
        pairs_data = self._get_synthetic_pairs_data(1)

        with self._patch_runtime_config():
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            db_path = get_db_path()

        conn = sqlite3.connect(db_path)
        try:
            pair_columns = {
                row[1]
                for row in conn.execute(
                    'PRAGMA table_info(event_pairs)'
                ).fetchall()
            }
            metadata_columns = {
                row[1]
                for row in conn.execute(
                    'PRAGMA table_info(trace_metadata)'
                ).fetchall()
            }
            metadata_rows = conn.execute(
                'SELECT trace_id, sampling_rate_hz, elevation, local_depth '
                'FROM trace_metadata'
            ).fetchall()
        finally:
            conn.close()

        self.assertIn('lag_samples', pair_columns)
        self.assertIn('cc_x100', pair_columns)
        self.assertNotIn('lag_sec', pair_columns)
        self.assertNotIn('orig_time1', pair_columns)
        self.assertIn('elevation', metadata_columns)
        self.assertIn('local_depth', metadata_columns)
        self.assertEqual(len(metadata_rows), 1)
        self.assertEqual(metadata_rows[0][0], 'XX.TEST.00.BHZ')
        self.assertAlmostEqual(metadata_rows[0][1], 40.0)
        self.assertIsNone(metadata_rows[0][2])
        self.assertIsNone(metadata_rows[0][3])

    def test_trace_metadata_stores_inventory_elevation_and_depth(self):
        """Inventory-backed metadata should persist elevation and depth."""
        pairs_data = self._get_synthetic_pairs_data(1)
        channel = Channel(
            code='BHZ',
            location_code='00',
            latitude=45.0,
            longitude=10.0,
            elevation=321.5,
            depth=12.25,
            sample_rate=40.0,
        )
        channel.start_date = UTCDateTime('2019-01-01T00:00:00')
        station = Station(
            code='TEST',
            latitude=45.0,
            longitude=10.0,
            elevation=321.5,
            channels=[channel],
        )
        inventory = Inventory(
            networks=[Network(code='XX', stations=[station])]
        )

        with self._patch_runtime_config(), patch.dict(
            config, {'inventory': inventory}, clear=False
        ):
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            db_path = get_db_path()

        conn = sqlite3.connect(db_path)
        try:
            metadata_row = conn.execute(
                'SELECT elevation, local_depth FROM trace_metadata'
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(metadata_row[0], 321.5)
        self.assertEqual(metadata_row[1], 12.25)

    def test_pairs_filters_use_encoded_cc_values(self):
        """cc_min/cc_max filters should match reconstructed cc values."""
        base = self._get_synthetic_pairs_data(3)
        pairs_data = [
            base[0]._replace(cc_max=0.841),
            base[1]._replace(cc_max=0.851),
            base[2]._replace(cc_max=0.861),
        ]

        with self._patch_runtime_config():
            self._seed_catalog_for_pairs(pairs_data)
            write_pairs(pairs_data, append=False)
            pairs = list(
                read_pairs_from_db(cc_min=0.851, cc_max=0.861)
            )

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].event1.evid, pairs_data[2].event1.evid)
        self.assertEqual(pairs[0].cc_max, 0.86)

    def test_no_waveform_pairs_without_metadata_do_not_fail_write(self):
        """No-waveform-only traces should not abort metadata persistence."""
        event1 = RequakeEvent(
            evid='ev_nometa_a',
            orig_time=UTCDateTime('2020-01-01T00:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=4.0,
            trace_id='YY.MISS.00.BHZ',
        )
        event2 = RequakeEvent(
            evid='ev_nometa_b',
            orig_time=UTCDateTime('2020-01-01T01:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=4.1,
            trace_id='YY.MISS.00.BHZ',
        )
        pair = PairRecord(
            event1,
            event2,
            'YY.MISS.00.BHZ',
            None,
            None,
            sampling_rate_hz=None,
        )

        with self._patch_runtime_config(), patch.dict(
            config,
            {'inventory': None},
            clear=False,
        ):
            self._seed_catalog_for_pairs([pair])
            # Should not raise PairsMetadataError.
            write_pairs([pair], append=False)
            db_path = get_db_path()

        conn = sqlite3.connect(db_path)
        try:
            metadata_rows = conn.execute(
                'SELECT trace_id FROM trace_metadata '
                "WHERE trace_id = 'YY.MISS.00.BHZ'"
            ).fetchall()
            pair_rows = conn.execute(
                'SELECT lag_samples, cc_x100 FROM event_pairs'
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual(len(pair_rows), 1)
        self.assertIsNone(pair_rows[0][0])
        self.assertIsNone(pair_rows[0][1])
        self.assertEqual(len(metadata_rows), 0)


if __name__ == '__main__':
    unittest.main()
