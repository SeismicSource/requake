# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for flag_family() update semantics.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import os
import importlib
from unittest.mock import patch
from argparse import Namespace
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.catalog import write_catalog
from requake.database.families import read_families, write_families
from requake.families.families import Family
from requake.families.flag_family import flag_family


flag_family_module = importlib.import_module('requake.families.flag_family')


class TestFlagFamily(unittest.TestCase):
    """Test flag_family() function."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _create_families(self, n_families=3, events_per_family=1):
        """Create synthetic families and persist them into a temp database."""
        families = []
        catalog_rows = []
        for fam_num in range(n_families):
            family = Family(fam_num)
            family.valid = True
            for ev_num in range(events_per_family):
                event = RequakeEvent(
                    evid=f'ev_{fam_num:04d}_{ev_num:02d}',
                    trace_id='XX.TEST.00.BHZ',
                    orig_time=UTCDateTime(
                        f'2020-01-{(fam_num + 1):02d}T00:00:00'
                    ),
                    lon=10.0,
                    lat=45.0,
                    depth=10.0,
                    mag_type='Mw',
                    mag=4.0,
                )
                family.append(event)
                catalog_rows.append(event)
            families.append(family)
        write_catalog(catalog_rows)
        write_families(families)

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

    def _family_valid_flags(self):
        """Read family valid flags from the database as a dict."""
        families = read_families()
        return {str(family.number): family.valid for family in families}

    def test_flag_family_toggles_valid(self):
        """Flag a family, re-read database rows, assert valid toggled."""
        with self._patch_runtime_config():
            self._create_families(3)
            config.args = Namespace(
                family_number='1',
                is_valid='false',
                outdir=self.test_dir.name,
            )

            with patch.object(flag_family_module, 'logger'):
                flag_family()

            valid_flags = self._family_valid_flags()

        # Check that family 1 is now False, others are True
        self.assertTrue(valid_flags['0'], 'Family 0 should be True')
        self.assertFalse(valid_flags['1'], 'Family 1 should be False')
        self.assertTrue(valid_flags['2'], 'Family 2 should be True')

    def test_flag_family_updates_all_rows_in_family(self):
        """Updating a family validity flag should affect all its rows."""
        with self._patch_runtime_config():
            self._create_families(2, events_per_family=3)
            config.args = Namespace(
                family_number='0',
                is_valid='false',
                outdir=self.test_dir.name,
            )

            with patch.object(flag_family_module, 'logger'):
                flag_family()

            families = read_families()

        family0 = next(family for family in families if family.number == 0)
        family1 = next(family for family in families if family.number == 1)
        self.assertFalse(family0.valid)
        self.assertTrue(family1.valid)
        self.assertEqual(len(family0), 3)

    def test_flag_family_unknown_family_no_op(self):
        """Flagging a non-existent family number leaves data unchanged."""
        with self._patch_runtime_config():
            self._create_families(2)
            config.args = Namespace(
                family_number='999',
                is_valid='false',
                outdir=self.test_dir.name,
            )
            original_flags = self._family_valid_flags()

            with patch.object(flag_family_module, 'logger'):
                flag_family()

            final_flags = self._family_valid_flags()

        self.assertEqual(original_flags, final_flags)

    def test_flag_family_invalid_value_no_op(self):
        """Invalid validity input should log and leave data unchanged."""
        with self._patch_runtime_config():
            self._create_families(2)
            config.args = Namespace(
                family_number='0',
                is_valid='maybe',
                outdir=self.test_dir.name,
            )
            original_flags = self._family_valid_flags()

            with patch.object(flag_family_module, 'logger') as logger:
                flag_family()

            final_flags = self._family_valid_flags()

        logger.error.assert_called_once()
        self.assertEqual(original_flags, final_flags)


if __name__ == '__main__':
    unittest.main()
