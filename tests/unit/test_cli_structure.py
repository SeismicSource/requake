# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the structure of the command line.

The expectations in this module are written independently of the code
that builds the command line, so that a command added, renamed or
removed without its dispatch entry (or the other way around) fails here.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import os
import sys
import contextlib
import unittest
from unittest.mock import patch

import requake
from requake import main
from requake.cli import build_parser, parse_arguments

# Command path -> action id
COMMANDS = {
    'config sample': 'sample_config',
    'config update': 'update_config',
    'read fdsn': 'read_catalog',
    'read file': 'read_catalog',
    'scan catalog': 'scan_catalog',
    'scan templates': 'scan_templates',
    'build families': 'build_families',
    'build templates': 'build_templates',
    'print catalog': 'print_catalog',
    'print pairs': 'print_pairs',
    'print families': 'print_families',
    'list catalogs': 'print_catalogs',
    'list scans': 'print_scans',
    'list builds': 'print_family_builds',
    'plot pair': 'plot_pair',
    'plot families': 'plot_families',
    'plot timespans': 'plot_timespans',
    'plot cumulative': 'plot_cumulative',
    'plot map': 'map_families',
    'flag family': 'flag_family',
    'flag duplicates': 'dedup_events',
    'delete catalog': 'delete_catalog',
    'delete scan': 'delete_scan',
    'delete build': 'delete_build',
    'wfcache prefetch': 'wfcache_prefetch',
    'wfcache print': 'wfcache_print',
    'wfcache inspect': 'wfcache_inspect',
    'wfcache extract': 'wfcache_extract',
    'wfcache reset-failures': 'wfcache_reset_failures',
}

# Positional arguments needed by each command
POSITIONALS = {
    'read file': ['events.csv'],
    'delete catalog': ['3'],
    'delete scan': ['3'],
    'delete build': ['3'],
    'flag family': ['1', 'true'],
    'plot pair': ['evid1', 'evid2'],
}

# Names retired when the commands became a verb and an object
RETIRED = (
    'sample_config', 'update_config', 'read_catalog', 'scan_catalog',
    'scan_templates', 'build_families', 'build_templates', 'print_catalog',
    'print_pairs', 'print_families', 'print_catalogs', 'print_scans',
    'print_family_builds', 'plot_pair', 'plot_families', 'plot_timespans',
    'plot_cumulative', 'map_families', 'flag_family', 'dedup_events',
)


def _argv(path):
    """Return the command line arguments for a command path."""
    return path.split() + POSITIONALS.get(path, [])


def _defines(root, package, function):
    """Return True if a module of *package* defines *function*."""
    directory = os.path.join(root, package.lstrip('.'))
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith('.py'):
            continue
        with open(
            os.path.join(directory, filename), encoding='utf8'
        ) as source:
            if f'\ndef {function}(' in source.read():
                return True
    return False


def _parsed_actions(parser):
    """Return the action id parsed for each command path."""
    return {
        path: parser.parse_args(_argv(path)).action for path in COMMANDS
    }


def _is_rejected(parser, name):
    """Return True if *parser* refuses *name* as a command."""
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            parser.parse_args([name])
        except SystemExit as exc:
            return exc.code == 2
    return False


class TestCommandTree(unittest.TestCase):
    """Test the commands declared by the parser."""

    @classmethod
    def setUpClass(cls):
        """Build the parser once."""
        cls.parser, cls.groups = build_parser()

    def test_command_paths_set_their_action(self):
        """Each documented command path must set its action id."""
        self.assertEqual(_parsed_actions(self.parser), COMMANDS)

    def test_every_group_is_reachable(self):
        """The first-level groups must be those holding the commands."""
        expected = {path.split()[0] for path in COMMANDS}
        self.assertEqual(set(self.groups), expected)

    def test_every_command_is_two_levels_deep(self):
        """Commands must be "verb object" pairs, never flat names."""
        too_deep = [path for path in COMMANDS if len(path.split()) != 2]
        self.assertEqual(too_deep, [])

    def test_dispatch_targets_exist(self):
        """Every action must resolve to an existing command function."""
        # The command modules are not imported here: some of them can only
        # be imported once the configuration is read.
        root = os.path.dirname(requake.__file__)
        missing = [
            f'{function}() not found in {package}'
            for package, function in main._ACTIONS.values()
            if not _defines(root, package, function)
        ]
        self.assertEqual(missing, [])

    def test_dispatch_table_matches_the_commands(self):
        """The dispatch table and the commands must cover each other."""
        # sample_config and update_config are handled by configure(),
        # before the dispatch table is looked up.
        commands = set(COMMANDS.values()) - {'sample_config', 'update_config'}
        self.assertEqual(set(main._ACTIONS), commands)

    def test_retired_names_are_rejected(self):
        """The old one-word command names must no longer be accepted."""
        accepted = [
            name for name in RETIRED if not _is_rejected(self.parser, name)
        ]
        self.assertEqual(accepted, [])


class TestGroupHelp(unittest.TestCase):
    """Test the help shown when a group is given without an object."""

    def _parse(self, *argv):
        """Parse *argv*, returning the exit code and the standard output."""
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['requake', *argv]):
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc:
                    parse_arguments()
        return exc.exception.code, stdout.getvalue()

    def _check_help(self, *argv):
        """Parse *argv* and return the help output, after a clean exit."""
        code, output = self._parse(*argv)
        self.assertEqual(code, 0)
        return output

    def test_group_alone_prints_its_help(self):
        """A group without an object must print its own help and exit 0."""
        output = self._check_help('plot')
        self.assertIn('requake plot', output)
        self.assertIn('Plot data to screen or file.', output)
        self.assertIn('timespans', output)
        self.assertNotIn('requake read', output)

    def test_no_argument_prints_the_main_help(self):
        """An empty command line must print the main help and exit 0."""
        output = self._check_help()
        self.assertIn('Repeating earthquakes search and analysis', output)
        self.assertIn('wfcache', output)


if __name__ == '__main__':
    unittest.main()
