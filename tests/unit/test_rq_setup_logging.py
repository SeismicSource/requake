# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the Requake logging setup.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import io
import logging
import unittest
import contextlib

from requake.config import rq_setup


class TestTqdmLoggingHandler(unittest.TestCase):
    """Test that log messages never go to standard output."""

    def test_info_goes_to_stderr(self):
        """An INFO record must be written to stderr, not to stdout."""
        logger = logging.getLogger('requake_test_tqdm_logging')
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self.addCleanup(logger.handlers.clear)
        rq_setup._setup_tqdm_logging(logger)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            logger.info('Using family build 2')
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('Using family build 2', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
