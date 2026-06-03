# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for waveform-cache CLI commands.

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


class TestWaveformCacheCli(unittest.TestCase):
    """Validate argparse wiring for wfcache command group."""

    def test_wfcache_print_action(self):
        """Wfcache print should map to wfcache_print action."""
        argv = ['requake', 'wfcache', 'print']
        with patch.object(sys, 'argv', argv):
            args = parse_arguments()
        self.assertEqual(args.action, 'wfcache_print')

    def test_wfcache_inspect_alias(self):
        """Wfcache inspect should map to wfcache_inspect action."""
        argv = ['requake', 'wfcache', 'inspect', '--json']
        with patch.object(sys, 'argv', argv):
            args = parse_arguments()
        self.assertEqual(args.action, 'wfcache_inspect')
        self.assertTrue(args.json)

    def test_wfcache_reset_failures_action(self):
        """Wfcache reset-failures should map to its action."""
        argv = [
            'requake',
            'wfcache',
            'reset-failures',
            '--event-id',
            'ev1',
        ]
        with patch.object(sys, 'argv', argv):
            args = parse_arguments()
        self.assertEqual(args.action, 'wfcache_reset_failures')
        self.assertEqual(args.event_id, ['ev1'])


if __name__ == '__main__':
    unittest.main()
