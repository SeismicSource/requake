# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the catalog scan registry.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.catalog import write_catalog
from requake.database.catalogs import create_catalog
from requake.database.pairs import (
    PairRecord,
    count_pairs,
    read_pairs,
    write_pair_records,
)
from requake.database.scans import (
    SCAN_STATUS_COMPLETE,
    ScanNotFoundError,
    create_scan,
    delete_scan_row,
    find_scan_by_hash,
    finish_scan,
    latest_scan_id,
    read_scan,
    read_scans,
    reset_scan,
    resolve_scan_id,
    summarize_scan_delete,
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


def _pairs(events, cc=0.9):
    """Return two synthetic pair records."""
    return [
        PairRecord(events[0], events[1], 'XX.TEST.00.BHZ', 10, cc,
                   sampling_rate_hz=100.0),
        PairRecord(events[1], events[2], 'XX.TEST.00.BHZ', 20, cc,
                   sampling_rate_hz=100.0),
    ]


class TestScansRegistry(unittest.TestCase):
    """Test the catalog scan registry."""

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
                'inventory': None,
            },
            clear=False,
        )

    def _seed_catalog(self, label='cat'):
        """Create a catalog with three events and return its id."""
        events = _events()
        catalog_id = create_catalog(
            f'cat-hash-{label}', '{}', source='test', label=label,
            nevents=len(events),
        )
        write_catalog(events, catalog_id)
        return catalog_id, events

    def test_two_scans_are_isolated(self):
        """Pairs of one scan must not appear in another scan."""
        with self._patch_runtime_config():
            catalog_id, events = self._seed_catalog()
            first = create_scan(catalog_id, 'h1', '{"a": 1}', label='one')
            second = create_scan(catalog_id, 'h2', '{"a": 2}', label='two')
            write_pair_records(_pairs(events), first, append=False)
            write_pair_records(_pairs(events)[:1], second, append=False)
            first_pairs = read_pairs(first)
            second_pairs = read_pairs(second)
            first_has_pairs = count_pairs(first)
            second_has_pairs = count_pairs(second)

        self.assertEqual(len(first_pairs), 2)
        self.assertEqual(len(second_pairs), 1)
        self.assertEqual(first_has_pairs, 1)
        self.assertEqual(second_has_pairs, 1)

    def test_latest_and_explicit_selection(self):
        """The latest scan is the default; ids can be given explicitly."""
        with self._patch_runtime_config():
            catalog_id, _ = self._seed_catalog('a')
            other_catalog_id, _ = self._seed_catalog('b')
            first = create_scan(catalog_id, 'h1', '{}')
            second = create_scan(other_catalog_id, 'h2', '{}')
            self.assertEqual(latest_scan_id(), second)
            self.assertEqual(resolve_scan_id(), second)
            self.assertEqual(resolve_scan_id(first), first)
            self.assertEqual(latest_scan_id(catalog_id=catalog_id), first)

    def test_find_scan_by_hash_is_catalog_scoped(self):
        """The same hash in another catalog must not match."""
        with self._patch_runtime_config():
            first_catalog, _ = self._seed_catalog('a')
            second_catalog, _ = self._seed_catalog('b')
            first = create_scan(first_catalog, 'same-hash', '{}')
            create_scan(second_catalog, 'same-hash', '{}')
            row = find_scan_by_hash('same-hash', catalog_id=first_catalog)
            missing = find_scan_by_hash('same-hash', catalog_id=999)

        self.assertEqual(int(row['scan_id']), first)
        self.assertIsNone(missing)

    def test_finish_scan_stores_counters(self):
        """Finishing a scan records status, time and pair counters."""
        with self._patch_runtime_config():
            catalog_id, _ = self._seed_catalog()
            scan_id = create_scan(catalog_id, 'h', '{}')
            finish_scan(scan_id, npairs_stored=10, npairs_analyzed=8)
            row = read_scan(scan_id)

        self.assertEqual(row['status'], SCAN_STATUS_COMPLETE)
        self.assertIsNotNone(row['finished_at'])
        self.assertEqual(row['npairs_stored'], 10)
        self.assertEqual(row['npairs_analyzed'], 8)

    def test_unknown_scan_raises(self):
        """An unknown scan id must raise a dedicated error."""
        with self._patch_runtime_config():
            catalog_id, _ = self._seed_catalog()
            create_scan(catalog_id, 'h', '{}')
            with self.assertRaises(ScanNotFoundError):
                read_scan(999)
            with self.assertRaises(ScanNotFoundError):
                resolve_scan_id(999)

    def test_reset_scan_keeps_the_id(self):
        """Resetting a scan clears its pairs but keeps the same id."""
        with self._patch_runtime_config():
            catalog_id, events = self._seed_catalog()
            scan_id = create_scan(catalog_id, 'h1', '{"a": 1}')
            write_pair_records(_pairs(events), scan_id, append=False)
            finish_scan(scan_id, npairs_stored=2, npairs_analyzed=2)
            reset_scan(scan_id, 'h2', '{"a": 2}', nevents=3)
            row = read_scan(scan_id)
            pairs_left = read_pairs(scan_id)

        self.assertEqual(int(row['scan_id']), scan_id)
        self.assertEqual(row['params_hash'], 'h2')
        self.assertEqual(row['status'], 'running')
        self.assertIsNone(row['finished_at'])
        self.assertIsNone(row['npairs_stored'])
        self.assertEqual(pairs_left, [])

    def test_delete_scan_keeps_other_scans(self):
        """Deleting a scan must leave the other scans untouched."""
        with self._patch_runtime_config():
            catalog_id, events = self._seed_catalog()
            first = create_scan(catalog_id, 'h1', '{}')
            second = create_scan(catalog_id, 'h2', '{}')
            write_pair_records(_pairs(events), first, append=False)
            write_pair_records(_pairs(events), second, append=False)
            summary = summarize_scan_delete(first)
            self.assertEqual(summary['pairs'], 2)
            delete_scan_row(first)
            remaining = read_scans()
            second_pairs = read_pairs(second)

        self.assertEqual([int(row['scan_id']) for row in remaining], [second])
        self.assertEqual(len(second_pairs), 2)


if __name__ == '__main__':
    unittest.main()
