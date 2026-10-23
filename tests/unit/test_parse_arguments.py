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

import io
import sys
import contextlib
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

    def test_include_invalid_option(self):
        """``--include-invalid`` must be off by default for print_pairs."""
        self.assertFalse(_parse_args('print_pairs').include_invalid)
        self.assertTrue(
            _parse_args('print_pairs', '--include-invalid').include_invalid
        )

    def test_reset_option(self):
        """``--reset`` must be off by default for dedup_events."""
        self.assertFalse(_parse_args('dedup_events').reset)
        self.assertTrue(_parse_args('dedup_events', '--reset').reset)
        self.assertTrue(_parse_args('dedup_events', '--reset', '-n').dry_run)


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


class TestPrintFamiliesOptions(unittest.TestCase):
    """Test the ``print_families`` command line options."""

    def test_events_off_by_default(self):
        """``--events`` must be off by default."""
        self.assertFalse(_parse_args('print_families').events)

    def test_events_option(self):
        """``-E``/``--events`` must select the per-event listing."""
        self.assertTrue(_parse_args('print_families', '-E').events)
        self.assertTrue(_parse_args('print_families', '--events').events)

    def test_events_combines_with_format(self):
        """``--events`` must be usable with an explicit format."""
        args = _parse_args('print_families', '-E', '-f', 'csv')
        self.assertTrue(args.events)
        self.assertEqual(args.format, 'csv')
        self.assertTrue(args.no_pager)

    def test_events_conflicts_with_detailed(self):
        """``--events`` and ``--detailed`` must be mutually exclusive."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print_families', '-E', '-d')
        self.assertEqual(cm.exception.code, 2)

    def test_events_conflicts_with_stats(self):
        """``--events`` must not be allowed with a statistics output."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print_families', '-E', '-f', 'stats')
        self.assertEqual(cm.exception.code, 2)


class TestPlotFamiliesOptions(unittest.TestCase):
    """Test the ``plot_families`` command line options."""

    def test_default_mode(self):
        """The wiggle plot mode must be the default."""
        self.assertEqual(_parse_args('plot_families').mode, 'wiggle')

    def test_mode_option(self):
        """``--mode`` must select the requested plot mode."""
        self.assertEqual(
            _parse_args('plot_families', '--mode', 'heatmap').mode,
            'heatmap')
        self.assertEqual(
            _parse_args('plot_families', '--mode', 'wiggle').mode,
            'wiggle')

    def test_invalid_mode(self):
        """An unknown plot mode must be rejected by argparse."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('plot_families', '--mode', 'matrix')
        self.assertEqual(cm.exception.code, 2)

    def test_default_max_labels(self):
        """``--max-labels`` must be unset by default."""
        self.assertIsNone(_parse_args('plot_families').max_labels)

    def test_max_labels_option(self):
        """``--max-labels`` must set the maximum number of labels."""
        self.assertEqual(
            _parse_args('plot_families', '--max-labels', '40').max_labels, 40)
        self.assertEqual(
            _parse_args('plot_families', '--max-labels', '0').max_labels, 0)

    def test_invalid_max_labels(self):
        """A non-integer label limit must be rejected by argparse."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('plot_families', '--max-labels', 'many')
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
