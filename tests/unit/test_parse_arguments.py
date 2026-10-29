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

from requake.cli import parse_arguments


def _parse_args(*argv):
    """Parse *argv* as if given on the command line."""
    with patch.object(sys, 'argv', ['requake', *argv]):
        return parse_arguments()


class TestPrintFormat(unittest.TestCase):
    """Test the format option of the ``print`` commands."""

    def test_default_format_keeps_pager_enabled(self):
        """The default format must not disable the pager."""
        args = _parse_args('print', 'families')
        self.assertEqual(args.format, 'simple')
        self.assertFalse(args.no_pager)

    def _assert_format_disables_pager(self, command, output_format):
        """Assert that *output_format* disables the pager for *command*."""
        args = _parse_args(*command.split(), '-f', output_format)
        self.assertEqual(args.format, output_format)
        self.assertTrue(args.no_pager)

    def test_format_disables_pager(self):
        """An explicit format must disable the pager."""
        self._assert_format_disables_pager('print families', 'simple')
        self._assert_format_disables_pager('print families', 'markdown')
        self._assert_format_disables_pager('print families', 'csv')
        self._assert_format_disables_pager('print families', 'stats')

    def test_no_pager_option(self):
        """``--no-pager`` must be available for all the print commands."""
        args = _parse_args('print', 'catalog', '--no-pager')
        self.assertTrue(args.no_pager)
        args = _parse_args('print', 'pairs', '--no-pager')
        self.assertTrue(args.no_pager)
        args = _parse_args('print', 'families', '--no-pager')
        self.assertTrue(args.no_pager)

    def test_format_disables_pager_for_catalog_and_pairs(self):
        """``print catalog`` and ``print pairs`` follow the same rule."""
        self._assert_format_disables_pager('print catalog', 'csv')
        self._assert_format_disables_pager('print pairs', 'csv')

    def test_stats_format_only_for_families(self):
        """The statistics format must be accepted only by print families."""
        self.assertEqual(
            _parse_args('print', 'families', '-f', 'stats').format, 'stats'
        )
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print', 'catalog', '-f', 'stats')
        self.assertEqual(cm.exception.code, 2)


class TestListPager(unittest.TestCase):
    """Test that the ``list`` commands never use the pager."""

    def test_list_commands_do_not_use_the_pager(self):
        """The list commands must print plain text by default."""
        no_pager = {
            command: _parse_args('list', command).no_pager
            for command in ('catalogs', 'scans', 'builds')
        }
        self.assertEqual(no_pager, dict.fromkeys(no_pager, True))

    def test_no_pager_option_is_still_accepted(self):
        """The old ``--no-pager`` flag must keep working on list commands."""
        args = _parse_args('list', 'catalogs', '--no-pager')
        self.assertTrue(args.no_pager)

    def test_print_commands_keep_the_pager(self):
        """The print commands must keep the pager enabled by default."""
        self.assertFalse(_parse_args('print', 'catalog').no_pager)


class TestPrintPairsOptions(unittest.TestCase):
    """Test the ``print pairs`` command line options."""

    def test_include_invalid_option(self):
        """``--include-invalid`` must be off by default."""
        self.assertFalse(_parse_args('print', 'pairs').include_invalid)
        args = _parse_args('print', 'pairs', '--include-invalid')
        self.assertTrue(args.include_invalid)

    def test_cc_limits(self):
        """The cross-correlation limits must be settable."""
        args = _parse_args('print', 'pairs', '-c', '0.9', '-C', '0.99')
        self.assertEqual(args.cc_min, 0.9)
        self.assertEqual(args.cc_max, 0.99)

    def test_cc_limits_old_spelling(self):
        """The deprecated option spelling must keep working."""
        args = _parse_args('print', 'pairs', '--cc_min', '0.9')
        self.assertEqual(args.cc_min, 0.9)
        args = _parse_args('print', 'pairs', '--cc_max', '0.99')
        self.assertEqual(args.cc_max, 0.99)


class TestScanDuplicatesOptions(unittest.TestCase):
    """Test the ``scan duplicates`` command line options."""

    def test_default_thresholds(self):
        """Default thresholds must be the documented ones."""
        args = _parse_args('scan', 'duplicates')
        self.assertEqual(args.cc_min, 0.98)
        self.assertEqual(args.max_time_diff, 60.)
        self.assertEqual(args.max_distance, 2.)
        self.assertFalse(args.dry_run)

    def test_thresholds_can_be_overridden(self):
        """Thresholds and dry-run must be settable from the command line."""
        args = _parse_args(
            'scan', 'duplicates',
            '-c', '0.99', '-t', '30', '-d', '1.5', '-n',
        )
        self.assertEqual(args.cc_min, 0.99)
        self.assertEqual(args.max_time_diff, 30.)
        self.assertEqual(args.max_distance, 1.5)
        self.assertTrue(args.dry_run)

    def test_reset_option(self):
        """``--reset`` must be off by default."""
        self.assertFalse(_parse_args('scan', 'duplicates').reset)
        self.assertTrue(
            _parse_args('scan', 'duplicates', '--reset').reset
        )


class TestPrintFamiliesOptions(unittest.TestCase):
    """Test the ``print families`` command line options."""

    def test_events_off_by_default(self):
        """``--events`` must be off by default."""
        self.assertFalse(_parse_args('print', 'families').events)

    def test_events_option(self):
        """``-E``/``--events`` must select the per-event listing."""
        self.assertTrue(_parse_args('print', 'families', '-E').events)
        self.assertTrue(_parse_args('print', 'families', '--events').events)

    def test_events_combines_with_format(self):
        """``--events`` must be usable with an explicit format."""
        args = _parse_args('print', 'families', '-E', '-f', 'csv')
        self.assertTrue(args.events)
        self.assertEqual(args.format, 'csv')
        self.assertTrue(args.no_pager)

    def test_events_conflicts_with_detailed(self):
        """``--events`` and ``--detailed`` must be mutually exclusive."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print', 'families', '-E', '-d')
        self.assertEqual(cm.exception.code, 2)

    def test_events_conflicts_with_stats(self):
        """``--events`` must not be allowed with a statistics output."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print', 'families', '-E', '-f', 'stats')
        self.assertEqual(cm.exception.code, 2)

    def test_durations_are_converted_to_seconds(self):
        """The family duration options must become seconds."""
        args = _parse_args(
            'print', 'families', '-l', '1d', '-S', '2d', '-m', '3'
        )
        self.assertEqual(args.longerthan, 86400.)
        self.assertEqual(args.shorterthan, 172800.)
        self.assertEqual(args.minevents, 3)

    def test_durations_old_spelling(self):
        """The deprecated duration options must keep working."""
        args = _parse_args(
            'print', 'families', '--longerthan', '1d', '--shorterthan', '2h'
        )
        self.assertEqual(args.longerthan, 86400.)
        self.assertEqual(args.shorterthan, 7200.)

    def test_invalid_duration(self):
        """A malformed duration must be rejected with exit code 2."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('print', 'families', '-l', '1x')
        self.assertEqual(cm.exception.code, 2)


class TestPlotFamiliesOptions(unittest.TestCase):
    """Test the ``plot families`` command line options."""

    def test_default_mode(self):
        """The wiggle plot mode must be the default."""
        self.assertEqual(_parse_args('plot', 'families').mode, 'wiggle')

    def test_mode_option(self):
        """``--mode`` must select the requested plot mode."""
        self.assertEqual(
            _parse_args('plot', 'families', '--mode', 'heatmap').mode,
            'heatmap')
        self.assertEqual(
            _parse_args('plot', 'families', '--mode', 'wiggle').mode,
            'wiggle')

    def test_invalid_mode(self):
        """An unknown plot mode must be rejected by argparse."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('plot', 'families', '--mode', 'matrix')
        self.assertEqual(cm.exception.code, 2)

    def test_default_max_labels(self):
        """``--max-labels`` must be unset by default."""
        self.assertIsNone(_parse_args('plot', 'families').max_labels)

    def test_max_labels_option(self):
        """``--max-labels`` must set the maximum number of labels."""
        args = _parse_args('plot', 'families', '--max-labels', '40')
        self.assertEqual(args.max_labels, 40)
        args = _parse_args('plot', 'families', '--max-labels', '0')
        self.assertEqual(args.max_labels, 0)

    def test_invalid_max_labels(self):
        """A non-integer label limit must be rejected by argparse."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                _parse_args('plot', 'families', '--max-labels', 'many')
        self.assertEqual(cm.exception.code, 2)

    def test_trace_window_options(self):
        """The trace window options must set their destinations."""
        args = _parse_args('plot', 'families', '-s', '1', '-e', '2')
        self.assertEqual(args.starttime, 1.)
        self.assertEqual(args.endtime, 2.)
        args = _parse_args('plot', 'families', '--starttime', '3')
        self.assertEqual(args.starttime, 3.)


if __name__ == '__main__':
    unittest.main()
