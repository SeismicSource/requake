# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the generic table printer.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import importlib
import contextlib
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch


# The ``config`` name is imported by value in the module, so patch it
# there instead of on the global config object.
generic_printer_module = importlib.import_module(
    'requake.config.generic_printer'
)
generic_printer = generic_printer_module.generic_printer


class TestGenericPrinter(unittest.TestCase):
    """Test the plain-text table output."""

    @staticmethod
    def _print(rows, print_headers=True, output_format='simple'):
        """Run generic_printer() capturing stdout."""
        headers_fmt = [('evid', None), ('cc', '.2f')]
        out = io.StringIO()
        config_stub = SimpleNamespace(
            args=Namespace(format=output_format)
        )
        with patch.object(generic_printer_module, 'config', config_stub):
            with contextlib.redirect_stdout(out):
                generic_printer(rows, headers_fmt, print_headers)
        return out.getvalue()

    def test_headers_and_rows(self):
        """A table with headers must show the header and all rows."""
        output = self._print([['ev_a', 0.9], ['ev_b', 0.8]])
        lines = output.strip().split('\n')
        self.assertIn('evid', lines[0])
        self.assertEqual(len(lines), 4)  # header + separator + 2 rows

    def test_continuation_batch_keeps_all_rows(self):
        """Continuation batches must drop the header block, not the rows."""
        rows = [[f'ev_{i:03d}', 0.9] for i in range(1000)]
        output = self._print(rows, print_headers=False)
        lines = output.strip().split('\n')
        self.assertEqual(len(lines), 1000)
        self.assertNotIn('evid', lines[0])
        self.assertIn('ev_000', lines[0])
        self.assertIn('ev_999', lines[-1])

    def test_markdown_continuation_batch_keeps_all_rows(self):
        """The markdown format follows the same rule."""
        rows = [['ev_a', 0.9], ['ev_b', 0.8]]
        output = self._print(
            rows, print_headers=False, output_format='markdown'
        )
        lines = output.strip().split('\n')
        self.assertEqual(len(lines), 2)
        self.assertNotIn('evid', lines[0])

    def test_empty_continuation_batch_prints_nothing(self):
        """An empty continuation batch must not print anything."""
        self.assertEqual(self._print([], print_headers=False), '')


if __name__ == '__main__':
    unittest.main()
