# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for configuration utility helpers.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import re
import time
import threading
import unittest
import contextlib
from types import SimpleNamespace
from unittest.mock import patch

from requake.config import utils
from requake.config.utils import (
    abort_requested,
    request_abort,
    run_with_spinner,
)
from requake.terminal import display_width


class TestAbortFlag(unittest.TestCase):
    """Test the abort-request flag."""

    def setUp(self):
        """Make sure the flag does not leak between tests."""
        request_abort(False)
        self.addCleanup(request_abort, False)

    def test_flag_defaults_to_false(self):
        """No abort should be pending by default."""
        self.assertFalse(abort_requested())

    def test_flag_can_be_requested_and_cleared(self):
        """The flag should follow request_abort()."""
        request_abort()
        self.assertTrue(abort_requested())
        request_abort(False)
        self.assertFalse(abort_requested())


class TestRunWithSpinner(unittest.TestCase):
    """Test the animated progress indicator."""

    def setUp(self):
        """Make sure the flag does not leak between tests."""
        request_abort(False)
        self.addCleanup(request_abort, False)

    def test_spinner_returns_result(self):
        """The wrapped function result should be returned."""
        with contextlib.redirect_stderr(io.StringIO()):
            result = run_with_spinner('working...', lambda: 42)
        self.assertEqual(result, 42)
        self.assertFalse(abort_requested())

    def test_spinner_propagates_error(self):
        """Errors raised by the worker should be propagated."""

        def _worker():
            raise ValueError('boom')

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError):
                run_with_spinner('working...', _worker)

    def test_spinner_clears_the_whole_line(self):
        """The spinner must erase the line it printed, however long."""
        message = 'x' * 120
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            run_with_spinner(message, lambda: time.sleep(0.15))
        runs = re.findall(r' +', stderr.getvalue())
        self.assertGreaterEqual(max(len(run) for run in runs),
                                len(message) + 2)

    def test_spinner_truncates_a_long_message(self):
        """The spinner keeps its message within the terminal width."""
        message = 'x' * 120
        with contextlib.redirect_stderr(io.StringIO()) as stderr, \
                patch.object(utils, '_terminal_columns', lambda: 40), \
                patch.dict('os.environ', {'NO_COLOR': '1'}):
            run_with_spinner(message, lambda: time.sleep(0.15))
        frames = [f for f in stderr.getvalue().split('\r') if f]
        self.assertTrue(frames[0].endswith('…'))
        self.assertEqual(display_width(frames[0]), 39)

    def test_spinner_keeps_a_short_message(self):
        """A message that fits the terminal is printed in full."""
        with contextlib.redirect_stderr(io.StringIO()) as stderr, \
                patch.object(utils, '_terminal_columns', lambda: 40), \
                patch.dict('os.environ', {'NO_COLOR': '1'}):
            run_with_spinner('reading...', lambda: time.sleep(0.15))
        self.assertIn('⠋ reading...', stderr.getvalue())

    def test_spinner_runs_in_place_outside_main_process(self):
        """Worker processes must not animate the spinner."""
        calls = []

        class _FakeProcess:
            """Stand-in for a worker process."""

            name = 'ForkPoolWorker-1'

        def _worker():
            calls.append(1)
            return 'done'

        with patch.object(
            utils.multiprocessing, 'current_process',
            staticmethod(lambda: _FakeProcess()),
        ), contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = run_with_spinner('working...', _worker)
        self.assertEqual(result, 'done')
        self.assertEqual(calls, [1])
        self.assertEqual(stderr.getvalue(), '')

    def test_spinner_abort_joins_worker(self):
        """An abort should stop the worker and wait for it to finish."""
        released = []
        observed = []

        class _InterruptedEvent:
            """Event that simulates an interrupt on the first wait."""

            def set(self):
                """Do nothing: the worker result is not needed here."""

            def wait(self, timeout=None):
                """Simulate a Ctrl+C in the spinner loop."""
                raise SystemExit(1)

        def _worker():
            time.sleep(0.05)
            observed.append(abort_requested())
            released.append('resources released')

        fake_threading = SimpleNamespace(
            Event=_InterruptedEvent, Thread=threading.Thread
        )
        with patch.object(utils, 'threading', fake_threading), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run_with_spinner('working...', _worker)
        # The worker must have seen the abort request and been joined
        # before the exception was propagated.
        self.assertEqual(observed, [True])
        self.assertEqual(released, ['resources released'])
        self.assertFalse(abort_requested())


class _FakeTerminalStream(io.StringIO):
    """String stream that can report itself as a terminal."""

    def __init__(self, isatty):
        super().__init__()
        self._isatty = isatty

    def isatty(self):
        """Return the configured ``isatty`` value."""
        return self._isatty


class TestUncaughtExceptionReport(unittest.TestCase):
    """Test the bug report printed for uncaught exceptions."""

    issues_url = 'https://github.com/SeismicSource/requake/issues'
    email = 'satriano@ipgp.fr'

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

    def _report(self, stream):
        """Run the handler and return what it wrote to ``stream``."""
        exception = ValueError('boom')
        with patch.object(utils.sys, 'stderr', stream):
            with self.assertRaises(SystemExit):
                utils.manage_uncaught_exception(exception)
        return stream.getvalue()

    def test_report_contains_clickable_links(self):
        """Issue URL and email are accented OSC 8 hyperlinks on a terminal."""
        out = self._report(_FakeTerminalStream(True))
        self.assertIn(
            f'\x1b]8;;{self.issues_url}\x1b\\'
            '\x1b[38;5;31m\x1b[4m\x1b[4:5m'
            f'github.com/SeismicSource/requake/issues\x1b[0m\x1b]8;;\x1b\\',
            out,
        )
        self.assertIn(
            f'\x1b]8;;mailto:{self.email}\x1b\\'
            '\x1b[38;5;31m\x1b[4m\x1b[4:5m'
            f'{self.email}\x1b[0m\x1b]8;;\x1b\\',
            out,
        )

    def test_report_plain_text_when_redirected(self):
        """Redirected output gets plain URLs, without escape sequences."""
        out = self._report(_FakeTerminalStream(False))
        self.assertNotIn('\x1b]8;;', out)
        self.assertIn(f'Please report it on {self.issues_url}', out)
        self.assertIn(f'or by email to {self.email}.', out)

    def test_report_plain_url_on_terminals_without_osc8(self):
        """A color terminal without OSC 8 support shows the full URL."""
        with patch.dict('os.environ', {'TERM': 'xterm-256color'}):
            out = self._report(_FakeTerminalStream(True))
        self.assertNotIn('\x1b]8;;', out)
        self.assertIn(f'Please report it on {self.issues_url}', out)

    def test_report_keeps_traceback_info(self):
        """The report still lists versions and the error message."""
        out = self._report(_FakeTerminalStream(False))
        self.assertIn('# BEGIN TRACEBACK', out)
        self.assertIn('# END TRACEBACK', out)
        self.assertIn('Error message: boom', out)
        self.assertIn('Requake version:', out)

    def test_report_is_framed(self):
        """The bug report message is surrounded by a frame."""
        lines = self._report(_FakeTerminalStream(False)).splitlines()
        top = next(
            i for i, line in enumerate(lines) if line.startswith('┌')
        )
        bottom = next(
            i for i, line in enumerate(lines) if line.startswith('└')
        )
        framed = lines[top:bottom + 1]
        self.assertGreater(len(framed), 4)
        self.assertEqual(len({display_width(line) for line in framed}), 1)
        self.assertIn(
            "Congratulations, you've found a bug in Requake! 🐞",
            framed[1],
        )
        self.assertTrue(
            any('Please report it on https://' in line for line in framed)
        )
        self.assertTrue(
            any('or by email to satriano@ipgp.fr.' in line for line in framed)
        )
        self.assertFalse(
            any(line.startswith('│') for line in lines[bottom + 1:])
        )


if __name__ == '__main__':
    unittest.main()
