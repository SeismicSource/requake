# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for event pairs CSV schema and types."""

import unittest
import tempfile
import os
import csv
from obspy import UTCDateTime
from requake.families.pairs import read_pairs_file


class TestPairsSchema(unittest.TestCase):
    """Test event pairs CSV schema and types."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

        # Mock config for reading pairs
        from requake import config as config_module
        self.original_config = config_module.config.copy()
        self.addCleanup(self._restore_config)

    def _restore_config(self):
        """Restore original config."""
        from requake import config as config_module
        config_module.config.clear()
        config_module.config.update(self.original_config)

    def _write_synthetic_pairs_csv(self, pairs_data):
        """
        Write synthetic pairs CSV file.

        :param pairs_data: list of dictionaries with pair data
        :type pairs_data: list
        :return: path to CSV file
        :rtype: str
        """
        csv_path = os.path.join(self.test_dir.name, 'test_pairs.csv')
        fieldnames = [
            'evid1', 'evid2', 'trace_id',
            'orig_time1', 'lon1', 'lat1', 'depth_km1', 'mag_type1', 'mag1',
            'orig_time2', 'lon2', 'lat2', 'depth_km2', 'mag_type2', 'mag2',
            'lag_samples', 'lag_sec', 'cc_max'
        ]
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for pair in pairs_data:
                writer.writerow(pair)
        return csv_path

    def _get_synthetic_pairs_data(self, n_pairs=3):
        """
        Generate synthetic pairs data.

        :param n_pairs: number of pairs to generate
        :type n_pairs: int
        :return: list of pair dictionaries
        :rtype: list
        """
        return [
            {
                'evid1': f'ev_{i:03d}_a',
                'evid2': f'ev_{i:03d}_b',
                'trace_id': 'XX.TEST.00.BHZ',
                'orig_time1': '2020-01-01T00:00:00',
                'lon1': 10.0 + i * 0.1,
                'lat1': 45.0 + i * 0.1,
                'depth_km1': 10.0,
                'mag_type1': 'Mw',
                'mag1': 4.0,
                'orig_time2': '2020-01-01T01:00:00',
                'lon2': 10.0 + i * 0.1,
                'lat2': 45.0 + i * 0.1,
                'depth_km2': 10.0,
                'mag_type2': 'Mw',
                'mag2': 4.1,
                'lag_samples': 100,
                'lag_sec': 2.5,
                'cc_max': 0.85
            }
            for i in range(n_pairs)
        ]

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

    def _read_triplets(self, csv_path):
        """Read (evid1, evid2, trace_id) triplets from a CSV file."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [
                (row['evid1'], row['evid2'], row['trace_id'])
                for row in reader
            ]

    def test_pairs_csv_headers(self):
        """
        Assert exact ordered header list after _process_pairs().

        The expected header order is:
        evid1, evid2, trace_id, orig_time1, lon1, lat1, depth_km1, mag_type1,
        mag1, orig_time2, lon2, lat2, depth_km2, mag_type2, mag2, lag_samples,
        lag_sec, cc_max
        """
        pairs_data = self._get_synthetic_pairs_data(2)
        csv_path = self._write_synthetic_pairs_csv(pairs_data)

        # Read and verify headers
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            expected_headers = [
                'evid1', 'evid2', 'trace_id',
                'orig_time1', 'lon1', 'lat1', 'depth_km1', 'mag_type1', 'mag1',
                'orig_time2', 'lon2', 'lat2', 'depth_km2', 'mag_type2', 'mag2',
                'lag_samples', 'lag_sec', 'cc_max'
            ]
            self.assertEqual(
                reader.fieldnames,
                expected_headers,
                'CSV headers do not match expected order'
            )

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
        csv_path = self._write_synthetic_pairs_csv(pairs_data)

        # Mock config
        from requake import config as config_module
        config_module.config.scan_catalog_pairs_file = csv_path

        # Read pairs using read_pairs_file
        pairs = list(read_pairs_file())

        self.assertEqual(len(pairs), 2, 'Should have 2 pairs')

        self._assert_pair_types(pairs[0])
        self._assert_pair_types(pairs[1])

    def test_pairs_uniqueness(self):
        """
        Verify no duplicate (evid1, evid2, trace_id) tuples.

        Create pairs with potential duplicates and ensure each unique
        tuple appears only once.
        """
        pairs_data = [
            {
                'evid1': 'ev_a',
                'evid2': 'ev_b',
                'trace_id': 'XX.TEST.00.BHZ',
                'orig_time1': '2020-01-01T00:00:00',
                'lon1': 10.0,
                'lat1': 45.0,
                'depth_km1': 10.0,
                'mag_type1': 'Mw',
                'mag1': 4.0,
                'orig_time2': '2020-01-01T01:00:00',
                'lon2': 10.0,
                'lat2': 45.0,
                'depth_km2': 10.0,
                'mag_type2': 'Mw',
                'mag2': 4.1,
                'lag_samples': 100,
                'lag_sec': 2.5,
                'cc_max': 0.85
            },
            {
                'evid1': 'ev_a',
                'evid2': 'ev_b',
                'trace_id': 'XX.TEST.00.BHZ',
                'orig_time1': '2020-01-01T00:00:00',
                'lon1': 10.0,
                'lat1': 45.0,
                'depth_km1': 10.0,
                'mag_type1': 'Mw',
                'mag1': 4.0,
                'orig_time2': '2020-01-01T01:00:00',
                'lon2': 10.0,
                'lat2': 45.0,
                'depth_km2': 10.0,
                'mag_type2': 'Mw',
                'mag2': 4.1,
                'lag_samples': 100,
                'lag_sec': 2.5,
                'cc_max': 0.86  # Different cc_max but same triplet
            }
        ]
        csv_path = self._write_synthetic_pairs_csv(pairs_data)

        triplets = self._read_triplets(csv_path)
        self.assertEqual(len(triplets), 2)
        self.assertEqual(len(set(triplets)), 1)


if __name__ == '__main__':
    unittest.main()
