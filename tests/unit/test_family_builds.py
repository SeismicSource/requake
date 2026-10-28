# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the family build registry.

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
from requake.database.families import read_families, write_families
from requake.database.family_builds import (
    BUILD_STATUS_COMPLETE,
    FamilyBuildNotFoundError,
    create_family_build,
    delete_family_build_row,
    find_family_build_by_hash,
    finish_family_build,
    latest_build_id,
    read_family_build,
    read_family_builds,
    reset_family_build,
    resolve_build_id,
    summarize_family_build_delete,
)
from requake.database.scans import create_scan
from requake.database.templates import (
    read_template_families,
    write_template_detections,
)
from requake.families.families import Family


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


def _family(events, number=0):
    """Build one synthetic family with valid flag set."""
    family = Family(number)
    family.valid = True
    for event in events:
        family.append(event)
    return family


class TestFamilyBuildsRegistry(unittest.TestCase):
    """Test the family build registry."""

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

    def _seed_scan(self, label='cat'):
        """Create catalog and scan rows and return their ids."""
        events = _events()
        catalog_id = create_catalog(
            f'cat-hash-{label}', '{}', source='test', label=label,
            nevents=len(events),
        )
        write_catalog(events, catalog_id)
        scan_id = create_scan(catalog_id, f'scan-hash-{label}', '{}')
        return catalog_id, scan_id, events

    def test_two_builds_are_isolated(self):
        """Families of one build must not appear in another build."""
        with self._patch_runtime_config():
            catalog_id, scan_id, events = self._seed_scan()
            shared = create_family_build(
                scan_id, 'shared', 0.95, 'h1', '{}', label='shared'
            )
            upgma = create_family_build(
                scan_id, 'UPGMA', 0.90, 'h2', '{}', label='upgma'
            )
            write_families(shared, catalog_id, [_family(events[:2])])
            write_families(upgma, catalog_id, [_family(events)])
            shared_families = read_families(build_id=shared)
            upgma_families = read_families(build_id=upgma)

        self.assertEqual(len(shared_families[0]), 2)
        self.assertEqual(len(upgma_families[0]), 3)

    def test_latest_and_explicit_selection(self):
        """The latest build is the default; ids can be given explicitly."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed_scan()
            first = create_family_build(scan_id, 'shared', 0.9, 'h1', '{}')
            second = create_family_build(scan_id, 'UPGMA', 0.9, 'h2', '{}')
            self.assertEqual(latest_build_id(), second)
            self.assertEqual(resolve_build_id(), second)
            self.assertEqual(resolve_build_id(first), first)
            self.assertEqual(latest_build_id(scan_id=scan_id), second)

    def test_find_build_by_hash_uses_method(self):
        """The method is part of the build identity."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed_scan()
            shared = create_family_build(scan_id, 'shared', 0.9, 'same', '{}')
            upgma = create_family_build(scan_id, 'UPGMA', 0.9, 'same', '{}')
            shared_row = find_family_build_by_hash(scan_id, 'shared', 'same')
            upgma_row = find_family_build_by_hash(scan_id, 'UPGMA', 'same')

        self.assertEqual(int(shared_row['build_id']), shared)
        self.assertEqual(int(upgma_row['build_id']), upgma)

    def test_finish_build_stores_counters(self):
        """Finishing a build records status, time and counters."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed_scan()
            build_id = create_family_build(scan_id, 'shared', 0.9, 'h', '{}')
            finish_family_build(build_id, nfamilies=4, nevents=11)
            row = read_family_build(build_id)

        self.assertEqual(row['status'], BUILD_STATUS_COMPLETE)
        self.assertIsNotNone(row['finished_at'])
        self.assertEqual(row['nfamilies'], 4)
        self.assertEqual(row['nevents'], 11)

    def test_unknown_build_raises(self):
        """An unknown build id must raise a dedicated error."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed_scan()
            create_family_build(scan_id, 'shared', 0.9, 'h', '{}')
            with self.assertRaises(FamilyBuildNotFoundError):
                read_family_build(999)
            with self.assertRaises(FamilyBuildNotFoundError):
                resolve_build_id(999)

    def test_reset_build_keeps_the_id(self):
        """Resetting a build clears its families but keeps the same id."""
        with self._patch_runtime_config():
            catalog_id, scan_id, events = self._seed_scan()
            build_id = create_family_build(
                scan_id, 'shared', 0.9, 'h1', '{}'
            )
            write_families(build_id, catalog_id, [_family(events)])
            finish_family_build(build_id, nfamilies=1, nevents=3)
            reset_family_build(
                build_id, 'UPGMA', 0.8, 'h2', '{}', scan_id=scan_id
            )
            row = read_family_build(build_id)
            families_left = read_families(build_id=build_id)

        self.assertEqual(int(row['build_id']), build_id)
        self.assertEqual(row['method'], 'UPGMA')
        self.assertEqual(row['params_hash'], 'h2')
        self.assertEqual(row['status'], 'running')
        self.assertIsNone(row['nfamilies'])
        self.assertEqual(families_left, [])

    def test_delete_build_keeps_other_builds(self):
        """Deleting a build must leave the other builds untouched."""
        with self._patch_runtime_config():
            catalog_id, scan_id, events = self._seed_scan()
            first = create_family_build(scan_id, 'shared', 0.9, 'h1', '{}')
            second = create_family_build(scan_id, 'UPGMA', 0.9, 'h2', '{}')
            write_families(first, catalog_id, [_family(events)])
            write_families(second, catalog_id, [_family(events)])
            summary = summarize_family_build_delete(first)
            self.assertEqual(summary['families'], 3)
            delete_family_build_row(first)
            remaining = read_family_builds()
            second_families = read_families(build_id=second)

        self.assertEqual(
            [int(row['build_id']) for row in remaining], [second]
        )
        self.assertEqual(len(second_families[0]), 3)

    def test_template_detections_are_build_scoped(self):
        """Template detections of one build must not leak into another."""
        with self._patch_runtime_config():
            _, scan_id, events = self._seed_scan()
            first = create_family_build(scan_id, 'shared', 0.9, 'h1', '{}')
            second = create_family_build(scan_id, 'UPGMA', 0.9, 'h2', '{}')
            detections = [
                (0, 'XX.TEST.00.BHZ', events[0], 0.9),
                (0, 'XX.TEST.00.BHZ', events[1], 0.8),
            ]
            write_template_detections(first, detections, append=False)
            write_template_detections(second, detections[:1], append=False)
            first_families = read_template_families(build_id=first)
            second_families = read_template_families(build_id=second)

        self.assertEqual(len(first_families[0]), 2)
        self.assertEqual(len(second_families[0]), 1)


if __name__ == '__main__':
    unittest.main()
