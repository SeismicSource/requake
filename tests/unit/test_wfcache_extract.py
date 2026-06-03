# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for waveform-cache extract command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import numpy as np
from obspy import Trace, UTCDateTime

from requake.config import config
from requake.wfcache import commands as commands_module
from requake.wfcache.storage import write_waveform_to_cache

MISSING = object()


def _build_trace(starttime):
    """Build a minimal trace suitable for miniSEED/SAC writing."""
    tr = Trace(data=np.arange(10, dtype=np.float32))
    tr.stats.starttime = starttime
    tr.stats.delta = 0.1
    tr.stats.network = 'IV'
    tr.stats.station = 'ATFO'
    tr.stats.location = ''
    tr.stats.channel = 'HHZ'
    return tr


class TestWaveformCacheExtract(unittest.TestCase):
    """Validate waveform-cache extract command behavior."""

    def setUp(self):
        """Store and override config values used by extract command."""
        self.config_keys = (
            'args',
            'catalog_waveform_disk_cache_enabled',
        )
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }

    def tearDown(self):
        """Restore config values modified by the tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def test_extract_writes_filtered_mseed_files(self):
        """Extract should write files for rows matching shared filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            export_dir = outdir / 'exported'
            config['catalog_waveform_disk_cache_enabled'] = True
            config['args'] = Namespace(outdir=str(outdir))

            start = UTCDateTime('2020-01-01T00:00:00')
            trace = _build_trace(start)
            wrote = write_waveform_to_cache(
                'ev1',
                'IV.ATFO..HHZ',
                start,
                start + 1,
                trace,
            )
            self.assertTrue(wrote)

            config['args'] = Namespace(
                outdir=str(outdir),
                event_id=['ev1'],
                event_id_file=None,
                trace_id=['IV.ATFO..HHZ'],
                start_time=None,
                end_time=None,
                limit=None,
                format='mseed',
                output_dir=str(export_dir),
            )

            with self.assertRaises(SystemExit) as exit_err:
                commands_module.wfcache_extract()
            self.assertEqual(exit_err.exception.code, 0)
            exported_files = list(export_dir.glob('*.mseed'))
            self.assertEqual(len(exported_files), 1)


if __name__ == '__main__':
    unittest.main()
