# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for colored terminal output helpers.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
from unittest.mock import patch

from requake.config.generic_printer import _style_table
from requake.terminal import color_enabled, error, style, warning


class _FakeStream:
    """Minimal stream stub with a configurable ``isatty``."""

    def __init__(self, isatty):
        self._isatty = isatty

    def isatty(self):
        """Return the configured ``isatty`` value."""
        return self._isatty


_TABLE_TEXT = 'a  b\n---  ---\n1  2'
_MULTILINE_TABLE_TEXT = 'a  c\n   d\n---  ---\n1  2'


class TestTerminalColors(unittest.TestCase):
    """Test the requake.terminal color helpers."""

    def setUp(self):
        """Reset color-related environment variables."""
        env = {'NO_COLOR': '', 'FORCE_COLOR': '', 'TERM': 'xterm'}
        patcher = patch.dict('os.environ', env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_style_plain_when_not_a_tty(self):
        """Styles are stripped when the stream is not a terminal."""
        stream = _FakeStream(False)
        self.assertEqual(
            style('hello', 'bold', 'red', stream=stream), 'hello'
        )

    def test_style_codes_when_a_tty(self):
        """Styles are applied when the stream is a terminal."""
        stream = _FakeStream(True)
        self.assertEqual(
            style('hello', 'bold', 'red', stream=stream),
            '\x1b[1m\x1b[31mhello\x1b[0m',
        )

    def test_style_without_styles_is_plain(self):
        """No styles means no escape sequences."""
        stream = _FakeStream(True)
        self.assertEqual(style('hello', stream=stream), 'hello')

    def test_style_unknown_style_raises(self):
        """Unknown style names raise a ValueError."""
        stream = _FakeStream(True)
        with self.assertRaises(ValueError):
            style('hello', 'not-a-style', stream=stream)

    def test_error_and_warning_prefixes(self):
        """Error and warning helpers add a plain prefix when disabled."""
        stream = _FakeStream(False)
        self.assertEqual(error('boom', stream=stream), 'ERROR: boom')
        self.assertEqual(
            warning('careful', stream=stream), 'WARNING: careful'
        )

    def test_error_and_warning_are_colored(self):
        """Error and warning labels are colored when enabled."""
        stream = _FakeStream(True)
        self.assertIn(
            '\x1b[1m\x1b[31mERROR:\x1b[0m', error('boom', stream=stream)
        )
        self.assertIn(
            '\x1b[1m\x1b[33mWARNING:\x1b[0m',
            warning('careful', stream=stream),
        )

    def test_no_color_env_disables_colors(self):
        """The NO_COLOR environment variable disables colors."""
        with patch.dict('os.environ', {'NO_COLOR': '1'}):
            self.assertFalse(color_enabled(_FakeStream(True)))

    def test_force_color_env_enables_colors(self):
        """The FORCE_COLOR environment variable enables colors."""
        with patch.dict('os.environ', {'FORCE_COLOR': '1'}):
            self.assertTrue(color_enabled(_FakeStream(False)))

    def test_auto_follows_stream_isatty(self):
        """In 'auto' mode colors follow the stream being a terminal."""
        self.assertTrue(color_enabled(_FakeStream(True)))
        self.assertFalse(color_enabled(_FakeStream(False)))

    def test_dumb_terminal_disables_colors(self):
        """A dumb terminal disables colors."""
        with patch.dict('os.environ', {'TERM': 'dumb'}):
            self.assertFalse(color_enabled(_FakeStream(True)))

    def test_style_table_highlights_header_and_separator(self):
        """Table headers are bold cyan and separators are dimmed."""
        with patch.dict('os.environ', {'FORCE_COLOR': '1'}):
            styled = _style_table(_TABLE_TEXT).split('\n')
        self.assertEqual(styled[0], '\x1b[1m\x1b[36ma  b\x1b[0m')
        self.assertEqual(styled[1], '\x1b[2m---  ---\x1b[0m')
        self.assertEqual(styled[2], '1  2')

    def test_style_table_highlights_multiline_header(self):
        """All header lines before the separator are highlighted."""
        with patch.dict('os.environ', {'FORCE_COLOR': '1'}):
            styled = _style_table(_MULTILINE_TABLE_TEXT).split('\n')
        self.assertTrue(styled[0].startswith('\x1b[1m\x1b[36m'))
        self.assertTrue(styled[1].startswith('\x1b[1m\x1b[36m'))
        self.assertEqual(styled[2], '\x1b[2m---  ---\x1b[0m')
        self.assertEqual(styled[3], '1  2')

    def test_style_table_without_header(self):
        """No header means no highlighting."""
        with patch.dict('os.environ', {'FORCE_COLOR': '1'}):
            text = _style_table('1  2\n3  4', has_header=False)
        self.assertEqual(text, '1  2\n3  4')

    def test_style_table_plain_when_disabled(self):
        """Table text is untouched when colors are disabled."""
        self.assertEqual(_style_table(_TABLE_TEXT), _TABLE_TEXT)


if __name__ == '__main__':
    unittest.main()
