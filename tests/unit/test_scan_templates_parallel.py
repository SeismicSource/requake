# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the optional parallel template scan.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import sqlite3
import multiprocessing
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.db import get_db_path
from requake.database.templates import write_template_detections
from requake.waveforms import NoWaveformError
import importlib
st = importlib.import_module('requake.scan.scan_templates')


def _serial_time_chunks(start, end, time_chunk, overlap):
    """Independent reference implementation of the serial chunk stepping."""
    chunks = []
    time = start
    while time <= end:
        chunks.append((time, time + time_chunk + overlap))
        time += time_chunk
    return chunks


class TestTemplateTimeChunks(unittest.TestCase):
    """The parallel scan must cover exactly the serial time windows."""

    def test_time_chunks_match_serial_stepping(self):
        """_template_time_chunks reproduces the serial while-loop windows."""
        start = UTCDateTime('2021-08-23T00:00:00')
        end = start + 10000.0
        with patch.dict(
            config,
            {
                'template_start_time': start,
                'template_end_time': end,
                'time_chunk': 3600.0,
                'time_chunk_overlap': 60.0,
            },
            clear=False,
        ):
            chunks = st._template_time_chunks()
        self.assertEqual(
            chunks, _serial_time_chunks(start, end, 3600.0, 60.0)
        )
        self.assertEqual(len(chunks), 3)


class TestResolveTemplateScanNprocs(unittest.TestCase):
    """Worker-count resolution: CLI over config, 0 auto, 1 serial, capped."""

    def _auto(self):
        """Expected automatic worker count on the running machine."""
        ncpu = multiprocessing.cpu_count()
        return ncpu - 1 if ncpu > 1 else 1

    def _resolve(self, nchunks, cli_nprocs, config_nprocs):
        """Resolve nprocs with a patched CLI and config value.

        ``patch.object`` is used rather than ``patch.dict`` so that the value
        is set through ``Config.__setattr__``, keeping the attribute and the
        dict item in sync (a stale ``config.args`` instance attribute left by
        another test would otherwise shadow a ``patch.dict`` item).
        """
        with patch.object(
            config, 'args', Namespace(nprocs=cli_nprocs)
        ), patch.object(
            config, 'template_scan_nprocs', config_nprocs, create=True
        ):
            return st._resolve_template_scan_nprocs(nchunks)

    def test_config_one_disables_parallelism(self):
        """template_scan_nprocs = 1 forces the serial fast path."""
        self.assertEqual(self._resolve(3, None, 1), 1)

    def test_config_zero_is_auto_capped_by_chunks(self):
        """template_scan_nprocs = 0 selects auto, capped by nchunks."""
        self.assertEqual(self._resolve(10, None, 0), min(self._auto(), 10))
        self.assertEqual(self._resolve(1, None, 0), 1)

    def test_cli_overrides_config(self):
        """--nprocs takes precedence over the config value."""
        self.assertEqual(self._resolve(5, 1, 0), 1)
        self.assertEqual(self._resolve(10, 4, 0), 4)
        self.assertEqual(self._resolve(2, 4, 0), 2)

    def test_cli_zero_is_auto(self):
        """--nprocs 0 means auto even when the config value is set."""
        self.assertEqual(self._resolve(10, 0, 8), min(self._auto(), 10))


class TestScanChunkWorker(unittest.TestCase):
    """The chunk worker delegates to the shared detection function."""

    def test_worker_collects_and_skips_missing_data(self):
        """Detections are collected; NoWaveformError templates are skipped."""
        def fake_scan_family_template(template, t0, t1):
            if template == 'with_data':
                return (0, 'XX.TEST.00.BHZ', 'detection', 0.9)
            if template == 'no_data':
                raise NoWaveformError('no data')
            return None

        t0 = UTCDateTime('2021-08-23T00:00:00')
        t1 = t0 + 3660.0
        with patch.object(
            st, '_scan_family_template', fake_scan_family_template
        ), patch.object(
            st, '_worker_templates', ['with_data', 'no_data', 'no_detection']
        ):
            results = st._scan_chunk_worker((t0, t1))
        self.assertEqual(results, [(0, 'XX.TEST.00.BHZ', 'detection', 0.9)])


class TestOverlapDedup(unittest.TestCase):
    """Overlap-zone duplicates collapse by evid; the later write wins."""

    def setUp(self):
        """Create a temporary directory for the test database."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _patch_runtime_config(self):
        """Point the global config to a temporary database."""
        return patch.dict(
            config,
            {
                'outdir': self.test_dir.name,
                'args': Namespace(outdir=self.test_dir.name, template=True),
            },
            clear=False,
        )

    def _detection(self, evid, cc_max):
        """Build a detection tuple for one fixed family and trace."""
        event = RequakeEvent(
            evid=evid,
            orig_time=UTCDateTime('2021-08-23T00:30:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            trace_id='XX.TEST.00.BHZ',
        )
        return (0, 'XX.TEST.00.BHZ', event, cc_max)

    def test_same_evid_collapses_keeping_last(self):
        """Two detections with one evid yield one row, last writer wins."""
        # Same event detected in two overlapping chunks: identical evid,
        # marginally different cc_max. Flattening in chunk order means the
        # later chunk is written last and wins the database REPLACE.
        detections = [self._detection('reqk2021aaaaaa', 0.80),
                      self._detection('reqk2021aaaaaa', 0.90)]
        with self._patch_runtime_config():
            write_template_detections(detections, append=False)
            conn = sqlite3.connect(get_db_path())
            try:
                rows = conn.execute(
                    'SELECT evid, cc_max FROM template_detections'
                ).fetchall()
            finally:
                conn.close()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0][1], 0.90, places=6)


if __name__ == '__main__':
    unittest.main()
