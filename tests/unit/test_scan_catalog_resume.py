# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for scan_catalog restart/continue controls.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import sys
import unittest
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np

from requake.config.parse_arguments import parse_arguments
from requake.scan.scan_catalog import (
    _get_slurm_context,
    _load_existing_pair_ids,
    _process_valid_pair_indices,
    _resolve_scan_catalog_nprocs,
    _slurm_progress_suffix,
)

SCAN_CATALOG_MODULE = importlib.import_module('requake.scan.scan_catalog')


class _DummyEvent:
    """Minimal event object used by scan_catalog helper tests."""

    def __init__(self, evid):
        self.evid = evid


class TestScanCatalogResume(unittest.TestCase):
    """Test scan_catalog resume and overwrite selection features."""

    def test_scan_catalog_force_flag(self):
        """--force should be accepted for scan_catalog."""
        with patch.object(sys, 'argv', ['requake', 'scan_catalog', '--force']):
            args = parse_arguments('requake')
        self.assertEqual(args.action, 'scan_catalog')
        self.assertTrue(args.force)
        self.assertFalse(args.force_continue)

    def test_scan_catalog_force_continue_flag(self):
        """--force-continue should be accepted for scan_catalog."""
        argv = ['requake', 'scan_catalog', '--force-continue']
        with patch.object(sys, 'argv', argv):
            args = parse_arguments('requake')
        self.assertEqual(args.action, 'scan_catalog')
        self.assertFalse(args.force)
        self.assertTrue(args.force_continue)

    def test_scan_catalog_force_modes_are_mutually_exclusive(self):
        """--force and --force-continue cannot be used together."""
        argv = [
            'requake',
            'scan_catalog',
            '--force',
            '--force-continue',
        ]
        with patch.object(sys, 'argv', argv):
            with self.assertRaises(SystemExit) as exc:
                parse_arguments('requake')
        self.assertEqual(exc.exception.code, 2)

    def test_scan_catalog_nprocs_flag(self):
        """--nprocs should be accepted for scan_catalog."""
        argv = ['requake', 'scan_catalog', '--nprocs', '4']
        with patch.object(sys, 'argv', argv):
            args = parse_arguments('requake')
        self.assertEqual(args.action, 'scan_catalog')
        self.assertEqual(args.nprocs, 4)

    def test_scan_catalog_nprocs_invalid(self):
        """--nprocs must be a non-negative integer."""
        argv = ['requake', 'scan_catalog', '--nprocs', '-1']
        with patch.object(sys, 'argv', argv):
            with self.assertRaises(SystemExit) as exc:
                parse_arguments('requake')
        self.assertEqual(exc.exception.code, 2)

    def test_load_existing_pair_ids_uses_canonical_keys(self):
        """Existing-pair IDs should be canonicalized by catalog index."""
        catalog = [_DummyEvent('A'), _DummyEvent('B'), _DummyEvent('C')]
        event_keys = [(10, 'A'), (11, 'B'), (12, 'C')]
        existing = {(11, 10), (12, 11)}
        with patch.object(
            SCAN_CATALOG_MODULE,
            'read_event_key_rows',
            return_value=event_keys,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'read_pair_key_ids',
            return_value=existing,
        ):
            existing_ids = _load_existing_pair_ids(catalog)
        nevents = len(catalog)
        expected = {
            0 * nevents + 1,
            1 * nevents + 2,
        }
        self.assertEqual(existing_ids, expected)

    def test_noninteractive_progress_uses_total_pair_count(self):
        """Resume progress log should use total pairs, not remaining."""
        with patch.object(
            SCAN_CATALOG_MODULE.sys.stderr,
            'isatty',
            return_value=False,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            '_log_noninteractive_progress',
            return_value=1.0,
        ) as log_progress, patch.object(
            SCAN_CATALOG_MODULE,
            '_process_pair',
            side_effect=AssertionError('No pairs should be processed'),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'WaveformPair',
            return_value=MagicMock(),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'write_pair_records',
        ):
            _process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.empty((0, 2), dtype=np.int32),
                npairs=0,
                initial_processed=7,
                total_pairs=10,
            )
        self.assertFalse(log_progress.called)

    def test_tqdm_uses_total_and_initial_on_resume(self):
        """Resume progress bar should initialize with total and offset."""
        with patch.object(
            SCAN_CATALOG_MODULE.sys.stderr,
            'isatty',
            return_value=True,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'tqdm',
        ) as tqdm_mock, patch.object(
            SCAN_CATALOG_MODULE,
            'WaveformPair',
            return_value=MagicMock(),
        ), patch.object(
            SCAN_CATALOG_MODULE,
            'write_pair_records',
        ):
            tqdm_mock.return_value = MagicMock()
            _process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.empty((0, 2), dtype=np.int32),
                npairs=0,
                initial_processed=12,
                total_pairs=40,
            )
        kwargs = tqdm_mock.call_args.kwargs
        self.assertEqual(kwargs['total'], 40)
        self.assertEqual(kwargs['initial'], 12)

    def test_resolve_nprocs_prefers_cli(self):
        """CLI nprocs should override config value."""
        dummy_config = SimpleNamespace(
            args=SimpleNamespace(nprocs=3),
            catalog_scan_nprocs=9,
        )
        with patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config):
            resolved = _resolve_scan_catalog_nprocs(100, {})
        self.assertEqual(resolved, 3)

    def test_resolve_nprocs_auto_slurm(self):
        """Auto nprocs should use Slurm cpus per task."""
        dummy_config = SimpleNamespace(
            args=SimpleNamespace(nprocs=None),
            catalog_scan_nprocs=0,
        )
        slurm_context = {'SLURM_CPUS_PER_TASK': '8'}
        with patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config):
            resolved = _resolve_scan_catalog_nprocs(100, slurm_context)
        self.assertEqual(resolved, 8)

    def test_resolve_nprocs_clamps_to_pair_count(self):
        """Resolved workers should be clamped to pair count."""
        dummy_config = SimpleNamespace(
            args=SimpleNamespace(nprocs=32),
            catalog_scan_nprocs=0,
        )
        with patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config):
            resolved = _resolve_scan_catalog_nprocs(5, {})
        self.assertEqual(resolved, 5)

    def test_get_slurm_context_returns_only_set_values(self):
        """Slurm context should include only environment variables set."""
        env = {
            'SLURM_JOB_ID': '1234',
            'SLURM_CPUS_PER_TASK': '12',
            'SLURM_NODELIST': 'node001',
        }
        with patch.dict(SCAN_CATALOG_MODULE.os.environ, env, clear=True):
            context = _get_slurm_context()
        self.assertEqual(context['SLURM_JOB_ID'], '1234')
        self.assertEqual(context['SLURM_CPUS_PER_TASK'], '12')
        self.assertEqual(context['SLURM_NODELIST'], 'node001')
        self.assertNotIn('SLURM_JOB_NAME', context)

    def test_slurm_progress_suffix(self):
        """Progress suffix should include compact Slurm metadata."""
        context = {
            'SLURM_JOB_ID': '77',
            'SLURM_PROCID': '2',
            'SLURM_NODELIST': 'nodeA',
            'SLURM_CPUS_PER_TASK': '16',
        }
        suffix = _slurm_progress_suffix(context)
        self.assertIn('SLURM_JOB_ID=77', suffix)
        self.assertIn('SLURM_PROCID=2', suffix)
        self.assertIn('SLURM_NODELIST=nodeA', suffix)
        self.assertNotIn('SLURM_CPUS_PER_TASK', suffix)


if __name__ == '__main__':
    unittest.main()
