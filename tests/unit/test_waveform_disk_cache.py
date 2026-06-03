# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for persistent waveform disk cache.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import tempfile
import sqlite3
import unittest
import warnings
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from obspy import Trace, UTCDateTime
from obspy.clients.fdsn.header import FDSNBadGatewayException

from requake.config import config
from requake.waveforms import waveforms as waveform_module


MISSING = object()


def _build_trace(starttime):
    """Build a minimal trace suitable for miniSEED round-trip."""
    tr = Trace(data=np.arange(10, dtype=np.float32))
    tr.stats.starttime = starttime
    tr.stats.delta = 0.1
    tr.stats.network = 'IV'
    tr.stats.station = 'ATFO'
    tr.stats.location = ''
    tr.stats.channel = 'HHZ'
    return tr


class TestWaveformDiskCache(unittest.TestCase):
    """Validate persistent waveform cache behavior."""

    def setUp(self):
        """Store and override config values used by disk cache."""
        self.config_keys = (
            'args',
            'catalog_waveform_disk_cache_enabled',
            'catalog_waveform_cache_failure_max_retries',
            'catalog_waveform_cache_failure_backoff_s',
            'cc_pre_P',
            'cc_trace_length',
        )
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }
        for stat_name in waveform_module.WAVEFORM_CACHE_STATS:
            waveform_module.WAVEFORM_CACHE_STATS[stat_name] = 0

    def tearDown(self):
        """Restore config values modified by the tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def test_client_fetch_uses_disk_cache_on_second_call(self):
        """A cached event waveform avoids a second client request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_waveform_disk_cache_enabled'] = True
            config['args'] = Namespace(outdir=tmpdir)
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0

            p_arrival_time = UTCDateTime('2020-01-01T00:00:05')
            cached_trace = _build_trace(UTCDateTime('2020-01-01T00:00:04'))

            with patch.object(
                waveform_module,
                'get_waveform_from_client',
                return_value=cached_trace,
            ) as mock_get_waveform:
                first = waveform_module._get_event_waveform_from_client(
                    'ev1', 'IV.ATFO..HHZ', p_arrival_time
                )
                second = waveform_module._get_event_waveform_from_client(
                    'ev1', 'IV.ATFO..HHZ', p_arrival_time
                )

            self.assertEqual(mock_get_waveform.call_count, 1)
            np.testing.assert_allclose(first.data, second.data)
            cache_file = Path(tmpdir) / 'waveform_cache.sqlite'
            self.assertTrue(cache_file.exists())
            with sqlite3.connect(cache_file) as conn:
                rows = conn.execute(
                    'SELECT COUNT(*) FROM waveform_cache'
                ).fetchone()[0]
            self.assertEqual(rows, 1)

            stats = waveform_module.get_waveform_cache_stats()
            self.assertEqual(stats['disk_cache_hits'], 1)
            self.assertEqual(stats['disk_cache_misses'], 1)
            self.assertEqual(stats['disk_cache_writes'], 1)
            self.assertEqual(stats['disk_cache_read_errors'], 0)
            self.assertEqual(stats['disk_cache_write_errors'], 0)

    def test_cache_write_ignores_stale_mseed_encoding(self):
        """Writing cache should not emit MiniSEED encoding warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_waveform_disk_cache_enabled'] = True
            config['args'] = Namespace(outdir=tmpdir)

            tr = _build_trace(UTCDateTime('2020-01-01T00:00:04'))
            tr.stats.mseed = {'encoding': 'INT32'}

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                written = waveform_module._write_waveform_to_disk_cache(
                    'ev2',
                    'IV.ATFO..HHZ',
                    UTCDateTime('2020-01-01T00:00:04'),
                    UTCDateTime('2020-01-01T00:00:08'),
                    tr,
                )

            self.assertTrue(written)
            self.assertFalse(
                any('encoding specified' in str(w.message) for w in caught)
            )

    def test_failure_cache_prevents_immediate_retry(self):
        """Repeated failures should be skipped by persistent cache state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_waveform_disk_cache_enabled'] = True
            config['catalog_waveform_cache_failure_max_retries'] = 10
            config['catalog_waveform_cache_failure_backoff_s'] = 3600.0
            config['args'] = Namespace(outdir=tmpdir)
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0

            p_arrival_time = UTCDateTime('2020-01-01T00:00:05')
            with patch.object(
                waveform_module,
                'get_waveform_from_client',
                side_effect=waveform_module.NoWaveformError('no data'),
            ) as mock_get_waveform:
                with self.assertRaises(waveform_module.NoWaveformError):
                    waveform_module._get_event_waveform_from_client(
                        'ev1', 'IV.ATFO..HHZ', p_arrival_time
                    )
                with self.assertRaises(waveform_module.NoWaveformError):
                    waveform_module._get_event_waveform_from_client(
                        'ev1', 'IV.ATFO..HHZ', p_arrival_time
                    )
            self.assertEqual(mock_get_waveform.call_count, 1)

    def test_client_bad_gateway_raises_no_waveform_error(self):
        """Client HTTP 502 must be converted into NoWaveformError."""
        client = Mock()
        client.get_waveforms.side_effect = FDSNBadGatewayException(
            'Service responds: Bad gateway '
        )
        config['dataselect_client'] = client

        with self.assertRaises(waveform_module.NoWaveformError):
            waveform_module.get_waveform_from_client(
                'IV.ATFO..HHZ',
                UTCDateTime('2020-01-01T00:00:00'),
                UTCDateTime('2020-01-01T00:00:10'),
            )


if __name__ == '__main__':
    unittest.main()
