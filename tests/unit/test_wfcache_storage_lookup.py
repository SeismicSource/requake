# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for waveform-cache lookup behavior.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import tempfile
import unittest
from argparse import Namespace

import numpy as np
from obspy import Trace, UTCDateTime

from requake.config import config
from requake.wfcache import storage as storage_mod
from requake.wfcache.storage import (
    read_waveform_from_cache,
    register_waveform_failure,
    should_skip_waveform_download,
    write_waveform_to_cache,
)

MISSING = object()


def _build_trace(starttime):
    """Build a minimal trace suitable for cache storage."""
    tr = Trace(data=np.arange(20, dtype=np.float32))
    tr.stats.starttime = starttime
    tr.stats.delta = 1.0
    tr.stats.network = 'IV'
    tr.stats.station = 'ATFO'
    tr.stats.location = ''
    tr.stats.channel = 'HHZ'
    return tr


class TestWaveformCacheStorageLookup(unittest.TestCase):
    """Validate cache lookup with exact and covering windows."""

    def setUp(self):
        """Store and override config values used by storage helpers."""
        self.config_keys = (
            'args',
            'catalog_waveform_disk_cache_enabled',
            'catalog_waveform_cache_failure_max_retries',
            'catalog_waveform_cache_failure_backoff_s',
        )
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }

    def tearDown(self):
        """Restore config values modified by tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def test_read_waveform_from_covering_window(self):
        """Read should trim and return a trace from a covering cache row."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_waveform_disk_cache_enabled'] = True
            config['args'] = Namespace(outdir=tmpdir)

            start = UTCDateTime('2020-01-01T00:00:00')
            wide_end = start + 19
            trace = _build_trace(start)
            wrote = write_waveform_to_cache(
                'ev1',
                'IV.ATFO..HHZ',
                start,
                wide_end,
                trace,
            )
            self.assertTrue(wrote)

            req_start = start + 5
            req_end = start + 10
            cut_trace = read_waveform_from_cache(
                'ev1',
                'IV.ATFO..HHZ',
                req_start,
                req_end,
            )
            self.assertIsNotNone(cut_trace)
            self.assertAlmostEqual(
                float(cut_trace.stats.starttime.timestamp),
                float(req_start.timestamp),
                places=6,
            )
            self.assertEqual(cut_trace.stats.npts, 6)

    def test_failure_skip_via_covering_window(self):
        """Negative cache should skip via covering windows as well."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_waveform_disk_cache_enabled'] = True
            config['catalog_waveform_cache_failure_max_retries'] = 0
            config['catalog_waveform_cache_failure_backoff_s'] = 0
            # Invalidate cached failure limits
            storage_mod._FAILURE_LIMITS = None
            config['args'] = Namespace(outdir=tmpdir)

            start = UTCDateTime('2020-01-01T00:00:00')
            wide_end = start + 30
            register_waveform_failure(
                'ev1',
                'IV.ATFO..HHZ',
                start,
                wide_end,
                'no data',
            )

            # Exact window within the stored covering failure
            req_start = start + 5
            req_end = start + 10
            skip, reason = should_skip_waveform_download(
                'ev1',
                'IV.ATFO..HHZ',
                req_start,
                req_end,
            )
            self.assertTrue(skip)
            self.assertIn('retry limit reached', reason)


if __name__ == '__main__':
    unittest.main()
