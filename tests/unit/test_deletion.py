# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the deletion of catalogs, scans and family builds.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import sys
import unittest
import tempfile
import sqlite3
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.cli import parse_arguments
from requake.database.catalog import write_catalog
from requake.database.catalogs import (
    create_catalog,
    delete_catalog_row,
    read_catalogs,
    summarize_catalog_delete,
)
from requake.database.db import get_db_path
from requake.database.families import write_families
from requake.database.family_builds import (
    create_family_build,
    delete_family_build_row,
    read_family_builds,
    summarize_family_build_delete,
)
from requake.database.pairs import PairRecord, write_pair_records
from requake.database.scans import (
    create_scan,
    delete_scan_row,
    read_scans,
    summarize_scan_delete,
)
from requake.families.families import Family

_TABLES = (
    'catalogs', 'catalog', 'scans', 'event_pairs', 'trace_metadata',
    'family_builds', 'families', 'template_detections',
)


def _events():
    """Return three synthetic events."""
    return [
        RequakeEvent(
            evid=f'ev_{idx}',
            orig_time=UTCDateTime(f'2020-01-0{idx + 1}T00:00:00'),
            lon=10.0 + idx * 0.1,
            lat=45.0,
            depth=10.0,
            mag_type='Mw',
            mag=3.0 + idx,
            trace_id='XX.TEST.00.BHZ',
        )
        for idx in range(3)
    ]


class TestDeletion(unittest.TestCase):
    """Test the deletion primitives and the delete command arguments."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _patch_runtime_config(self):
        """Return a patch that points the global config to a temp database."""
        return patch.dict(
            config,
            {
                'args': Namespace(outdir=self.test_dir.name),
                'outdir': self.test_dir.name,
                'mag_to_slip_model': 'NJ1998',
            },
            clear=False,
        )

    def _seed_pyramid(self):
        """Create catalog, scan, pairs, build and families."""
        events = _events()
        catalog_id = create_catalog(
            'cat-hash', '{}', source='test', nevents=len(events)
        )
        write_catalog(events, catalog_id)
        scan_id = create_scan(catalog_id, 'scan-hash', '{}')
        pairs = [
            PairRecord(events[0], events[1], 'XX.TEST.00.BHZ', 10, 0.9,
                       sampling_rate_hz=100.0),
            PairRecord(events[1], events[2], 'XX.TEST.00.BHZ', 20, 0.8,
                       sampling_rate_hz=100.0),
        ]
        write_pair_records(pairs, scan_id, append=False)
        build_id = create_family_build(
            scan_id, 'shared', 0.9, 'build-hash', '{}'
        )
        family = Family(0)
        family.valid = True
        for event in events[:2]:
            family.append(event)
        write_families(build_id, catalog_id, [family])
        return catalog_id, scan_id, build_id

    def _table_counts(self):
        """Return the row count of every table."""
        conn = sqlite3.connect(get_db_path())
        try:
            counts = {}
            for table in _TABLES:
                try:
                    counts[table] = conn.execute(
                        f'SELECT COUNT(*) FROM {table}'
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    counts[table] = 0
            return counts
        finally:
            conn.close()

    def _foreign_key_violations(self):
        """Return the foreign-key violations of the database."""
        conn = sqlite3.connect(get_db_path())
        try:
            return conn.execute('PRAGMA foreign_key_check').fetchall()
        finally:
            conn.close()

    def test_summaries_do_not_modify_the_database(self):
        """Summarizing a deletion must be read-only."""
        with self._patch_runtime_config():
            catalog_id, scan_id, build_id = self._seed_pyramid()
            before = self._table_counts()
            summarize_catalog_delete(catalog_id)
            summarize_scan_delete(scan_id)
            summarize_family_build_delete(build_id)
            after = self._table_counts()

        self.assertEqual(before, after)

    def test_delete_build_removes_only_its_families(self):
        """Deleting a build removes its families, not the pairs."""
        with self._patch_runtime_config():
            catalog_id, scan_id, build_id = self._seed_pyramid()
            delete_family_build_row(build_id)
            counts = self._table_counts()
            self.assertEqual(counts['family_builds'], 0)
            self.assertEqual(counts['families'], 0)
            self.assertEqual(counts['event_pairs'], 2)
            self.assertEqual(read_family_builds(), [])
            self.assertEqual(self._foreign_key_violations(), [])
            del catalog_id, scan_id

    def test_delete_scan_removes_pairs_and_builds(self):
        """Deleting a scan removes its pairs and its family builds."""
        with self._patch_runtime_config():
            catalog_id, scan_id, _ = self._seed_pyramid()
            delete_scan_row(scan_id)
            counts = self._table_counts()
            self.assertEqual(counts['scans'], 0)
            self.assertEqual(counts['event_pairs'], 0)
            self.assertEqual(counts['trace_metadata'], 0)
            self.assertEqual(counts['family_builds'], 0)
            self.assertEqual(counts['families'], 0)
            self.assertEqual(counts['catalog'], 3)
            self.assertEqual(read_scans(), [])
            self.assertEqual(read_family_builds(), [])
            self.assertEqual(self._foreign_key_violations(), [])
            self.assertEqual(
                [row['catalog_id'] for row in read_catalogs()], [catalog_id]
            )

    def test_delete_catalog_removes_everything(self):
        """Deleting a catalog removes all the dependent data."""
        with self._patch_runtime_config():
            catalog_id, _, _ = self._seed_pyramid()
            summary = summarize_catalog_delete(catalog_id)
            delete_catalog_row(catalog_id)
            counts = self._table_counts()

        self.assertEqual(summary['scans'], 1)
        self.assertEqual(summary['pairs'], 2)
        self.assertEqual(summary['builds'], 1)
        self.assertEqual(summary['families'], 2)
        self.assertTrue(all(count == 0 for count in counts.values()))


class TestDeleteArguments(unittest.TestCase):
    """Test the parsing of the delete sub-actions."""

    def _parse(self, argv):
        """Parse *argv* and return the resulting namespace."""
        with patch.object(sys, 'argv', ['requake'] + argv):
            return parse_arguments()

    def test_delete_catalog_arguments(self):
        """`delete catalog` maps to the catalog deletion action."""
        args = self._parse(['delete', 'catalog', '3', '-n'])
        self.assertEqual(args.action, 'delete_catalog')
        self.assertEqual(args.catalog_id, 3)
        self.assertTrue(args.dry_run)
        self.assertFalse(args.force)

    def test_delete_scan_arguments(self):
        """`delete scan` maps to the scan deletion action."""
        args = self._parse(['delete', 'scan', '5', '-f'])
        self.assertEqual(args.action, 'delete_scan')
        self.assertEqual(args.scan_id, 5)
        self.assertTrue(args.force)

    def test_delete_build_arguments(self):
        """`delete build` maps to the family build deletion action."""
        args = self._parse(['delete', 'build', '7'])
        self.assertEqual(args.action, 'delete_build')
        self.assertEqual(args.build_id, 7)
        self.assertFalse(args.dry_run)


if __name__ == '__main__':
    unittest.main()
