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
from requake.scan.scan_catalog import _process_pairs
from requake.scan.scan_catalog_pairs import load_existing_pair_ids
from requake.scan.scan_catalog_helpers import (
    init_progress_bar,
    log_pair_processing_report,
    resolve_scan_catalog_nprocs,
)
from requake.scan.slurm_diagnostics import (
    slurm_get_context,
    slurm_progress_suffix,
)
from requake.scan.scan_catalog_workers import (
    _ParallelCacheStatsCollector,
    _effective_worker_cache_size,
    _max_pending_futures,
    process_valid_pair_indices,
    _result_to_pair_record,
    _silence_worker_console_logging,
)

SCAN_CATALOG_MODULE = importlib.import_module('requake.scan.scan_catalog')
PAIRS_MODULE = importlib.import_module('requake.scan.scan_catalog_pairs')
RUNTIME_MODULE = importlib.import_module('requake.scan.scan_catalog_helpers')
WORKERS_MODULE = importlib.import_module('requake.scan.scan_catalog_workers')


class _DummyEvent:
    """Minimal event object used by scan_catalog helper tests."""

    def __init__(self, evid):
        self.evid = evid


class _FakeFuture:
    """Simple future stub returning a precomputed result."""

    def __init__(self, result, executor):
        self._result = result
        self._executor = executor

    def result(self):
        return self._result


class _RecordingExecutor:
    """Executor stub recording max in-flight submissions."""

    max_pending_seen = 0

    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.pending = set()
        _RecordingExecutor.max_pending_seen = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def submit(self, fn, idx_pair):
        del fn
        idx1, idx2 = idx_pair
        future = _FakeFuture(
            {
                'status': 'ok',
                'idx1': int(idx1),
                'idx2': int(idx2),
                'worker_pid': 100 + int(idx1),
                'trace_id': 'WI.TDBA.00.HHZ',
                'lag_samples': 0,
                'cc_max': 1.0,
                'sampling_rate_hz': 100.0,
                'fetch_dt': 0.0,
                'crosscorr_dt': 0.0,
                'worker_messages': (),
                'worker_cache_stats': {},
            },
            self,
        )
        self.pending.add(future)
        _RecordingExecutor.max_pending_seen = max(
            _RecordingExecutor.max_pending_seen,
            len(self.pending),
        )
        return future


class _DummyConfig:
    """Config stub used by scan_catalog helper tests."""

    def __init__(self):
        self.args = SimpleNamespace(traceid=None)
        self.catalog_trace_id = ['WI.TDBA.00.HHZ']


class TestScanCatalogResume(unittest.TestCase):
    """Test scan_catalog resume and overwrite selection features."""

    @staticmethod
    def _resolve_nprocs(nprocs, npairs, slurm_context=None):
        """Resolve nprocs with a config stub patched in."""
        dummy_config = SimpleNamespace(
            args=SimpleNamespace(nprocs=nprocs),
            catalog_scan_nprocs=0,
        )
        with patch.object(RUNTIME_MODULE, 'config', dummy_config):
            return resolve_scan_catalog_nprocs(npairs, slurm_context or {})

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
        nevents = len(catalog)
        packed = {0 * nevents + 1, 1 * nevents + 2}
        with patch.object(
            PAIRS_MODULE,
            'read_event_key_rows',
            return_value=event_keys,
        ), patch.object(
            PAIRS_MODULE,
            'read_packed_pair_ids',
            return_value=packed,
        ):
            existing_ids = load_existing_pair_ids(catalog)
        self.assertEqual(existing_ids, packed)

    def test_noninteractive_progress_uses_total_pair_count(self):
        """Resume progress log should use total pairs, not remaining."""
        with patch.object(
            WORKERS_MODULE,
            'init_progress_bar',
            return_value=(False, None),
        ), patch.object(
            WORKERS_MODULE,
            'update_noninteractive_progress',
        ) as update_progress, patch.object(
            WORKERS_MODULE,
            '_process_pair',
            side_effect=AssertionError('No pairs should be processed'),
        ), patch.object(
            WORKERS_MODULE,
            'WaveformPair',
            return_value=MagicMock(),
        ), patch.object(
            WORKERS_MODULE,
            'write_pair_records',
        ):
            process_valid_pair_indices(
                catalog=[],
                valid_pair_idx=np.empty((0, 2), dtype=np.int32),
                npairs=0,
                initial_processed=7,
                total_pairs=10,
            )
        self.assertFalse(update_progress.called)

    def test_tqdm_uses_total_and_initial_on_resume(self):
        """Resume progress bar should initialize with total and offset."""
        with patch.object(
            RUNTIME_MODULE.sys.stderr,
            'isatty',
            return_value=True,
        ), patch.object(
            RUNTIME_MODULE,
            'tqdm',
        ) as tqdm_mock:
            tqdm_mock.return_value = MagicMock()
            init_progress_bar(
                {
                    'nprocs': 1,
                    'total_pairs': 40,
                    'initial_processed': 12,
                }
            )
        kwargs = tqdm_mock.call_args.kwargs
        self.assertEqual(kwargs['total'], 40)
        self.assertEqual(kwargs['initial'], 12)

    def test_resolve_nprocs_prefers_cli(self):
        """CLI nprocs should override config value."""
        resolved = self._resolve_nprocs(nprocs=3, npairs=100)
        self.assertEqual(resolved, 3)

    def test_resolve_nprocs_auto_slurm(self):
        """Auto nprocs should use Slurm cpus per task."""
        resolved = self._resolve_nprocs(
            nprocs=None, npairs=100,
            slurm_context={'SLURM_CPUS_PER_TASK': '8'},
        )
        self.assertEqual(resolved, 8)

    def test_resolve_nprocs_clamps_to_pair_count(self):
        """Resolved workers should be clamped to pair count."""
        resolved = self._resolve_nprocs(nprocs=32, npairs=5)
        self.assertEqual(resolved, 5)

    def test_resolve_nprocs_uses_slurm_cpus_on_node(self):
        """Automatic nprocs should use SLURM_CPUS_ON_NODE."""
        resolved = self._resolve_nprocs(
            nprocs=None, npairs=100,
            slurm_context={'SLURM_CPUS_ON_NODE': '12'},
        )
        self.assertEqual(resolved, 12)

    def test_resolve_nprocs_parses_job_cpus_per_node(self):
        """Automatic nprocs should parse SLURM_JOB_CPUS_PER_NODE."""
        resolved = self._resolve_nprocs(
            nprocs=None, npairs=100,
            slurm_context={'SLURM_JOB_CPUS_PER_NODE': '8(x2),4'},
        )
        self.assertEqual(resolved, 8)

    def test_get_slurm_context_returns_only_set_values(self):
        """Slurm context should include only environment variables set."""
        env = {
            'SLURM_JOB_ID': '1234',
            'SLURM_CPUS_PER_TASK': '12',
            'SLURM_NODELIST': 'node001',
        }
        with patch.dict(RUNTIME_MODULE.os.environ, env, clear=True):
            context = slurm_get_context()
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
        suffix = slurm_progress_suffix(context)
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
        with patch.object(WORKERS_MODULE, 'config', dummy_config):
            size = _effective_worker_cache_size(7)
        self.assertEqual(size, 714)

    def test_effective_worker_cache_size_parallel_override(self):
        """Parallel override should set per-worker cache size directly."""
        dummy_config = SimpleNamespace(
            catalog_waveform_cache_size=5000,
            catalog_waveform_cache_size_parallel=1200,
        )
        with patch.object(WORKERS_MODULE, 'config', dummy_config):
            size = _effective_worker_cache_size(7)
        self.assertEqual(size, 1200)

    def test_process_valid_pair_indices_uses_parallel_branch(self):
        """nprocs>1 should route processing through parallel helper."""
        with patch.object(
            WORKERS_MODULE,
            'init_progress_bar',
            return_value=(False, None),
        ), patch.object(
            WORKERS_MODULE,
            '_process_valid_pair_indices_parallel',
            return_value=11,
        ) as parallel_mock:
            result = process_valid_pair_indices(
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
                'build_valid_pair_indices',
                return_value=valid_pair_idx,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                'resolve_scan_catalog_nprocs',
                return_value=1,
            ),
            patch.object(
                SCAN_CATALOG_MODULE,
                'process_valid_pair_indices',
                return_value=0,
            ),
        ):
            _process_pairs(catalog, continue_scan=False, slurm_context={})

        self.assertGreaterEqual(len(call_order), 2)
        self.assertEqual(call_order[0], 'load_inventory')
        self.assertEqual(call_order[1], 'store_trace_metadata')

    def test_worker_process_pair_returns_compact_payload(self):
        """Worker payload should contain only compact scalar-like fields."""
        dummy_pair_record = SimpleNamespace(
            trace_id='WI.TDBA.00.HHZ',
            lag_samples=12,
            cc_max=0.95,
            sampling_rate_hz=100.0,
        )
        waveform_pair = MagicMock()
        waveform_pair.get_cache_stats.return_value = {
            'trace_cache_hits': 1,
            'trace_cache_misses': 1,
            'trace_cache_hit_rate': 0.5,
            'sorted_trace_ids_cache_hits': 0,
            'sorted_trace_ids_cache_misses': 0,
            'sorted_trace_ids_cache_hit_rate': 0.0,
            'skipped_trace_hits': 0,
            'trace_cache_evictions': 0,
            'trace_cache_size': 1,
            'max_trace_cache_size': 10,
            'disk_cache_hits': 0,
            'disk_cache_misses': 0,
            'disk_cache_writes': 0,
            'disk_cache_read_errors': 0,
            'disk_cache_write_errors': 0,
        }
        with patch.object(
            WORKERS_MODULE,
            '_WORKER_WAVEFORM_PAIR',
            waveform_pair,
        ), patch.object(
            WORKERS_MODULE,
            '_WORKER_CATALOG',
            [_DummyEvent('A'), _DummyEvent('B')],
        ), patch.object(
            WORKERS_MODULE,
            '_process_pair',
            return_value=(dummy_pair_record, 0.1, 0.2),
        ), patch.object(WORKERS_MODULE.os, 'getpid', return_value=321):
            result = WORKERS_MODULE._worker_process_pair((0, 1))
        self.assertEqual(result['idx1'], 0)
        self.assertEqual(result['idx2'], 1)
        self.assertEqual(result['worker_pid'], 321)
        self.assertIsInstance(result['trace_id'], str)
        self.assertIsInstance(result['lag_samples'], int)
        self.assertIsInstance(result['cc_max'], float)
        self.assertIsInstance(result['sampling_rate_hz'], float)
        self.assertIsInstance(result['worker_messages'], tuple)
        self.assertIsInstance(result['worker_cache_stats'], dict)

    def test_parallel_path_bounds_pending_futures(self):
        """Parallel scheduler should never exceed max_pending futures."""
        valid_pair_idx = np.array([[idx, idx + 1] for idx in range(40)])
        catalog = [_DummyEvent(f'ev_{idx}') for idx in range(41)]
        state = {
            'nprocs': 2,
            'initial_processed': 0,
            'total_pairs': len(valid_pair_idx),
            'waveform_fetch_time': 0.0,
            'crosscorr_time': 0.0,
            'window_pair_count': 0,
            'window_fetch_time': 0.0,
            'window_crosscorr_time': 0.0,
            'next_log_time': 0.0,
            'window_start_time': 0.0,
            'slurm_context': {},
            'start_time': 0.0,
        }

        def _fake_wait(pending, return_when):
            del return_when
            future = next(iter(pending))
            pending.remove(future)
            future._executor.pending.remove(future)
            return {future}, pending

        with patch.object(
            WORKERS_MODULE,
            'ProcessPoolExecutor',
            _RecordingExecutor,
        ), patch.object(
            WORKERS_MODULE,
            'wait',
            side_effect=_fake_wait,
        ), patch.object(
            WORKERS_MODULE,
            'to_picklable_config_dict',
            return_value={},
        ), patch.object(
            WORKERS_MODULE,
            '_effective_worker_cache_size',
            return_value=100,
        ), patch.object(
            WORKERS_MODULE,
            'update_noninteractive_progress',
        ), patch.object(
            WORKERS_MODULE,
            '_finalize_pair_processing',
        ), patch.object(
            WORKERS_MODULE,
            '_flush_pair_batch_if_needed',
        ):
            analyzed = (
                WORKERS_MODULE._process_valid_pair_indices_parallel(
                    catalog,
                    valid_pair_idx,
                    len(valid_pair_idx),
                    state,
                    show_pbar=False,
                    pbar=None,
                )
            )
        self.assertEqual(analyzed, len(valid_pair_idx))
        self.assertLessEqual(
            _RecordingExecutor.max_pending_seen,
            WORKERS_MODULE._max_pending_futures(2),
        )

    def test_parallel_path_flushes_batches_at_threshold(self):
        """Parallel path should flush parent batches at the fixed threshold."""
        valid_pair_idx = np.array([[idx, idx + 1] for idx in range(105)])
        catalog = [_DummyEvent(f'ev_{idx}') for idx in range(106)]
        state = {
            'nprocs': 2,
            'initial_processed': 0,
            'total_pairs': len(valid_pair_idx),
            'waveform_fetch_time': 0.0,
            'crosscorr_time': 0.0,
            'window_pair_count': 0,
            'window_fetch_time': 0.0,
            'window_crosscorr_time': 0.0,
            'next_log_time': 0.0,
            'window_start_time': 0.0,
            'slurm_context': {},
            'start_time': 0.0,
        }
        flush_lengths = []

        def _fake_wait(pending, return_when):
            del return_when
            future = next(iter(pending))
            pending.remove(future)
            future._executor.pending.remove(future)
            return {future}, pending

        def _record_write_pair_records(pairs, append=True):
            del append
            flush_lengths.append(len(pairs))

        def _record_finalize(batch_of_pairs, pbar, npairs, state_arg, cache):
            del pbar, npairs, state_arg, cache
            flush_lengths.append(len(batch_of_pairs))

        with patch.object(
            WORKERS_MODULE,
            'ProcessPoolExecutor',
            _RecordingExecutor,
        ), patch.object(
            WORKERS_MODULE,
            'wait',
            side_effect=_fake_wait,
        ), patch.object(
            WORKERS_MODULE,
            'to_picklable_config_dict',
            return_value={},
        ), patch.object(
            WORKERS_MODULE,
            '_effective_worker_cache_size',
            return_value=100,
        ), patch.object(
            WORKERS_MODULE,
            'update_noninteractive_progress',
        ), patch.object(
            WORKERS_MODULE,
            'write_pair_records',
            side_effect=_record_write_pair_records,
        ), patch.object(
            WORKERS_MODULE,
            '_finalize_pair_processing',
            side_effect=_record_finalize,
        ):
            WORKERS_MODULE._process_valid_pair_indices_parallel(
                catalog,
                valid_pair_idx,
                len(valid_pair_idx),
                state,
                show_pbar=False,
                pbar=None,
            )
        self.assertEqual(flush_lengths[0], 100)
        self.assertEqual(flush_lengths[-1], 5)

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
        with patch.object(WORKERS_MODULE.logger, 'warning') as warning:
            pair_record, fetch_dt, cc_dt = _result_to_pair_record(
                catalog,
                result,
            )
        self.assertEqual(pair_record.trace_id, 'WI.TDBA.00.HHZ')
        self.assertEqual(fetch_dt, 0.0)
        self.assertEqual(cc_dt, 0.0)
        messages = [call.args[0] for call in warning.call_args_list]
        self.assertIn('worker warning one', messages[0])
        self.assertIn('worker failure detail', messages[1])

    def test_pair_processing_report_contains_benchmark_fields(self):
        """End report should include stable metrics for comparisons."""
        state = {
            'nprocs': 7,
            'initial_processed': 10,
            'total_pairs': 110,
            'waveform_fetch_time': 12.0,
            'crosscorr_time': 8.0,
        }
        with patch.object(RUNTIME_MODULE.logger, 'info') as info_log:
            log_pair_processing_report(
                state,
                analyzed_pairs=100,
                elapsed=40.0,
            )
        self.assertEqual(info_log.call_count, 1)
        message = info_log.call_args.args[0]
        self.assertIn('[rq:report] Pair processing report:', message)
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
