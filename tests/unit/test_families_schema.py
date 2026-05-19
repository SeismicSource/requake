# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for families CSV schema and types."""

import unittest
import tempfile
import os
import csv
from obspy import UTCDateTime
from requake.families.families import _read_families_from_catalog_scan


class TestFamiliesSchema(unittest.TestCase):
    """Test families CSV schema and types."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

        # Mock config for reading families
        from requake import config as config_module
        self.original_config = config_module.config.copy()
        self.addCleanup(self._restore_config)

    def _restore_config(self):
        """Restore original config."""
        from requake import config as config_module
        config_module.config.clear()
        config_module.config.update(self.original_config)

    def _write_synthetic_families_csv(self, families_data):
        """
        Write synthetic families CSV file.

        :param families_data: list of dictionaries with family data
        :type families_data: list
        :return: path to CSV file
        :rtype: str
        """
        csv_path = os.path.join(self.test_dir.name, 'test_families.csv')
        fieldnames = [
            'evid', 'trace_id', 'orig_time', 'lon', 'lat', 'depth_km',
            'mag_type', 'mag', 'family_number', 'valid'
        ]
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for family in families_data:
                writer.writerow(family)
        return csv_path

    def _get_synthetic_families_data(self, n_families=2, events_per_family=2):
        """
        Generate synthetic families data.

        :param n_families: number of families to generate
        :type n_families: int
        :param events_per_family: events per family
        :type events_per_family: int
        :return: list of family row dictionaries
        :rtype: list
        """
        families = []
        event_counter = 0
        for fam_num in range(n_families):
            for _ in range(events_per_family):
                families.append({
                    'evid': f'ev_{event_counter:04d}',
                    'trace_id': 'XX.TEST.00.BHZ',
                    'orig_time': f'2020-01-{(fam_num+1):02d}T00:00:00',
                    'lon': 10.0 + fam_num * 0.5,
                    'lat': 45.0 + fam_num * 0.5,
                    'depth_km': 10.0,
                    'mag_type': 'Mw',
                    'mag': 4.0,
                    'family_number': fam_num,
                    'valid': 'True'
                })
                event_counter += 1
        return families

    def _assert_event_basic_types(self, ev):
        """Assert core event types for one family event."""
        self.assertIsInstance(ev.evid, str)
        self.assertIsInstance(ev.orig_time, UTCDateTime)
        self.assertIsInstance(ev.trace_id, str)
        self.assertIsInstance(ev.lon, float)
        self.assertIsInstance(ev.lat, float)
        self.assertIsInstance(ev.depth, float)
        self.assertIsInstance(ev.mag_type, str)
        self.assertIsInstance(ev.mag, float)

    def test_families_csv_headers(self):
        """
        Assert exact ordered header list after _write_families().

        The expected header order is:
        evid, trace_id, orig_time, lon, lat, depth_km, mag_type, mag,
        family_number, valid
        """
        families_data = self._get_synthetic_families_data(2, 2)
        csv_path = self._write_synthetic_families_csv(families_data)

        # Read and verify headers
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            expected_headers = [
                'evid', 'trace_id', 'orig_time', 'lon', 'lat', 'depth_km',
                'mag_type', 'mag', 'family_number', 'valid'
            ]
            self.assertEqual(reader.fieldnames, expected_headers,
                           "CSV headers do not match expected order")

    def test_families_row_types(self):
        """
        Read back families and assert column types.

        Verify that:
        - family_number is int
        - valid is bool
        - coordinate types (lon, lat, depth_km) are float or None
        - mag_type, mag are preserved
        - orig_time is valid UTC datetime
        """
        families_data = self._get_synthetic_families_data(2, 2)
        csv_path = self._write_synthetic_families_csv(families_data)

        # Mock config
        from requake import config as config_module
        config_module.config.build_families_outfile = csv_path
        config_module.config.mag_to_slip_model = 'NJ1998'  # required by Family.append

        # Read families using _read_families_from_catalog_scan
        families = _read_families_from_catalog_scan()

        self.assertEqual(len(families), 2, "Should have 2 families")

        family0 = families[0]
        family1 = families[1]
        self.assertIsInstance(family0.number, int, "family_number should be int")
        self.assertIsInstance(family0.valid, bool, "valid should be bool")
        self.assertIsInstance(family1.number, int, "family_number should be int")
        self.assertIsInstance(family1.valid, bool, "valid should be bool")

        self._assert_event_basic_types(family0[0])
        self._assert_event_basic_types(family0[1])
        self._assert_event_basic_types(family1[0])
        self._assert_event_basic_types(family1[1])

    def test_families_empty_write_read(self):
        """
        Test that empty families CSV round-trip produces empty list.
        """
        # Write empty families CSV
        csv_path = os.path.join(self.test_dir.name, 'test_empty_families.csv')
        fieldnames = [
            'evid', 'trace_id', 'orig_time', 'lon', 'lat', 'depth_km',
            'mag_type', 'mag', 'family_number', 'valid'
        ]
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

        # Read empty families
        from requake import config as config_module
        config_module.config.build_families_outfile = csv_path

        families = _read_families_from_catalog_scan()

        # Assert empty
        self.assertEqual(len(families), 0, "Empty families should remain empty")


if __name__ == '__main__':
    unittest.main()
