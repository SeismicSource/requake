# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for colored help and usage output.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import unittest
from unittest.mock import patch

from requake.config.parse_arguments import (
    ColoredHelpArgumentParser,
    SubcommandHelpFormatter,
)

DARK_ORANGE = '\x1b[38;5;208m'
GRAY = '\x1b[38;5;244m'
CYAN = '\x1b[36m'
RESET = '\x1b[0m'


class _StringStream(io.StringIO):
    """String stream that can report itself as a terminal."""

    def __init__(self, isatty):
        super().__init__()
        self._isatty = isatty

    def isatty(self):
        """Return the configured ``isatty`` value."""
        return self._isatty


def _build_parser():
    """Build a small parser using Requake's colored help classes."""
    parser = ColoredHelpArgumentParser(
        prog='requake',
        description='Test parser.',
        formatter_class=SubcommandHelpFormatter,
    )
    subparser = parser.add_subparsers(dest='action', title='commands')
    subparser.metavar = '<command> [options]'
    parser.add_argument(
        '-c', '--configfile', type=str, default='requake.conf',
        help='config file',
    )
    parser.add_argument('catalog_file', nargs='?', help='catalog file')
    subparser.add_parser('read_catalog', help='read an event catalog')
    return parser


def _invocation(parser, option_string):
    """Return the argparse-formatted invocation of an option.

    The exact text depends on the Python version (recent versions repeat
    the metavar after each option string, e.g. ``-c CONFIGFILE,
    --configfile CONFIGFILE``), so let the parser's own formatter build it.
    """
    action = next(
        action for action in parser._actions
        if option_string in action.option_strings
    )
    return parser._get_formatter()._format_action_invocation(action)


class TestColoredHelp(unittest.TestCase):
    """Test colored usage and help output."""

    def setUp(self):
        """Reset color-related environment variables."""
        env = {'NO_COLOR': '', 'FORCE_COLOR': '', 'TERM': 'xterm'}
        patcher = patch.dict('os.environ', env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _help_text(self, isatty, parser=None):
        """Return the help text as written to a fake terminal or pipe."""
        if parser is None:
            parser = _build_parser()
        stream = _StringStream(isatty)
        parser.print_help(file=stream)
        return stream.getvalue()

    def test_help_has_no_colors_when_piped(self):
        """Help written to a pipe has no escape sequences."""
        self.assertNotIn('\x1b[', self._help_text(False))

    def test_headings_are_capitalized(self):
        """Usage and section headings start with a capital letter."""
        text = self._help_text(False)
        self.assertIn('Usage: requake', text)
        self.assertIn('Options:', text)
        self.assertIn('Commands:', text)

    def test_help_has_colors_on_a_terminal(self):
        """Help written to a terminal has colors."""
        parser = _build_parser()
        text = self._help_text(True, parser)
        # usage prefix and program name
        self.assertIn(f'{DARK_ORANGE}Usage: {RESET}', text)
        self.assertIn(f'{GRAY}requake{RESET}', text)
        # options and metavars in the usage line
        self.assertIn(f'[{CYAN}-h{RESET}]', text)
        self.assertIn(f'{CYAN}CONFIGFILE{RESET}', text)
        self.assertIn(f'[{CYAN}catalog_file{RESET}]', text)
        self.assertIn(f'{CYAN}<command> [options]{RESET}', text)
        # section headings
        self.assertIn(f'{DARK_ORANGE}Options{RESET}:', text)
        self.assertIn(f'{DARK_ORANGE}Commands{RESET}:', text)
        # option strings and command names
        # (the invocation text depends on the argparse version)
        help_invocation = _invocation(parser, '-h')
        config_invocation = _invocation(parser, '-c')
        self.assertIn(f'{CYAN}{help_invocation}{RESET}', text)
        self.assertIn(f'{CYAN}{config_invocation}{RESET}', text)
        self.assertIn(f'{CYAN}read_catalog{RESET}', text)

    def test_usage_has_no_colors_when_piped(self):
        """Usage written to a pipe has no escape sequences."""
        stream = _StringStream(False)
        _build_parser().print_usage(file=stream)
        self.assertNotIn('\x1b[', stream.getvalue())

    def test_usage_has_colors_on_a_terminal(self):
        """Usage written to a terminal has colors."""
        stream = _StringStream(True)
        _build_parser().print_usage(file=stream)
        self.assertIn(f'{DARK_ORANGE}Usage: {RESET}', stream.getvalue())

    def test_help_plain_with_no_color_env(self):
        """The NO_COLOR environment variable disables help colors."""
        with patch.dict('os.environ', {'NO_COLOR': '1'}):
            self.assertNotIn('\x1b[', self._help_text(True))


if __name__ == '__main__':
    unittest.main()
