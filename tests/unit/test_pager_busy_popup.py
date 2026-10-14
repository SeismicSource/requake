# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the pager busy popup.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import time
import unittest

from requake.config.utils import abort_requested, request_abort
from requake.pager import _run_with_busy_popup


class _FakeScreen:
    """Minimal stand-in for a curses window."""

    def __init__(self, keys):
        self._keys = list(keys)
        self.nodelay_state = None

    def getmaxyx(self):
        """Return a fixed screen size."""
        return (24, 80)

    def addstr(self, *_args, **_kwargs):
        """Accept (and ignore) any drawing call."""

    def refresh(self):
        """Accept (and ignore) refresh calls."""

    def nodelay(self, state):
        """Record the nodelay state."""
        self.nodelay_state = state

    def getch(self):
        """Return the next queued key, or -1 when the queue is empty."""
        return self._keys.pop(0) if self._keys else -1


class TestRunWithBusyPopup(unittest.TestCase):
    """Test the pager busy popup and its abort handling."""

    def setUp(self):
        """Make sure the abort flag does not leak between tests."""
        request_abort(False)
        self.addCleanup(request_abort, False)

    def test_abort_key_stops_and_joins_operation(self):
        """Cancelling the popup should stop the operation and join it."""
        observed = []
        released = []

        def _operation():
            time.sleep(0.05)
            observed.append(abort_requested())
            released.append('resources released')

        screen = _FakeScreen(keys=[ord('q')])
        with self.assertRaises(KeyboardInterrupt):
            _run_with_busy_popup(screen, 'Loading...', _operation)

        self.assertEqual(observed, [True])
        self.assertEqual(released, ['resources released'])
        # The pager may keep running afterwards, so the abort request
        # must not outlive the cancelled operation.
        self.assertFalse(abort_requested())
        self.assertFalse(screen.nodelay_state)

    def test_operation_error_is_propagated(self):
        """Errors raised by the operation should be propagated."""

        def _operation():
            raise ValueError('boom')

        screen = _FakeScreen(keys=[])
        with self.assertRaises(ValueError):
            _run_with_busy_popup(screen, 'Loading...', _operation)


if __name__ == '__main__':
    unittest.main()
