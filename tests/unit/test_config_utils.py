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


if __name__ == '__main__':
    unittest.main()
