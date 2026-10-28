# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the catalog registry.

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
from requake.database.catalog import read_catalog, write_catalog
from requake.database.catalogs import (
    CatalogNotFoundError,
    count_catalog_scans,
    create_catalog,
    delete_catalog_row,
    find_catalog_by_hash,
    latest_catalog_id,
    read_catalog_row,
    read_catalogs,
    resolve_catalog_id,
    summarize_catalog_delete,
)


def _events(prefix='ev'):
    """Return three synthetic events."""
    return [
        RequakeEvent(
            evid=f'{prefix}_{idx}',
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


def _create(label, events):
    """Create a catalog registry entry and write its events."""
    catalog_id = create_catalog(
        f'hash-{label}', '{}', source=f'source-{label}', label=label,
        nevents=len(events),
    )
    write_catalog(events, catalog_id)
    return catalog_id


class TestCatalogsRegistry(unittest.TestCase):
    """Test the catalog registry."""

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
            },
            clear=False,
        )

    def test_two_catalogs_coexist(self):
        """Reading a new catalog must not replace an existing one."""
        with self._patch_runtime_config():
            first = _create('first', _events('a'))
            second = _create('second', _events('b'))
            rows = read_catalogs()
            first_ids = [ev.evid for ev in read_catalog(first)]
            second_ids = [ev.evid for ev in read_catalog(second)]

        self.assertEqual([row['catalog_id'] for row in rows], [first, second])
        self.assertEqual([row['label'] for row in rows], ['first', 'second'])
        self.assertEqual(set(first_ids), {'a_0', 'a_1', 'a_2'})
        self.assertEqual(set(second_ids), {'b_0', 'b_1', 'b_2'})

    def test_latest_and_explicit_selection(self):
        """The latest catalog is the default; explicit ids are honoured."""
        with self._patch_runtime_config():
            first = _create('first', _events('a'))
            second = _create('second', _events('b'))
            self.assertEqual(latest_catalog_id(), second)
            self.assertEqual(resolve_catalog_id(), second)
            self.assertEqual(resolve_catalog_id(first), first)

    def test_find_catalog_by_hash(self):
        """The most recent catalog with a given hash is returned."""
        with self._patch_runtime_config():
            create_catalog('same-hash', '{}', label='one')
            second = create_catalog('same-hash', '{}', label='two')
            row = find_catalog_by_hash('same-hash')
            missing = find_catalog_by_hash('other-hash')

        self.assertEqual(int(row['catalog_id']), second)
        self.assertIsNone(missing)

    def test_unknown_catalog_raises(self):
        """An unknown catalog id must raise a dedicated error."""
        with self._patch_runtime_config():
            _create('first', _events('a'))
            with self.assertRaises(CatalogNotFoundError):
                read_catalog_row(999)
            with self.assertRaises(CatalogNotFoundError):
                resolve_catalog_id(999)

    def test_no_catalog_available(self):
        """Resolving the default catalog must fail on an empty database."""
        with self._patch_runtime_config():
            first = _create('first', _events('a'))
            delete_catalog_row(first)
            self.assertIsNone(latest_catalog_id())
            with self.assertRaises(CatalogNotFoundError):
                resolve_catalog_id()

    def test_delete_catalog_removes_events_and_scans(self):
        """Deleting a catalog must remove its events and dependent scans."""
        with self._patch_runtime_config():
            from requake.database.scans import create_scan, read_scans

            catalog_id = _create('first', _events('a'))
            create_scan(catalog_id, 'scan-hash', '{}')
            summary = summarize_catalog_delete(catalog_id)
            self.assertEqual(summary['events'], 3)
            self.assertEqual(summary['scans'], 1)
            delete_catalog_row(catalog_id)
            self.assertEqual(read_catalogs(), [])
            self.assertEqual(read_scans(), [])
            with self.assertRaises(CatalogNotFoundError):
                read_catalog_row(catalog_id)

    def test_count_catalog_scans(self):
        """Scan counts are reported per catalog."""
        with self._patch_runtime_config():
            from requake.database.scans import create_scan

            first = _create('first', _events('a'))
            second = _create('second', _events('b'))
            create_scan(first, 'h1', '{}')
            create_scan(first, 'h2', '{}')
            create_scan(second, 'h3', '{}')
            self.assertEqual(count_catalog_scans(first), 2)
            self.assertEqual(count_catalog_scans(second), 1)


if __name__ == '__main__':
    unittest.main()
