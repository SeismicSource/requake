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
from requake.terminal import (
    _LINK_RGB,
    _LINK_RGB_256,
    _display_width,
    color_enabled,
    error,
    frame,
    hyperlink,
    style,
    warning,
)


class _FakeStream:
    """Minimal stream stub with a configurable ``isatty``."""

    def __init__(self, isatty):
        self._isatty = isatty

    def isatty(self):
        """Return the configured ``isatty`` value."""
        return self._isatty


_TABLE_TEXT = 'a  b\n---  ---\n1  2'
_MULTILINE_TABLE_TEXT = 'a  c\n   d\n---  ---\n1  2'
_OSC8_START = '\x1b]8;;{}\x1b\\'
_OSC8_END = '\x1b]8;;\x1b\\'
_LINK_ACCENT = '\x1b[38;5;31m\x1b[4m\x1b[4:5m'
_LINK_ACCENT_TRUECOLOR = '\x1b[38;2;0;116;217m\x1b[4m\x1b[4:5m'
_RESET = '\x1b[0m'


def _link(url, text):
    """Return the expected OSC 8 sequence for a link."""
    return (
        f'{_OSC8_START.format(url)}{_LINK_ACCENT}{text}{_RESET}{_OSC8_END}'
    )


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


class TestTerminalHyperlinks(unittest.TestCase):
    """Test the requake.terminal hyperlink helper."""

    def setUp(self):
        """Reset color- and hyperlink-related environment variables."""
        env = {
            'NO_COLOR': '', 'FORCE_COLOR': '', 'TERM': 'xterm-kitty',
            'NO_HYPERLINK': '', 'FORCE_HYPERLINK': '', 'WT_SESSION': '',
            'TERM_PROGRAM': '', 'LC_TERMINAL': '', 'VTE_VERSION': '',
            'KONSOLE_VERSION': '', 'COLORTERM': '',
        }
        patcher = patch.dict('os.environ', env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_hyperlink_drops_url_scheme(self):
        """The displayed URL loses its http(s) scheme."""
        stream = _FakeStream(True)
        self.assertEqual(
            hyperlink('https://example.org', stream=stream),
            _link('https://example.org', 'example.org'),
        )
        self.assertEqual(
            hyperlink('http://example.org', stream=stream),
            _link('http://example.org', 'example.org'),
        )

    def test_hyperlink_with_custom_text(self):
        """The display text can differ from the target URL."""
        stream = _FakeStream(True)
        self.assertEqual(
            hyperlink('https://example.org', 'example', stream=stream),
            _link('https://example.org', 'example'),
        )

    def test_hyperlink_text_is_accented(self):
        """The link text is accented, inside the OSC 8 span."""
        stream = _FakeStream(True)
        link = hyperlink('https://example.org', 'example', stream=stream)
        self.assertIn(f'{_LINK_ACCENT}example{_RESET}', link)

    def test_hyperlink_truecolor_accent(self):
        """The accent uses truecolor when the terminal supports it."""
        stream = _FakeStream(True)
        with patch.dict('os.environ', {'COLORTERM': 'truecolor'}):
            link = hyperlink('https://example.org', 'example', stream=stream)
        self.assertIn(f'{_LINK_ACCENT_TRUECOLOR}example{_RESET}', link)

    def test_hyperlink_mailto(self):
        """A mailto target keeps the readable address as text."""
        stream = _FakeStream(True)
        self.assertEqual(
            hyperlink('mailto:user@example.org', 'user@example.org',
                      stream=stream),
            _link('mailto:user@example.org', 'user@example.org'),
        )
        self.assertEqual(
            hyperlink('mailto:user@example.org', stream=stream),
            _link('mailto:user@example.org', 'mailto:user@example.org'),
        )

    def test_hyperlink_plain_when_not_a_tty(self):
        """Redirected output gets the plain, complete URL."""
        stream = _FakeStream(False)
        self.assertEqual(
            hyperlink('https://example.org', 'example', stream=stream),
            'example',
        )
        self.assertEqual(
            hyperlink('https://example.org', stream=stream),
            'https://example.org',
        )

    def test_no_color_env_disables_hyperlinks(self):
        """The NO_COLOR environment variable disables hyperlinks."""
        with patch.dict('os.environ', {'NO_COLOR': '1'}):
            self.assertEqual(
                hyperlink('https://example.org', 'example',
                          stream=_FakeStream(True)),
                'example',
            )

    def test_dumb_terminal_disables_hyperlinks(self):
        """A dumb terminal disables hyperlinks."""
        with patch.dict('os.environ', {'TERM': 'dumb'}):
            self.assertEqual(
                hyperlink('https://example.org', 'example',
                          stream=_FakeStream(True)),
                'example',
            )

    def test_unknown_terminal_keeps_the_full_url(self):
        """Color terminals without OSC 8 support get the full URL."""
        with patch.dict('os.environ', {'TERM': 'xterm-256color'}):
            self.assertEqual(
                hyperlink('https://example.org', stream=_FakeStream(True)),
                'https://example.org',
            )

    def test_term_program_identifies_a_supported_terminal(self):
        """TERM_PROGRAM can identify a terminal supporting OSC 8."""
        env = {'TERM': 'xterm-256color', 'TERM_PROGRAM': 'iTerm.app'}
        with patch.dict('os.environ', env):
            self.assertEqual(
                hyperlink('https://example.org', stream=_FakeStream(True)),
                _link('https://example.org', 'example.org'),
            )

    def test_vte_version_identifies_a_supported_terminal(self):
        """A recent VTE (GNOME Terminal and friends) supports OSC 8."""
        env = {'TERM': 'xterm-256color', 'VTE_VERSION': '5000'}
        with patch.dict('os.environ', env):
            self.assertEqual(
                hyperlink('https://example.org', stream=_FakeStream(True)),
                _link('https://example.org', 'example.org'),
            )

    def test_force_hyperlink_env_enables_hyperlinks(self):
        """FORCE_HYPERLINK enables hyperlinks on unsupported terminals."""
        env = {'TERM': 'xterm-256color', 'FORCE_HYPERLINK': '1'}
        with patch.dict('os.environ', env):
            self.assertEqual(
                hyperlink('https://example.org', stream=_FakeStream(True)),
                _link('https://example.org', 'example.org'),
            )

    def test_no_hyperlink_env_disables_hyperlinks(self):
        """NO_HYPERLINK disables hyperlinks on supported terminals."""
        env = {'TERM': 'xterm-kitty', 'NO_HYPERLINK': '1'}
        with patch.dict('os.environ', env):
            self.assertEqual(
                hyperlink('https://example.org', stream=_FakeStream(True)),
                'https://example.org',
            )

    def test_force_color_env_enables_hyperlinks(self):
        """The FORCE_COLOR environment variable enables hyperlinks."""
        with patch.dict('os.environ', {'FORCE_COLOR': '1'}):
            self.assertEqual(
                hyperlink('https://example.org', 'example',
                          stream=_FakeStream(False)),
                _link('https://example.org', 'example'),
            )


class TestTerminalFrame(unittest.TestCase):
    """Test the requake.terminal frame helper."""

    def setUp(self):
        """Reset color- and hyperlink-related environment variables."""
        env = {
            'NO_COLOR': '', 'FORCE_COLOR': '', 'TERM': 'xterm-kitty',
            'NO_HYPERLINK': '', 'FORCE_HYPERLINK': '', 'WT_SESSION': '',
            'TERM_PROGRAM': '', 'LC_TERMINAL': '', 'VTE_VERSION': '',
            'KONSOLE_VERSION': '', 'COLORTERM': '',
        }
        patcher = patch.dict('os.environ', env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_frame_draws_a_box(self):
        """The frame surrounds the text, padding the short lines."""
        self.assertEqual(
            frame('a\nbb', stream=_FakeStream(False)),
            '┌────┐\n│ a  │\n│ bb │\n└────┘',
        )

    def test_frame_keeps_blank_lines(self):
        """Blank lines inside the text are preserved."""
        self.assertEqual(
            frame('a\n\nbb', stream=_FakeStream(False)),
            '┌────┐\n│ a  │\n│    │\n│ bb │\n└────┘',
        )

    def test_frame_counts_wide_characters(self):
        """Wide characters, such as emoji, take two columns."""
        self.assertEqual(
            frame('🐞', stream=_FakeStream(False)),
            '┌────┐\n│ 🐞 │\n└────┘',
        )

    def test_frame_ignores_escape_sequences(self):
        """Colors and hyperlinks do not count toward the frame width."""
        stream = _FakeStream(True)
        link = hyperlink('https://example.org', 'example.org', stream=stream)
        framed = frame(f'see {link}', stream=stream)
        widths = {_display_width(line) for line in framed.splitlines()}
        self.assertEqual(widths, {19})

    def test_frame_border_is_colored(self):
        """The border is red when colors are enabled."""
        framed = frame('a', stream=_FakeStream(True))
        self.assertIn('\x1b[31m┌───┐\x1b[0m', framed)
        self.assertIn('\x1b[31m│\x1b[0m a \x1b[31m│\x1b[0m', framed)

    def test_frame_is_plain_without_colors(self):
        """No escape sequences are emitted when colors are disabled."""
        self.assertNotIn('\x1b[', frame('a', stream=_FakeStream(False)))


def _relative_luminance(rgb):
    """Return the relative luminance of an RGB color."""
    def _linearize(value):
        value /= 255
        return (
            ((value + 0.055) / 1.055) ** 2.4
            if value > 0.03928 else value / 12.92
        )
    red, green, blue = (_linearize(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(rgb, background):
    """Return the WCAG contrast ratio between two RGB colors."""
    luminance = _relative_luminance(rgb)
    other = _relative_luminance(background)
    lighter, darker = max(luminance, other), min(luminance, other)
    return (lighter + 0.05) / (darker + 0.05)


class TestLinkContrast(unittest.TestCase):
    """Test that the link accent is readable on dark and light terminals."""

    def test_truecolor_link_is_readable_on_black_and_white(self):
        """The truecolor accent reaches 4:1 contrast on black and white."""
        self.assertGreaterEqual(_contrast_ratio(_LINK_RGB, (0, 0, 0)), 4)
        self.assertGreaterEqual(
            _contrast_ratio(_LINK_RGB, (255, 255, 255)), 4
        )

    def test_256_color_link_is_readable_on_black_and_white(self):
        """The 256-color accent reaches 4:1 contrast on black and white."""
        self.assertGreaterEqual(
            _contrast_ratio(_LINK_RGB_256, (0, 0, 0)), 4
        )
        self.assertGreaterEqual(
            _contrast_ratio(_LINK_RGB_256, (255, 255, 255)), 4
        )


if __name__ == '__main__':
    unittest.main()
