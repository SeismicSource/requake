# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for scan_catalog restart/continue controls.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import sys
import unittest
import importlib
from unittest.mock import MagicMock, patch
import numpy as np

from requake.config.parse_arguments import parse_arguments
from requake.scan.scan_catalog import (
    _filter_existing_pair_indices,
    _process_valid_pair_indices,
)

SCAN_CATALOG_MODULE = importlib.import_module('requake.scan.scan_catalog')


class _DummyEvent:
    """Minimal event object used by scan_catalog helper tests."""

    def __init__(self, evid):
        self.evid = evid


class TestScanCatalogResume(unittest.TestCase):
    """Test scan_catalog resume and overwrite selection features."""

    def test_scan_catalog_force_flag(self):
        """--force should be accepted for scan_catalog."""
        with patch.object(sys, 'argv', ['requake', 'scan_catalog', '--force']):
            args = parse_arguments('requake')
        self.assertEqual(args.action, 'scan_catalog')
        self.assertTrue(args.force)
        self.assertFalse(args.force_continue)

    def test_scan_catalog_force_continue_flag(self):
        """--force-continue should be accepted for scan_catalog."""
        argv = ['requake', 'scan_catalog', '--force-continue']
        with patch.object(sys, 'argv', argv):
            args = parse_arguments('requake')
        self.assertEqual(args.action, 'scan_catalog')
        self.assertFalse(args.force)
        self.assertTrue(args.force_continue)

    def test_scan_catalog_force_modes_are_mutually_exclusive(self):
        """--force and --force-continue cannot be used together."""
        argv = [
            'requake',
            'scan_catalog',
            '--force',
            '--force-continue',
        ]
        with patch.object(sys, 'argv', argv):
            with self.assertRaises(SystemExit) as exc:
                parse_arguments('requake')
        self.assertEqual(exc.exception.code, 2)

    def test_filter_existing_pair_indices_uses_canonical_keys(self):
        """Resume filtering should skip already computed event pairs."""
        catalog = [_DummyEvent('A'), _DummyEvent('B'), _DummyEvent('C')]
        valid_pair_idx = np.array([[0, 1], [0, 2], [1, 2]], dtype=np.int32)
        existing = {('B', 'A'), ('C', 'B')}
        with patch.object(
            SCAN_CATALOG_MODULE,
            'read_pair_keys',
            return_value=existing,
        ):
            filtered, skipped = _filter_existing_pair_indices(
                catalog, valid_pair_idx
            )
        expected = np.array([[0, 2]], dtype=np.int32)
        self.assertEqual(skipped, 2)
        np.testing.assert_array_equal(filtered, expected)

    def test_noninteractive_progress_uses_total_pair_count(self):
        """Resume progress log should use total pairs, not remaining."""
        with patch.object(
            SCAN_CATALOG_MODULE.sys.stderr,
            'isatty',
            return_value=False,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            '_log_noninteractive_progress',
            return_value=1.0,
        ) as log_progress, patch.object(
            SCAN_CATALOG_MODULE,
            '_process_pair',
            side_effect=AssertionError('No pairs should be processed'),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'WaveformPair',
            return_value=MagicMock(),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'write_pair_records',
        ):
            _process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.empty((0, 2), dtype=np.int32),
                npairs=0,
                initial_processed=7,
                total_pairs=10,
            )
        self.assertFalse(log_progress.called)

    def test_tqdm_uses_total_and_initial_on_resume(self):
        """Resume progress bar should initialize with total and offset."""
        with patch.object(
            SCAN_CATALOG_MODULE.sys.stderr,
            'isatty',
            return_value=True,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'tqdm',
        ) as tqdm_mock, patch.object(
            SCAN_CATALOG_MODULE,
            'WaveformPair',
            return_value=MagicMock(),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'write_pair_records',
        ):
            tqdm_mock.return_value = MagicMock()
            _process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.empty((0, 2), dtype=np.int32),
                npairs=0,
                initial_processed=12,
                total_pairs=40,
            )
        kwargs = tqdm_mock.call_args.kwargs
        self.assertEqual(kwargs['total'], 40)
        self.assertEqual(kwargs['initial'], 12)


if __name__ == '__main__':
    unittest.main()
