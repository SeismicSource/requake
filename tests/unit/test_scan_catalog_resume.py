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
import logging
import unittest
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np

from requake.config.parse_arguments import parse_arguments
from requake.scan.scan_catalog import (
    _ParallelCacheStatsCollector,
    _effective_worker_cache_size,
    _get_slurm_context,
    _load_existing_pair_ids,
    _log_pair_processing_report,
    _max_pending_futures,
    _process_pairs,
    _process_valid_pair_indices,
    _result_to_pair_record,
    _resolve_scan_catalog_nprocs,
    _silence_worker_console_logging,
    _slurm_progress_suffix,
)

SCAN_CATALOG_MODULE = importlib.import_module('requake.scan.scan_catalog')


class _DummyEvent:
    """Minimal event object used by scan_catalog helper tests."""

    def __init__(self, evid):
        self.evid = evid


class _DummyConfig:
    """Config stub used by scan_catalog helper tests."""

    def __init__(self):
        self.args = SimpleNamespace(traceid=None)
        self.catalog_trace_id = ['WI.TDBA.00.HHZ']


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

    def test_max_pending_futures_is_bounded(self):
        """Pending futures should have a deterministic lower bound."""
        self.assertEqual(_max_pending_futures(1), 32)
        self.assertEqual(_max_pending_futures(8), 32)
        self.assertEqual(_max_pending_futures(20), 40)

    def test_effective_worker_cache_size_splits_global_cache(self):
        """Without override, parallel cache should split global budget."""
        dummy_config = SimpleNamespace(
            catalog_waveform_cache_size=5000,
            catalog_waveform_cache_size_parallel=0,
        )
        with patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config):
            size = _effective_worker_cache_size(7)
        self.assertEqual(size, 714)

    def test_effective_worker_cache_size_parallel_override(self):
        """Parallel override should set per-worker cache size directly."""
        dummy_config = SimpleNamespace(
            catalog_waveform_cache_size=5000,
            catalog_waveform_cache_size_parallel=1200,
        )
        with patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config):
            size = _effective_worker_cache_size(7)
        self.assertEqual(size, 1200)

    def test_process_valid_pair_indices_uses_parallel_branch(self):
        """nprocs>1 should route processing through parallel helper."""
        with patch.object(
            SCAN_CATALOG_MODULE.sys.stderr,
            'isatty',
            return_value=False,
        ), patch.object(
            SCAN_CATALOG_MODULE,
            '_process_valid_pair_indices_parallel',
            return_value=11,
        ) as parallel_mock:
            result = _process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.array([[0, 0]], dtype=np.int32),
                npairs=1,
                initial_processed=0,
                total_pairs=1,
                nprocs=2,
                slurm_context={},
            )
        self.assertEqual(result, 11)
        self.assertTrue(parallel_mock.called)

    def test_process_pairs_loads_inventory_before_trace_metadata(self):
        """Parent should load inventory before parent-side metadata writes."""
        call_order = []
        dummy_config = _DummyConfig()
        valid_pair_idx = np.empty((0, 2), dtype=np.int32)
        catalog = [_DummyEvent('A'), _DummyEvent('B')]

        def _mark_load_inventory():
            call_order.append('load_inventory')

        def _mark_store_trace_metadata(_trace_ids):
            call_order.append('store_trace_metadata')

        with (
            patch.object(SCAN_CATALOG_MODULE, 'config', dummy_config),
            patch.object(
                SCAN_CATALOG_MODULE,
                'write_pair_records',
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                'load_inventory',
                side_effect=_mark_load_inventory,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                'store_trace_metadata_from_inventory',
                side_effect=_mark_store_trace_metadata,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                '_build_valid_pair_indices',
                return_value=valid_pair_idx,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                '_resolve_scan_catalog_nprocs',
                return_value=1,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                '_process_valid_pair_indices',
                return_value=0,
            ),
        ):
            _process_pairs(catalog, continue_scan=False, slurm_context={})

        self.assertGreaterEqual(len(call_order), 2)
        self.assertEqual(call_order[0], 'load_inventory')
        self.assertEqual(call_order[1], 'store_trace_metadata')

    def test_silence_worker_console_logging(self):
        """Worker logging setup should remove visible root handlers."""
        root_logger = logging.getLogger()
        original_handlers = list(root_logger.handlers)
        original_level = root_logger.level
        extra_handler = logging.StreamHandler(stream=sys.stderr)
        root_logger.addHandler(extra_handler)
        try:
            _silence_worker_console_logging()
            self.assertEqual(root_logger.level, logging.INFO)
            self.assertEqual(len(root_logger.handlers), 1)
            self.assertIsInstance(root_logger.handlers[0], logging.NullHandler)
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)

    def test_result_to_pair_record_logs_worker_messages_in_parent(self):
        """Forwarded worker messages should be logged by parent once."""
        result = {
            'status': 'no_waveform',
            'idx1': 0,
            'idx2': 1,
            'trace_id': 'WI.TDBA.00.HHZ',
            'message': 'worker failure detail',
            'fetch_dt': 0.0,
            'crosscorr_dt': 0.0,
            'worker_messages': (
                'worker warning one',
                'worker warning one',
                'worker failure detail',
            ),
        }
        catalog = [_DummyEvent('A'), _DummyEvent('B')]
        with patch.object(SCAN_CATALOG_MODULE.logger, 'warning') as warning:
            pair_record, fetch_dt, cc_dt = _result_to_pair_record(
                catalog,
                result,
            )
        self.assertEqual(pair_record.trace_id, 'WI.TDBA.00.HHZ')
        self.assertEqual(fetch_dt, 0.0)
        self.assertEqual(cc_dt, 0.0)
        messages = [call.args[0] for call in warning.call_args_list]
        self.assertEqual(
            messages,
            ['worker warning one', 'worker failure detail'],
        )

    def test_pair_processing_report_contains_benchmark_fields(self):
        """End report should include stable metrics for comparisons."""
        state = {
            'nprocs': 7,
            'initial_processed': 10,
            'total_pairs': 110,
            'waveform_fetch_time': 12.0,
            'crosscorr_time': 8.0,
        }
        with patch.object(SCAN_CATALOG_MODULE.logger, 'info') as info_log:
            _log_pair_processing_report(
                state,
                analyzed_pairs=100,
                elapsed=40.0,
            )
        self.assertEqual(info_log.call_count, 1)
        message = info_log.call_args.args[0]
        self.assertIn('Pair processing report:', message)
        self.assertIn('mode=parallel', message)
        self.assertIn('workers=7', message)
        self.assertIn('analyzed_pairs=100', message)
        self.assertIn('skipped_pairs=10', message)
        self.assertIn('total_pairs=110', message)
        self.assertIn('elapsed_s=40.000', message)
        self.assertIn('pairs_per_s=2.5', message)

    def test_parallel_cache_stats_collector_aggregates_workers(self):
        """Parallel cache collector should merge worker snapshots."""
        collector = _ParallelCacheStatsCollector()
        collector.update_from_result(
            {
                'worker_pid': 11,
                'worker_cache_stats': {
                    'trace_cache_hits': 10,
                    'trace_cache_misses': 5,
                    'sorted_trace_ids_cache_hits': 2,
                    'sorted_trace_ids_cache_misses': 2,
                    'skipped_trace_hits': 1,
                    'trace_cache_evictions': 0,
                    'trace_cache_size': 4,
                    'max_trace_cache_size': 100,
                    'disk_cache_hits': 7,
                    'disk_cache_misses': 1,
                    'disk_cache_writes': 0,
                    'disk_cache_read_errors': 0,
                    'disk_cache_write_errors': 0,
                },
            }
        )
        collector.update_from_result(
            {
                'worker_pid': 22,
                'worker_cache_stats': {
                    'trace_cache_hits': 30,
                    'trace_cache_misses': 10,
                    'sorted_trace_ids_cache_hits': 3,
                    'sorted_trace_ids_cache_misses': 1,
                    'skipped_trace_hits': 2,
                    'trace_cache_evictions': 1,
                    'trace_cache_size': 5,
                    'max_trace_cache_size': 100,
                    'disk_cache_hits': 10,
                    'disk_cache_misses': 3,
                    'disk_cache_writes': 1,
                    'disk_cache_read_errors': 0,
                    'disk_cache_write_errors': 0,
                },
            }
        )
        stats = collector.get_cache_stats()
        self.assertEqual(stats['trace_cache_hits'], 40)
        self.assertEqual(stats['trace_cache_misses'], 15)
        self.assertEqual(stats['trace_cache_size'], 9)
        self.assertEqual(stats['max_trace_cache_size'], 200)
        self.assertEqual(stats['disk_cache_hits'], 17)
        self.assertEqual(stats['disk_cache_misses'], 4)
        self.assertAlmostEqual(stats['trace_cache_hit_rate'], 40 / 55)


if __name__ == '__main__':
    unittest.main()
