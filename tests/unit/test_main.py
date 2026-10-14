# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the Requake command line entry point.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import sqlite3
import unittest
import contextlib
from unittest.mock import MagicMock, patch

import requake.main
from requake.config import rq_setup
from requake.config.rq_setup import rq_exit
from requake.config.utils import request_abort


class TestMainAbortHandling(unittest.TestCase):
    """Test how the entry point handles an aborted query."""

    def setUp(self):
        """Make sure the abort flag does not leak between tests."""
        request_abort(False)
        self.addCleanup(request_abort, False)

    def _run_main(self, err):
        """
        Run main() with run() failing with *err*.

        The exit code is returned, since rq_exit() ends the process.
        """
        exit_mock = MagicMock(side_effect=SystemExit(1))
        crash_patch = patch(
            'requake.config.utils.manage_uncaught_exception'
        )
        with patch.object(requake.main, 'run', side_effect=err), \
                crash_patch as crash, \
                patch('requake.config.rq_setup.rq_exit', exit_mock):
            try:
                requake.main.main()
            except SystemExit as exc:
                return crash, exit_mock, exc.code
        return crash, exit_mock, None

    def test_aborted_query_exits_without_error_report(self):
        """An aborted query must exit cleanly, without a bug report."""
        request_abort()
        crash, exit_mock, code = self._run_main(
            sqlite3.OperationalError('interrupted')
        )
        crash.assert_not_called()
        exit_mock.assert_called_once_with(1, abort=True)
        self.assertEqual(code, 1)

    def test_spontaneous_interruption_is_reported(self):
        """An interruption with no abort pending is a bug."""
        err = sqlite3.OperationalError('interrupted')
        crash, exit_mock, code = self._run_main(err)
        crash.assert_called_once_with(err)
        exit_mock.assert_not_called()
        self.assertIsNone(code)

    def test_other_errors_are_reported(self):
        """Ordinary errors must still be reported."""
        request_abort()
        err = sqlite3.OperationalError('no such table: catalog')
        crash, exit_mock, code = self._run_main(err)
        crash.assert_called_once_with(err)
        exit_mock.assert_not_called()
        self.assertIsNone(code)


class TestRqExitAbortMessage(unittest.TestCase):
    """Test the abort message printed by rq_exit()."""

    def setUp(self):
        """Reset the one-shot abort message and keep logging usable."""
        rq_setup._ABORT_MESSAGE_PRINTED = False
        self.addCleanup(
            setattr, rq_setup, '_ABORT_MESSAGE_PRINTED', False
        )
        shutdown = patch.object(rq_setup.logging, 'shutdown')
        shutdown.start()
        self.addCleanup(shutdown.stop)

    def _capture_rq_exit(self, **kwargs):
        """Run rq_exit() and return its output and exit code."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                rq_exit(**kwargs)
        return stdout.getvalue(), ctx.exception.code

    def test_abort_message_is_printed_only_once(self):
        """Repeated aborts must not print "Aborting." twice."""
        out, code = self._capture_rq_exit(abort=True, retval=1)
        self.assertEqual(code, 1)
        self.assertIn('Aborting.', out)

        out, code = self._capture_rq_exit(abort=True, retval=1)
        self.assertEqual(code, 1)
        self.assertNotIn('Aborting.', out)

    def test_normal_exit_prints_no_abort_message(self):
        """A normal exit should not print an abort message."""
        out, code = self._capture_rq_exit(retval=0)
        self.assertEqual(code, 0)
        self.assertNotIn('Aborting.', out)


if __name__ == '__main__':
    unittest.main()
