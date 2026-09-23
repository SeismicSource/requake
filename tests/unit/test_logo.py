# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the Requake logo.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import contextlib
import io
import unittest
from unittest.mock import patch

from requake.config.parse_arguments import parse_arguments
from requake.logo import REQUAKE_LOGO

# U+018E, LATIN CAPITAL LETTER REVERSED E
REVERSED_E = '\u018e'
# U+25C0, BLACK LEFT-POINTING TRIANGLE
LEFT_TRIANGLE = '\u25c0'


class TestLogo(unittest.TestCase):
    """Test the Requake logo."""

    def test_logo_spells_stylized_name(self):
        """The logo decorates the program name with triangles."""
        expected = f'{LEFT_TRIANGLE}{LEFT_TRIANGLE} R{REVERSED_E}Quake'
        self.assertEqual(REQUAKE_LOGO, expected)

    def test_logo_is_shown_in_help(self):
        """The logo is shown in the command line help."""
        buffer = io.StringIO()
        with patch('sys.argv', ['requake', '-h']):
            with contextlib.redirect_stdout(buffer):
                with self.assertRaises(SystemExit):
                    parse_arguments()
        self.assertIn(REQUAKE_LOGO, buffer.getvalue())


if __name__ == '__main__':
    unittest.main()
