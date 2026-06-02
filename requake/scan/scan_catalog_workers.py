# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Worker and pair-processing helpers for catalog-based repeater scans.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

from ..config import (
    config,
    from_picklable_config_dict,
    rq_exit,
    to_picklable_config_dict,
)
from ..database.pairs import PairRecord, write_pair_records
from ..waveforms import (
    MetadataMismatchError,
    NoMetadataError,
    NoWaveformError,
    WaveformPair,
    cc_waveform_pair,
)
from .scan_catalog_helpers import (
    init_pair_processing_state,
    init_progress_bar,
    log_pair_processing_report,
    log_cache_stats,
    log_pair_timing_split,
    progress_summary,
    update_noninteractive_progress,
)

logger = logging.getLogger('scan_catalog')

MIN_PENDING_FUTURES = 32
MAX_PENDING_MULTIPLIER = 2
MIN_WORKER_CACHE_SIZE = 2

_WORKER_WAVEFORM_PAIR = None
_WORKER_CATALOG = None


class _WorkerLogCaptureHandler(logging.Handler):
    """Collect worker log messages for parent-side emission."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        """Capture warning/error messages as single-line strings."""
        message = record.getMessage().replace('\n', ' ').strip()
        if message:
            self.messages.append(message)


class ParallelCacheStatsCollector:
    """Collect and aggregate cache stats snapshots from workers."""

    def __init__(self):
        """Initialize the per-worker cache-stats registry."""
        self._stats_by_pid = {}

    def update_from_result(self, result):
        """Store the latest cache-stats snapshot for a worker."""
        worker_pid = result.get('worker_pid')
        stats = result.get('worker_cache_stats')
        if worker_pid is None or stats is None:
            return
        self._stats_by_pid[worker_pid] = stats

    def get_cache_stats(self):
        """Return merged cache stats across all workers."""
        totals = {
            'trace_cache_hits': 0,
            'trace_cache_misses': 0,
            'sorted_trace_ids_cache_hits': 0,
            'sorted_trace_ids_cache_misses': 0,
            'skipped_trace_hits': 0,
            'trace_cache_evictions': 0,
            'trace_cache_size': 0,
            'max_trace_cache_size': 0,
            'disk_cache_hits': 0,
            'disk_cache_misses': 0,
            'disk_cache_writes': 0,
            'disk_cache_read_errors': 0,
            'disk_cache_write_errors': 0,
        }
        for stats in self._stats_by_pid.values():
            for key in totals:
                totals[key] += int(stats.get(key, 0))
        trace_lookups = (
            totals['trace_cache_hits'] + totals['trace_cache_misses']
        )
        sorted_lookups = (
            totals['sorted_trace_ids_cache_hits']
            + totals['sorted_trace_ids_cache_misses']
        )
        totals['trace_cache_hit_rate'] = (
            totals['trace_cache_hits'] / trace_lookups
            if trace_lookups > 0
            else 0.0
        )
        totals['sorted_trace_ids_cache_hit_rate'] = (
            totals['sorted_trace_ids_cache_hits'] / sorted_lookups
            if sorted_lookups > 0
            else 0.0
        )
        return totals


def effective_worker_cache_size(nprocs):
    """Return per-worker waveform cache size."""
    parallel_cache_size = int(
        getattr(config, 'catalog_waveform_cache_size_parallel', 0)
    )
    if parallel_cache_size > 0:
        return max(parallel_cache_size, MIN_WORKER_CACHE_SIZE)
    global_cache_size = max(
        int(getattr(config, 'catalog_waveform_cache_size', 5000)),
        MIN_WORKER_CACHE_SIZE,
    )
    return max(MIN_WORKER_CACHE_SIZE, global_cache_size // max(nprocs, 1))


def _connect_worker_clients():
    """Create process-local clients for worker processes."""
    if config.station_metadata_path is None:
        from obspy.clients.fdsn import Client as FDSNClient

        config.station_client = FDSNClient(config.fdsn_station_url)
    if config.sds_data_path is not None:
        from obspy.clients.filesystem.sds import Client as SDSClient

        config.dataselect_client = SDSClient(config.sds_data_path)
        return
    if config.event_data_path is not None:
        config.dataselect_client = None
        return
    from obspy.clients.fdsn import Client as FDSNClient

    config.dataselect_client = FDSNClient(config.fdsn_dataselect_url)


def silence_worker_console_logging():
    """Disable worker console logging to keep tqdm output stable."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.addHandler(logging.NullHandler())
    root_logger.setLevel(logging.INFO)


def _worker_initializer(cfg_dict, catalog, worker_cache_size):
    """Initialize process-local worker state."""
    global _WORKER_WAVEFORM_PAIR
    global _WORKER_CATALOG

    silence_worker_console_logging()
    restored_cfg = from_picklable_config_dict(cfg_dict)
    config.clear()
    config.update(restored_cfg)
    _connect_worker_clients()
    config.catalog_waveform_cache_size = worker_cache_size
    _WORKER_WAVEFORM_PAIR = WaveformPair()
    _WORKER_CATALOG = catalog


def _fix_trace_id(stats):
    """
    Fix trace_id in an ObsPy stats object by replacing dots.

    This makes trace_id compliant with the FDSN standard.

    The fixes are done in place.

    :param stats: ObsPy stats object
    :type stats: ObsPy AttribDict
    """
    stats.network = stats.network.replace('.', '_')
    stats.station = stats.station.replace('.', '_')
    stats.location = stats.location.replace('.', '_')
    stats.channel = stats.channel.replace('.', '_')


def _process_pair(pair, waveform_pair):
    """Process a single pair and return result plus timing."""
    t_fetch_start = time.monotonic()
    pair_st = waveform_pair.get_waveform_pair(pair)
    waveform_fetch_dt = time.monotonic() - t_fetch_start
    tr1, tr2 = pair_st.traces
    t_cc_start = time.monotonic()
    lag, _, cc_max = cc_waveform_pair(tr1, tr2)
    crosscorr_dt = time.monotonic() - t_cc_start
    _fix_trace_id(tr1.stats)
    _fix_trace_id(tr2.stats)
    return PairRecord(
        pair[0],
        pair[1],
        tr1.id,
        lag,
        cc_max,
        float(tr1.stats.sampling_rate),
    ), waveform_fetch_dt, crosscorr_dt


def worker_process_pair(idx_pair):
    """Process one pair index in a worker and return a compact payload."""
    root_logger = logging.getLogger()
    capture_handler = _WorkerLogCaptureHandler()
    root_logger.addHandler(capture_handler)
    idx1, idx2 = idx_pair
    pair = (_WORKER_CATALOG[idx1], _WORKER_CATALOG[idx2])
    try:
        pair_out, fetch_dt, crosscorr_dt = _process_pair(
            pair,
            _WORKER_WAVEFORM_PAIR,
        )
        root_logger.removeHandler(capture_handler)
        return {
            'status': 'ok',
            'idx1': idx1,
            'idx2': idx2,
            'worker_pid': os.getpid(),
            'trace_id': pair_out.trace_id,
            'lag_samples': pair_out.lag_samples,
            'cc_max': pair_out.cc_max,
            'sampling_rate_hz': pair_out.sampling_rate_hz,
            'fetch_dt': fetch_dt,
            'crosscorr_dt': crosscorr_dt,
            'worker_messages': tuple(capture_handler.messages),
            'worker_cache_stats': _WORKER_WAVEFORM_PAIR.get_cache_stats(),
        }
    except NoWaveformError as err:
        root_logger.removeHandler(capture_handler)
        return {
            'status': 'no_waveform',
            'idx1': idx1,
            'idx2': idx2,
            'worker_pid': os.getpid(),
            'trace_id': pair[0].trace_id,
            'message': str(err),
            'fetch_dt': 0.0,
            'crosscorr_dt': 0.0,
            'worker_messages': tuple(capture_handler.messages),
            'worker_cache_stats': _WORKER_WAVEFORM_PAIR.get_cache_stats(),
        }


def max_pending_futures(nprocs):
    """Return bounded number of in-flight futures."""
    return max(MIN_PENDING_FUTURES, MAX_PENDING_MULTIPLIER * nprocs)


def result_to_pair_record(catalog, result):
    """Convert worker payload to PairRecord and timings."""
    idx1 = result['idx1']
    idx2 = result['idx2']
    fetch_dt = result['fetch_dt']
    crosscorr_dt = result['crosscorr_dt']
    if result['status'] == 'ok':
        pair_record = PairRecord(
            catalog[idx1],
            catalog[idx2],
            result['trace_id'],
            result['lag_samples'],
            result['cc_max'],
            result['sampling_rate_hz'],
        )
        return pair_record, fetch_dt, crosscorr_dt
    seen_messages = set()
    for message in result.get('worker_messages', ()):
        if message in seen_messages:
            continue
        seen_messages.add(message)
        logger.warning(message)
    msg = result.get('message', '')
    if msg and msg not in seen_messages:
        logger.warning(msg)
    pair_record = PairRecord(
        catalog[idx1],
        catalog[idx2],
        result['trace_id'],
        None,
        None,
    )
    return pair_record, fetch_dt, crosscorr_dt


def _flush_pair_batch_if_needed(batch_of_pairs):
    """Flush pair batch when it reaches the configured chunk size."""
    if len(batch_of_pairs) >= 100:
        write_pair_records(batch_of_pairs, append=True)
        batch_of_pairs.clear()


def _finalize_pair_processing(
    batch_of_pairs,
    pbar,
    npairs,
    state,
    waveform_pair,
):
    """Flush pending rows and emit final processing logs."""
    if batch_of_pairs:
        write_pair_records(batch_of_pairs, append=True)
    if pbar is not None:
        pbar.close()
    elif npairs > 0:
        summary = progress_summary(
            state['total_pairs'],
            state['total_pairs'],
            state['start_time'],
        )
        logger.info(f'Processing pairs: {summary}')
    if npairs == 0:
        return
    total_elapsed = time.monotonic() - state['start_time']
    log_pair_timing_split(
        npairs,
        total_elapsed,
        state['waveform_fetch_time'],
        state['crosscorr_time'],
    )
    log_pair_processing_report(state, npairs, total_elapsed)
    log_cache_stats(waveform_pair)


def _process_and_store_pair(pair, waveform_pair, batch_of_pairs, state):
    """Process one pair and update batch/state counters."""
    pair_out, fetch_dt, crosscorr_dt = _process_pair(pair, waveform_pair)
    state['waveform_fetch_time'] += fetch_dt
    state['crosscorr_time'] += crosscorr_dt
    state['window_pair_count'] += 1
    state['window_fetch_time'] += fetch_dt
    state['window_crosscorr_time'] += crosscorr_dt
    batch_of_pairs.append(pair_out)
    _flush_pair_batch_if_needed(batch_of_pairs)


def _process_candidate_pair(pair, waveform_pair, batch_of_pairs, state):
    """Process one candidate pair and handle waveform-level errors."""
    try:
        _process_and_store_pair(
            pair,
            waveform_pair,
            batch_of_pairs,
            state,
        )
    except (NoMetadataError, MetadataMismatchError) as msg:
        logger.error(msg)
        rq_exit(1)
    except NoWaveformError as msg:
        if str(msg):
            logger.warning(msg)
        batch_of_pairs.append(
            PairRecord(pair[0], pair[1], pair[0].trace_id, None, None)
        )
        _flush_pair_batch_if_needed(batch_of_pairs)


def process_valid_pair_indices_parallel(
    catalog,
    valid_pair_idx,
    npairs,
    state,
    show_pbar,
    pbar,
):
    """Process valid pair indices using a bounded process pool."""
    nprocs = state['nprocs']
    worker_cache_size = effective_worker_cache_size(nprocs)
    logger.info(
        'Using parallel pair processing: '
        f'workers={nprocs:n}, '
        f'worker_cache_size={worker_cache_size:n}'
    )
    cache_stats = ParallelCacheStatsCollector()
    batch_of_pairs = []
    analyzed_pairs = 0
    max_pending = max_pending_futures(nprocs)
    cfg_dict = to_picklable_config_dict(config)
    pending = set()
    pair_iter = iter(valid_pair_idx)
    with ProcessPoolExecutor(
        max_workers=nprocs,
        initializer=_worker_initializer,
        initargs=(cfg_dict, tuple(catalog), worker_cache_size),
    ) as executor:
        while len(pending) < max_pending:
            try:
                idx_pair = next(pair_iter)
            except StopIteration:
                break
            pending.add(executor.submit(worker_process_pair, idx_pair))
        while pending:
            done, pending = wait(
                pending,
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                result = future.result()
                cache_stats.update_from_result(result)
                analyzed_pairs += 1
                if pbar is not None:
                    pbar.update()
                pair_record, fetch_dt, crosscorr_dt = result_to_pair_record(
                    catalog,
                    result,
                )
                state['waveform_fetch_time'] += fetch_dt
                state['crosscorr_time'] += crosscorr_dt
                state['window_pair_count'] += 1
                state['window_fetch_time'] += fetch_dt
                state['window_crosscorr_time'] += crosscorr_dt
                batch_of_pairs.append(pair_record)
                _flush_pair_batch_if_needed(batch_of_pairs)
                update_noninteractive_progress(
                    state,
                    cache_stats,
                    show_pbar,
                    analyzed_pairs,
                )
                try:
                    idx_pair = next(pair_iter)
                except StopIteration:
                    continue
                pending.add(executor.submit(worker_process_pair, idx_pair))
    _finalize_pair_processing(
        batch_of_pairs,
        pbar,
        analyzed_pairs,
        state,
        cache_stats,
    )
    return analyzed_pairs


def process_valid_pair_indices(
    catalog,
    valid_pair_idx,
    npairs,
    initial_processed=0,
    total_pairs=None,
    nprocs=1,
    slurm_context=None,
):
    """Process valid pairs from index pairs."""
    logger.info('Computing waveform cross-correlation...')
    state = init_pair_processing_state(
        npairs,
        initial_processed,
        total_pairs,
    )
    state['nprocs'] = nprocs
    state['slurm_context'] = slurm_context or {}
    show_pbar, pbar = init_progress_bar(state)
    if nprocs > 1 and npairs > 0:
        return process_valid_pair_indices_parallel(
            catalog,
            valid_pair_idx,
            npairs,
            state,
            show_pbar,
            pbar,
        )
    waveform_pair = WaveformPair()
    batch_of_pairs = []
    analyzed_pairs = 0
    for processed, (idx1, idx2) in enumerate(valid_pair_idx, start=1):
        update_noninteractive_progress(
            state,
            waveform_pair,
            show_pbar,
            processed,
        )
        pair = (catalog[idx1], catalog[idx2])
        analyzed_pairs += 1
        if pbar is not None:
            pbar.update()
        _process_candidate_pair(
            pair,
            waveform_pair,
            batch_of_pairs,
            state,
        )
    _finalize_pair_processing(
        batch_of_pairs,
        pbar,
        analyzed_pairs,
        state,
        waveform_pair,
    )
    return analyzed_pairs
