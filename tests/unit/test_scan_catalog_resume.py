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
from unittest.mock import patch
import numpy as np

from requake.config.parse_arguments import parse_arguments
from requake.scan.scan_catalog import _filter_existing_pair_indices


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
        with patch(
            'requake.scan.scan_catalog.read_pair_keys',
            return_value=existing,
        ):
            filtered, skipped = _filter_existing_pair_indices(
                catalog, valid_pair_idx
            )
        expected = np.array([[0, 2]], dtype=np.int32)
        self.assertEqual(skipped, 2)
        np.testing.assert_array_equal(filtered, expected)


if __name__ == '__main__':
    unittest.main()
