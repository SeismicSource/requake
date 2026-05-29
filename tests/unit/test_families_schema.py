# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for families CSV schema and types.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import os
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.catalog import write_catalog
from requake.database.families import write_families
from requake.families.families import Family, _read_families_from_catalog_scan


class TestFamiliesSchema(unittest.TestCase):
    """Test stored families schema and types."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _get_synthetic_families_data(self, n_families=2, events_per_family=2):
        """
        Generate synthetic Family objects.

        :param n_families: number of families to generate
        :type n_families: int
        :param events_per_family: events per family
        :type events_per_family: int
        :return: list of Family objects
        :rtype: list
        """
        families = []
        event_counter = 0
        for fam_num in range(n_families):
            family = Family(fam_num)
            family.valid = True
            for _ in range(events_per_family):
                family.append(RequakeEvent(
                    evid=f'ev_{event_counter:04d}',
                    trace_id='XX.TEST.00.BHZ',
                    orig_time=UTCDateTime(
                        f'2020-01-{(fam_num + 1):02d}T00:00:00'
                    ),
                    lon=10.0 + fam_num * 0.5,
                    lat=45.0 + fam_num * 0.5,
                    depth=10.0,
                    mag_type='Mw',
                    mag=4.0,
                ))
                event_counter += 1
            families.append(family)
        return families

    def _patch_runtime_config(self):
        """Return a patch that points the global config to a temp database."""
        args = Namespace(outdir=self.test_dir.name)
        return patch.dict(
            config,
            {
                'args': args,
                'outdir': self.test_dir.name,
                'build_families_outfile': os.path.join(
                    self.test_dir.name, 'requake.event_families.csv'
                ),
                'mag_to_slip_model': 'NJ1998',
            },
            clear=False,
        )

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

    @staticmethod
    def _seed_catalog_for_families(families_data):
        """Write catalog rows required by family foreign-key constraints."""
        write_catalog(
            [event for family in families_data for event in family],
        )

    def test_families_roundtrip_preserves_fields(self):
        """Stored families should preserve values when read back."""
        with self._patch_runtime_config():
            families_data = self._get_synthetic_families_data(2, 2)
            self._seed_catalog_for_families(families_data)
            write_families(families_data)
            families = _read_families_from_catalog_scan()

        self.assertEqual(len(families), 2)
        self.assertEqual(families[0].number, families_data[0].number)
        self.assertEqual(families[0][0].evid, families_data[0][0].evid)
        self.assertEqual(families[0][0].trace_id, families_data[0][0].trace_id)
        self.assertEqual(families[0][0].mag, families_data[0][0].mag)

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
        with self._patch_runtime_config():
            families_data = self._get_synthetic_families_data(2, 2)
            self._seed_catalog_for_families(families_data)
            write_families(families_data)
            families = _read_families_from_catalog_scan()

        self.assertEqual(len(families), 2, 'Should have 2 families')

        family0 = families[0]
        family1 = families[1]
        self.assertIsInstance(
            family0.number, int, 'family_number should be int')
        self.assertIsInstance(
            family0.valid, bool, 'valid should be bool')
        self.assertIsInstance(
            family1.number, int, 'family_number should be int')
        self.assertIsInstance(
            family1.valid, bool, 'valid should be bool')

        self._assert_event_basic_types(family0[0])
        self._assert_event_basic_types(family0[1])
        self._assert_event_basic_types(family1[0])
        self._assert_event_basic_types(family1[1])

    def test_families_empty_write_read(self):
        """Test that empty families round-trip produces empty list."""
        with self._patch_runtime_config():
            write_catalog([])
            write_families([])
            families = _read_families_from_catalog_scan()

        # Assert empty
        self.assertEqual(
            len(families), 0, 'Empty families should remain empty')


if __name__ == '__main__':
    unittest.main()
