# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the S-wave cross-correlation and combined acceptance criterion.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import importlib
import unittest
import tempfile
import sqlite3
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from obspy import Trace, UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.db import get_db_path
from requake.database.templates import write_template_detections

st = importlib.import_module('requake.scan.scan_templates')


class TestCombinedCriterion(unittest.TestCase):
    """The combined NCC/NCCs acceptance criterion is fully parametrizable."""

    def setUp(self):
        """Patch the combined-criterion thresholds."""
        patcher = patch.multiple(
            config,
            create=True,
            template_cc_min=0.6,
            template_cc_min_combined=0.4,
            template_ccs_min_combined=0.7,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_accepts_on_high_ncc_alone(self):
        """NCC above template_cc_min is accepted regardless of NCCs."""
        self.assertTrue(st._accept_detection(0.65, None))
        self.assertTrue(st._accept_detection(0.65, 0.0))

    def test_accepts_on_combined_clause(self):
        """Moderate NCC plus high NCCs is accepted."""
        self.assertTrue(st._accept_detection(0.55, 0.75))

    def test_rejects_when_nccs_too_low(self):
        """Moderate NCC with insufficient NCCs is rejected."""
        self.assertFalse(st._accept_detection(0.55, 0.65))

    def test_rejects_when_ncc_below_combined_floor(self):
        """NCC below template_cc_min_combined is rejected even at high NCCs."""
        self.assertFalse(st._accept_detection(0.35, 0.95))

    def test_rejects_without_nccs(self):
        """Without NCCs only the high-NCC clause can accept."""
        self.assertFalse(st._accept_detection(0.55, None))

    def test_thresholds_are_strict(self):
        """Equality does not pass the strict comparison."""
        self.assertFalse(st._accept_detection(0.6, None))

    def test_thresholds_track_config(self):
        """Lowering template_cc_min changes the decision."""
        with patch.object(config, 'template_cc_min', 0.5):
            self.assertTrue(st._accept_detection(0.55, None))


class TestCcsDetectionFallback(unittest.TestCase):
    """The S-wave correlation degrades gracefully without geometry."""

    def test_returns_none_without_sac_geometry(self):
        """A template without SAC headers yields no NCCs."""
        tr = Trace(data=np.zeros(100, dtype='float64'))
        tr.stats.sampling_rate = 20.0
        tr.stats.starttime = UTCDateTime(0)
        template = Trace(data=np.zeros(100, dtype='float64'))
        template.stats.sampling_rate = 20.0
        template.stats.starttime = UTCDateTime(0)
        self.assertIsNone(
            st._ccs_detection(tr, template, UTCDateTime(10))
        )


class TestCcsStorage(unittest.TestCase):
    """The ccs column is persisted and the schema migrates in place."""

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

    def _detection(self, evid, cc_max, ccs=None):
        """Build a detection tuple, with or without an NCCs value."""
        event = RequakeEvent(
            evid=evid,
            orig_time=UTCDateTime('2021-08-23T00:00:00'),
            lon=10.0, lat=45.0, depth=10.0, trace_id='XX.TEST.00.BHZ',
        )
        if ccs is None:
            return (0, 'XX.TEST.00.BHZ', event, cc_max)
        return (0, 'XX.TEST.00.BHZ', event, cc_max, ccs)

    def test_ccs_is_stored_and_nullable(self):
        """A 5-tuple stores ccs; a 4-tuple stores NULL."""
        with self._patch_runtime_config():
            write_template_detections(
                [self._detection('reqk2021aaaaaa', 0.85, 0.91),
                 self._detection('reqk2021bbbbbb', 0.80)],
                append=False,
            )
            conn = sqlite3.connect(get_db_path())
            try:
                rows = dict(conn.execute(
                    'SELECT evid, ccs FROM template_detections'
                ).fetchall())
            finally:
                conn.close()
        self.assertAlmostEqual(rows['reqk2021aaaaaa'], 0.91, places=6)
        self.assertIsNone(rows['reqk2021bbbbbb'])

    def test_schema_migration_adds_ccs(self):
        """Writing into an old table without ccs migrates it in place."""
        with self._patch_runtime_config():
            conn = sqlite3.connect(get_db_path())
            conn.execute(
                'CREATE TABLE template_detections ('
                'id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'family_number INTEGER NOT NULL, trace_id TEXT NOT NULL, '
                'evid TEXT NOT NULL, orig_time TEXT NOT NULL, lon REAL, '
                'lat REAL, depth_km REAL, cc_max REAL, '
                'UNIQUE (family_number, trace_id, evid))'
            )
            conn.commit()
            conn.close()
            write_template_detections(
                [self._detection('reqk2021cccccc', 0.8, 0.9)], append=True
            )
            conn = sqlite3.connect(get_db_path())
            try:
                cols = [
                    r[1] for r in conn.execute(
                        'PRAGMA table_info(template_detections)'
                    )
                ]
                ccs = conn.execute(
                    'SELECT ccs FROM template_detections'
                ).fetchone()[0]
            finally:
                conn.close()
        self.assertIn('ccs', cols)
        self.assertAlmostEqual(ccs, 0.9, places=6)


class TestTemplateSMinusP(unittest.TestCase):
    """S minus P uses cached SAC picks and avoids per-detection TauP calls."""

    def _template(self, sac):
        """Build a minimal template trace carrying a SAC header dict."""
        tr = Trace(data=np.zeros(10, dtype='float64'))
        tr.stats.sampling_rate = 20.0
        tr.stats.sac = sac
        return tr

    def test_uses_sac_picks_without_taup(self):
        """When a and t0 are set, S-P comes from picks, never from TauP."""
        tr = self._template({'a': 5.0, 't0': 12.0})
        with patch.object(st, 'get_arrivals',
                          side_effect=AssertionError('TauP called')):
            self.assertAlmostEqual(st._template_s_minus_p(tr), 7.0)
        self.assertAlmostEqual(tr.stats.s_minus_p, 7.0)

    def test_cache_short_circuits(self):
        """A cached value is returned without touching the SAC header."""
        tr = self._template({'a': 5.0, 't0': 12.0})
        tr.stats.s_minus_p = 3.0
        with patch.object(st, 'get_arrivals',
                          side_effect=AssertionError('TauP called')):
            self.assertAlmostEqual(st._template_s_minus_p(tr), 3.0)

    def test_falls_back_to_arrivals_when_picks_missing(self):
        """Undefined SAC picks (-12345) fall back to a travel-time call."""
        tr = self._template({'a': 5.0, 't0': -12345.0, 'stla': 0.0,
                             'stlo': 0.0, 'evla': 1.0, 'evlo': 1.0,
                             'evdp': 10.0})
        fake = (SimpleNamespace(time=2.0), SimpleNamespace(time=9.0), 0.0, 0.0)
        with patch.object(st, 'get_arrivals', return_value=fake):
            self.assertAlmostEqual(st._template_s_minus_p(tr), 7.0)


if __name__ == '__main__':
    unittest.main()
