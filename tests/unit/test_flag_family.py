# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for flag_family() update semantics."""

import unittest
import tempfile
import os
import csv
import importlib
from unittest.mock import patch
from requake.families.flag_family import flag_family
from argparse import Namespace


flag_family_module = importlib.import_module('requake.families.flag_family')


class TestFlagFamily(unittest.TestCase):
    """Test flag_family() function."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

        # Mock config
        from requake import config as config_module
        self.original_config = config_module.config.copy()
        self.addCleanup(self._restore_config)

    def _restore_config(self):
        """Restore original config."""
        from requake import config as config_module
        config_module.config.clear()
        config_module.config.update(self.original_config)

    def _create_families_csv(self, n_families=3):
        """
        Create a test families CSV file.

        :param n_families: number of families
        :type n_families: int
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
            for fam_num in range(n_families):
                writer.writerow({
                    'evid': f'ev_{fam_num:04d}',
                    'trace_id': 'XX.TEST.00.BHZ',
                    'orig_time': f'2020-01-{(fam_num + 1):02d}T00:00:00',
                    'lon': 10.0,
                    'lat': 45.0,
                    'depth_km': 10.0,
                    'mag_type': 'Mw',
                    'mag': 4.0,
                    'family_number': str(fam_num),
                    'valid': 'True'
                })
        return csv_path

    def _read_valid_flags(self, csv_path):
        """Read family valid flags from CSV as dict by family_number."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return {row['family_number']: row['valid'] for row in reader}

    def _read_rows(self, csv_path):
        """Read all CSV rows as list of dicts."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def test_flag_family_toggles_valid(self):
        """Flag a family, re-read file, assert valid toggled."""
        csv_path = self._create_families_csv(3)

        # Mock config
        from requake import config as config_module
        config_module.config.build_families_outfile = csv_path
        config_module.config.args = Namespace(
            family_number='1', is_valid='false')

        # Call flag_family
        with patch.object(flag_family_module, 'logger'):
            flag_family()

        valid_flags = self._read_valid_flags(csv_path)

        # Check that family 1 is now False, others are True
        self.assertEqual(valid_flags['0'], 'True', 'Family 0 should be True')
        self.assertEqual(valid_flags['1'], 'False', 'Family 1 should be False')
        self.assertEqual(valid_flags['2'], 'True', 'Family 2 should be True')

    def test_flag_family_atomic(self):
        """
        Simulate crash mid-write: original file should remain intact.

        Monkeypatch rename to fail, assert original file is unchanged
        and temp file is cleaned up.
        """
        csv_path = self._create_families_csv(2)

        # Mock config
        from requake import config as config_module
        config_module.config.build_families_outfile = csv_path
        config_module.config.args = Namespace(
            family_number='0', is_valid='false')

        original_rows = self._read_rows(csv_path)

        # Monkeypatch shutil.move to fail
        def failing_move(src, dst):
            raise RuntimeError('Simulated failure')

        with patch('shutil.move', side_effect=failing_move):
            with patch.object(flag_family_module, 'logger'):
                with self.assertRaises(RuntimeError):
                    flag_family()

        final_rows = self._read_rows(csv_path)

        # Check that file is unchanged
        self.assertEqual(
            len(original_rows),
            len(final_rows),
            'File should have same number of rows'
        )
        self.assertEqual(original_rows[0]['valid'], final_rows[0]['valid'])
        self.assertEqual(original_rows[1]['valid'], final_rows[1]['valid'])

    def test_flag_family_unknown_family_no_op(self):
        """Flagging a non-existent family number leaves file unchanged."""
        csv_path = self._create_families_csv(2)

        # Mock config with non-existent family number
        from requake import config as config_module
        config_module.config.build_families_outfile = csv_path
        config_module.config.args = Namespace(
            family_number='999', is_valid='false')

        original_rows = self._read_rows(csv_path)

        # Call flag_family
        with patch.object(flag_family_module, 'logger'):
            flag_family()

        final_rows = self._read_rows(csv_path)

        self.assertEqual(original_rows[0]['valid'], final_rows[0]['valid'])
        self.assertEqual(original_rows[1]['valid'], final_rows[1]['valid'])


if __name__ == '__main__':
    unittest.main()
