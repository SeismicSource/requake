# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the ``print_`` command line options.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import sys
import unittest
from unittest.mock import patch

from requake.config.parse_arguments import parse_arguments


def _parse_args(*argv):
    """Parse *argv* as if given on the command line."""
    with patch.object(sys, 'argv', ['requake', *argv]):
        return parse_arguments()


class TestPrintFormat(unittest.TestCase):
    """Test the format option of the ``print_`` commands."""

    def test_default_format_keeps_pager_enabled(self):
        """The default format must not disable the pager."""
        args = _parse_args('print_families')
        self.assertEqual(args.format, 'simple')
        self.assertFalse(args.no_pager)

    def _assert_format_disables_pager(self, command, output_format):
        """Assert that *output_format* disables the pager for *command*."""
        args = _parse_args(command, '-f', output_format)
        self.assertEqual(args.format, output_format)
        self.assertTrue(args.no_pager)

    def test_format_disables_pager(self):
        """An explicit format must disable the pager."""
        self._assert_format_disables_pager('print_families', 'simple')
        self._assert_format_disables_pager('print_families', 'markdown')
        self._assert_format_disables_pager('print_families', 'csv')
        self._assert_format_disables_pager('print_families', 'stats')

    def test_no_pager_option(self):
        """``--no-pager`` must be available for all the print commands."""
        self.assertTrue(_parse_args('print_catalog', '--no-pager').no_pager)
        self.assertTrue(_parse_args('print_pairs', '--no-pager').no_pager)
        self.assertTrue(_parse_args('print_families', '--no-pager').no_pager)

    def test_format_disables_pager_for_catalog_and_pairs(self):
        """``print_catalog`` and ``print_pairs`` follow the same rule."""
        self._assert_format_disables_pager('print_catalog', 'csv')
        self._assert_format_disables_pager('print_pairs', 'csv')


class TestDedupEventsOptions(unittest.TestCase):
    """Test the ``dedup_events`` command line options."""

    def test_default_thresholds(self):
        """Default thresholds must be the documented ones."""
        args = _parse_args('dedup_events')
        self.assertEqual(args.cc_min, 0.98)
        self.assertEqual(args.max_time_diff, 60.)
        self.assertEqual(args.max_distance, 2.)
        self.assertFalse(args.dry_run)

    def test_thresholds_can_be_overridden(self):
        """Thresholds and dry-run must be settable from the command line."""
        args = _parse_args(
            'dedup_events',
            '-c', '0.99', '-t', '30', '-d', '1.5', '-n',
        )
        self.assertEqual(args.cc_min, 0.99)
        self.assertEqual(args.max_time_diff, 30.)
        self.assertEqual(args.max_distance, 1.5)
        self.assertTrue(args.dry_run)


if __name__ == '__main__':
    unittest.main()
