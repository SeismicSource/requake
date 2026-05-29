# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for template catalog schema and format.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
import sqlite3
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.db import get_db_path
from requake.database.templates import (
    read_template_families,
    write_template_detections,
)


class TestTemplateCatalogSchema(unittest.TestCase):
    """Test stored template detections schema and grouping."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _patch_runtime_config(self):
        """Return a patch that points the global config to a temp database."""
        return patch.dict(
            config,
            {
                'outdir': self.test_dir.name,
                'args': Namespace(outdir=self.test_dir.name, template=True),
            },
            clear=False,
        )

    def _synthetic_detection(self, family_number, trace_id, evid, cc_max):
        """Build one synthetic template detection tuple."""
        event = RequakeEvent(
            evid=evid,
            orig_time=UTCDateTime('2020-01-01T00:00:00'),
            lon=10.0,
            lat=45.0,
            depth=10.0,
            trace_id=trace_id,
        )
        return (family_number, trace_id, event, cc_max)

    def test_template_detections_group_by_family_and_trace(self):
        """Template detections should regroup into template families."""
        detections = [
            self._synthetic_detection(0, 'XX.TEST.00.BHZ', 'ev_001', 0.85),
            self._synthetic_detection(0, 'XX.TEST.00.BHZ', 'ev_002', 0.87),
            self._synthetic_detection(1, 'YY.TEST.00.BHP', 'ev_003', 0.88),
        ]

        with self._patch_runtime_config():
            write_template_detections(detections, append=False)
            families = read_template_families()

        self.assertEqual(len(families), 2)
        self.assertEqual(families[0].number, 0)
        self.assertEqual(families[0].trace_id, 'XX.TEST.00.BHZ')
        self.assertEqual(len(families[0]), 2)
        self.assertEqual(families[1].number, 1)
        self.assertEqual(families[1].trace_id, 'YY.TEST.00.BHP')

    def test_template_detection_cc_max_contract(self):
        """Verify each stored detection preserves cc_max in [-1, 1]."""
        detections = [
            self._synthetic_detection(0, 'XX.TEST.00.BHZ', 'ev_001', 0.85),
            self._synthetic_detection(0, 'XX.TEST.00.BHZ', 'ev_002', 0.87),
        ]

        with self._patch_runtime_config():
            write_template_detections(detections, append=False)
            conn = sqlite3.connect(get_db_path())
            try:
                rows = conn.execute(
                    'SELECT evid, cc_max FROM template_detections '
                    'ORDER BY evid'
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0][1], 0.85, places=6)
        self.assertAlmostEqual(rows[1][1], 0.87, places=6)
        self.assertGreaterEqual(rows[0][1], -1.0)
        self.assertLessEqual(rows[1][1], 1.0)


if __name__ == '__main__':
    unittest.main()
