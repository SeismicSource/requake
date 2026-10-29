# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the ``edit`` commands that change stored labels.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import sys
import unittest
import tempfile
import importlib
from argparse import Namespace
from unittest.mock import patch

from requake.catalog.edit_catalog import edit_catalog
from requake.cli import parse_arguments
from requake.config import config
from requake.database.catalogs import create_catalog, read_catalog_row
from requake.database.family_builds import (
    create_family_build,
    read_family_build,
)
from requake.database.scans import create_scan, read_scan
from requake.families.edit_family_build import edit_family_build
from requake.scan.edit_scan import edit_scan

edit_catalog_module = importlib.import_module(
    'requake.catalog.edit_catalog')
edit_scan_module = importlib.import_module('requake.scan.edit_scan')
edit_build_module = importlib.import_module(
    'requake.families.edit_family_build')


class TestEditLabels(unittest.TestCase):
    """Test the edit commands that change stored labels."""

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

    def _seed(self):
        """Create a catalog, a scan and a build, each with a label."""
        catalog_id = create_catalog(
            'catalog-hash', '{}', label='old catalog'
        )
        scan_id = create_scan(
            catalog_id, 'scan-hash', '{}', label='old scan'
        )
        build_id = create_family_build(
            scan_id, 'shared', 0.9, 'build-hash', '{}', label='old build'
        )
        return catalog_id, scan_id, build_id

    def _run(self, function, module, **kwargs):
        """Run *function* with the given command line arguments."""
        config.args = Namespace(outdir=self.test_dir.name, **kwargs)
        try:
            with patch.object(module, 'logger'):
                function()
        finally:
            # The Config class mirrors items as attributes, and
            # patch.dict() restores only the items: drop the attribute so
            # that it cannot shadow the next patched configuration.
            del config.args

    def test_edit_catalog_sets_label(self):
        """Setting an explicit catalog label updates only that catalog."""
        with self._patch_runtime_config():
            catalog_id, _, _ = self._seed()
            self._run(
                edit_catalog, edit_catalog_module,
                label='new catalog', catalog_id=catalog_id
            )
            row = read_catalog_row(catalog_id)
        self.assertEqual(row['label'], 'new catalog')

    def test_edit_catalog_defaults_to_latest(self):
        """Without an id, the latest catalog is relabeled."""
        with self._patch_runtime_config():
            first = create_catalog('hash-1', '{}', label='first')
            latest = create_catalog('hash-2', '{}', label='second')
            self._run(
                edit_catalog, edit_catalog_module,
                label='third', catalog_id=None
            )
            first_row = read_catalog_row(first)
            latest_row = read_catalog_row(latest)
        self.assertEqual(first_row['label'], 'first')
        self.assertEqual(latest_row['label'], 'third')

    def test_edit_catalog_empty_label_removes_it(self):
        """A blank label is stored as no label at all."""
        with self._patch_runtime_config():
            catalog_id, _, _ = self._seed()
            self._run(
                edit_catalog, edit_catalog_module,
                label='   ', catalog_id=catalog_id
            )
            row = read_catalog_row(catalog_id)
        self.assertIsNone(row['label'])

    def test_edit_catalog_unknown_id_exits(self):
        """An unknown catalog id must be reported as an error."""
        with self._patch_runtime_config():
            self._seed()
            with patch.object(
                edit_catalog_module, 'rq_exit',
                side_effect=SystemExit
            ) as exit_mock:
                with self.assertRaises(SystemExit):
                    self._run(
                        edit_catalog, edit_catalog_module,
                        label='new', catalog_id=999
                    )
        exit_mock.assert_called_once_with(1)

    def test_edit_scan_sets_label(self):
        """Setting an explicit scan label updates only that scan."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed()
            self._run(
                edit_scan, edit_scan_module,
                label='new scan', scan_id=scan_id
            )
            row = read_scan(scan_id)
        self.assertEqual(row['label'], 'new scan')

    def test_edit_scan_defaults_to_latest(self):
        """Without an id, the latest scan is relabeled."""
        with self._patch_runtime_config():
            catalog_id, _, _ = self._seed()
            latest = create_scan(catalog_id, 'scan-hash-2', '{}')
            self._run(
                edit_scan, edit_scan_module, label='new scan', scan_id=None
            )
            row = read_scan(latest)
        self.assertEqual(row['label'], 'new scan')

    def test_edit_build_sets_label(self):
        """Setting an explicit build label updates only that build."""
        with self._patch_runtime_config():
            _, _, build_id = self._seed()
            self._run(
                edit_family_build, edit_build_module,
                label='new build', build_id=build_id
            )
            row = read_family_build(build_id)
        self.assertEqual(row['label'], 'new build')

    def test_edit_build_defaults_to_latest(self):
        """Without an id, the latest family build is relabeled."""
        with self._patch_runtime_config():
            _, scan_id, _ = self._seed()
            latest = create_family_build(
                scan_id, 'upgma', 0.9, 'build-hash-2', '{}'
            )
            self._run(
                edit_family_build, edit_build_module,
                label='new build', build_id=None
            )
            row = read_family_build(latest)
        self.assertEqual(row['label'], 'new build')


class TestEditArguments(unittest.TestCase):
    """Test the parsing of the edit sub-actions."""

    def _parse(self, argv):
        """Parse *argv* and return the resulting namespace."""
        with patch.object(sys, 'argv', ['requake'] + argv):
            return parse_arguments()

    def test_edit_catalog_arguments(self):
        """`edit catalog` maps to the catalog label action."""
        args = self._parse(
            ['edit', 'catalog', 'new label', '--catalog-id', '3']
        )
        self.assertEqual(args.action, 'edit_catalog')
        self.assertEqual(args.label, 'new label')
        self.assertEqual(args.catalog_id, 3)

    def test_edit_scan_arguments(self):
        """`edit scan` maps to the scan label action."""
        args = self._parse(['edit', 'scan', 'new label', '--scan-id', '5'])
        self.assertEqual(args.action, 'edit_scan')
        self.assertEqual(args.label, 'new label')
        self.assertEqual(args.scan_id, 5)

    def test_edit_build_arguments(self):
        """`edit build` maps to the family build label action."""
        args = self._parse(['edit', 'build', 'new label', '--build-id', '7'])
        self.assertEqual(args.action, 'edit_build')
        self.assertEqual(args.label, 'new label')
        self.assertEqual(args.build_id, 7)

    def test_edit_family_arguments(self):
        """`edit family` maps to the family flag action."""
        args = self._parse(
            ['edit', 'family', '1', 'false', '--build-id', '2']
        )
        self.assertEqual(args.action, 'flag_family')
        self.assertEqual(args.family_number, '1')
        self.assertEqual(args.is_valid, 'false')
        self.assertEqual(args.build_id, 2)

    def test_scan_duplicates_arguments(self):
        """`scan duplicates` maps to the duplicate detection action."""
        args = self._parse(['scan', 'duplicates', '--reset'])
        self.assertEqual(args.action, 'dedup_events')
        self.assertTrue(args.reset)


if __name__ == '__main__':
    unittest.main()
