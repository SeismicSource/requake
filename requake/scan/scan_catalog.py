# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import os
import math
import time
import logging
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import numpy as np
from tqdm import tqdm
from scipy.spatial import cKDTree
from ..config import (
    config,
    rq_exit,
    to_picklable_config_dict,
    from_picklable_config_dict,
)
from ..database.db import get_db_path
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..database.pairs import (
    PairRecord,
    count_pairs,
    read_event_key_rows,
    read_pair_key_ids,
    write_pair_records,
)
from ..database.trace_metadata import store_trace_metadata_from_inventory
from ..waveforms import (
    WaveformPair, cc_waveform_pair,
    load_inventory,
    NoWaveformError, NoMetadataError, MetadataMismatchError
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
EARTH_RADIUS_KM = 6371.0088
SLURM_CONTEXT_KEYS = (
    'SLURM_JOB_ID',
    'SLURM_JOB_NAME',
    'SLURM_CLUSTER_NAME',
    'SLURM_CPUS_PER_TASK',
    'SLURM_NTASKS',
    'SLURM_PROCID',
    'SLURM_NODELIST',
    'SLURM_MEM_PER_CPU',
    'SLURM_MEM_PER_NODE',
)
SLURM_PROGRESS_KEYS = (
    'SLURM_JOB_ID',
    'SLURM_PROCID',
    'SLURM_NODELIST',
)
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


class _ParallelCacheStatsCollector:
    """Collect and aggregate cache stats snapshots from workers."""

    def __init__(self):
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


def _get_slurm_context():
    """Return current Slurm environment variables that are set."""
    context = {}
    for key in SLURM_CONTEXT_KEYS:
        value = os.environ.get(key)
        if value:
            context[key] = value
    return context


def _log_slurm_runtime_context(slurm_context):
    """Log Slurm runtime details when available."""
    if not slurm_context:
        return
    details = ', '.join(
        f'{key}={slurm_context[key]}'
        for key in SLURM_CONTEXT_KEYS
        if key in slurm_context
    )
    logger.info(f'Slurm runtime context: {details}')


def _slurm_progress_suffix(slurm_context):
    """Build compact Slurm suffix for periodic progress logs."""
    if not slurm_context:
        return ''
    details = ', '.join(
        f'{key}={slurm_context[key]}'
        for key in SLURM_PROGRESS_KEYS
        if key in slurm_context
    )
    return f', {details}' if details else ''


def _available_cpu_count():
    """Return available CPU count, preferring affinity when supported."""
    if hasattr(os, 'sched_getaffinity'):
        try:
            return len(os.sched_getaffinity(0))
        except OSError:
            pass
    return os.cpu_count() or 1


def _resolve_scan_catalog_nprocs(npairs, slurm_context):
    """Resolve effective worker count for scan_catalog."""
    cli_nprocs = getattr(config.args, 'nprocs', None)
    config_nprocs = getattr(config, 'catalog_scan_nprocs', 0)
    requested = cli_nprocs if cli_nprocs is not None else config_nprocs
    if requested < 0:
        logger.error('catalog_scan_nprocs must be >= 0')
        rq_exit(1)
    if requested == 0:
        slurm_cpus = slurm_context.get('SLURM_CPUS_PER_TASK')
        if slurm_cpus is not None:
            try:
                base_nprocs = int(slurm_cpus)
            except ValueError:
                logger.warning(
                    'Invalid SLURM_CPUS_PER_TASK value '
                    f'{slurm_cpus!r}; using host CPU count instead'
                )
                base_nprocs = _available_cpu_count()
        else:
            base_nprocs = _available_cpu_count()
            if base_nprocs > 1:
                base_nprocs -= 1
    else:
        base_nprocs = requested
    max_workers = max(1, npairs)
    effective_nprocs = min(max(1, base_nprocs), max_workers)
    logger.info(
        'scan_catalog workers: '
        f'requested={requested:n}, effective={effective_nprocs:n}'
    )
    return effective_nprocs


def _effective_worker_cache_size(nprocs):
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


def _silence_worker_console_logging():
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

    _silence_worker_console_logging()
    restored_cfg = from_picklable_config_dict(cfg_dict)
    config.clear()
    config.update(restored_cfg)
    _connect_worker_clients()
    config.catalog_waveform_cache_size = worker_cache_size
    _WORKER_WAVEFORM_PAIR = WaveformPair()
    _WORKER_CATALOG = catalog


def _worker_process_pair(idx_pair):
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


def _max_pending_futures(nprocs):
    """Return bounded number of in-flight futures."""
    return max(MIN_PENDING_FUTURES, MAX_PENDING_MULTIPLIER * nprocs)


def _result_to_pair_record(catalog, result):
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


def _process_valid_pair_indices_parallel(
    catalog,
    valid_pair_idx,
    npairs,
    state,
    show_pbar,
    pbar,
):
    """Process valid pair indices using a bounded process pool."""
    nprocs = state['nprocs']
    worker_cache_size = _effective_worker_cache_size(nprocs)
    logger.info(
        'Using parallel pair processing: '
        f'workers={nprocs:n}, '
        f'worker_cache_size={worker_cache_size:n}'
    )
    cache_stats = _ParallelCacheStatsCollector()
    batch_of_pairs = []
    analyzed_pairs = 0
    max_pending = _max_pending_futures(nprocs)
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
            pending.add(executor.submit(_worker_process_pair, idx_pair))
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
                pair_record, fetch_dt, crosscorr_dt = _result_to_pair_record(
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
                _update_noninteractive_progress(
                    state,
                    cache_stats,
                    show_pbar,
                    analyzed_pairs,
                )
                try:
                    idx_pair = next(pair_iter)
                except StopIteration:
                    continue
                pending.add(executor.submit(_worker_process_pair, idx_pair))
    _finalize_pair_processing(
        batch_of_pairs,
        pbar,
        analyzed_pairs,
        state,
        cache_stats,
    )
    return analyzed_pairs


def _build_spatial_index(catalog):
    """Build and return KD-tree spatial index inputs."""
    range_km = config.catalog_search_range
    if range_km <= 0:
        return None, None, None
    lats = np.array([ev.lat for ev in catalog], dtype=float)
    lons = np.array([ev.lon for ev in catalog], dtype=float)
    lat_rad = np.radians(lats)
    lon_rad = np.radians(lons)
    cos_lat = np.cos(lat_rad)
    coords = np.column_stack(
        (
            cos_lat * np.cos(lon_rad),
            cos_lat * np.sin(lon_rad),
            np.sin(lat_rad),
        )
    )
    tree = cKDTree(coords)
    angular_dist = range_km / EARTH_RADIUS_KM
    chord_dist = 2.0 * math.sin(angular_dist / 2.0)
    return coords, tree, chord_dist


def _build_valid_pair_indices(catalog):
    """Build grouped event-pair indices using int32 storage."""
    nevents = len(catalog)
    coords, tree, chord_dist = _build_spatial_index(catalog)
    if coords is None:
        return np.empty((0, 2), dtype=np.int32)
    logger.info('Grouping valid pairs while building the spatial index...')
    counts = np.empty(nevents, dtype=np.int32)
    grouped_seconds = []
    npairs = 0
    for idx, coord in enumerate(coords):
        neighbors = np.asarray(
            tree.query_ball_point(coord, chord_dist),
            dtype=np.int32
        )
        neighbors = neighbors[neighbors > idx]
        grouped_seconds.append(neighbors)
        n_neighbors = len(neighbors)
        counts[idx] = n_neighbors
        npairs += n_neighbors
    if npairs == 0:
        return np.empty((0, 2), dtype=np.int32)
    pair_idx = np.empty((npairs, 2), dtype=np.int32)
    offsets = np.empty(nevents + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    for idx, neighbors in enumerate(grouped_seconds):
        if counts[idx] == 0:
            continue
        start = offsets[idx]
        stop = offsets[idx + 1]
        pair_idx[start:stop, 0] = idx
        pair_idx[start:stop, 1] = neighbors
    return pair_idx


def _progress_summary(current, total, start_time):
    """Return a compact progress summary string."""
    elapsed = max(time.monotonic() - start_time, 1e-9)
    rate = current / elapsed
    percent = 100.0 * current / total if total else 0.0
    return (
        f'{current:n}/{total:n} ({percent:.1f}%) '
        f'[{rate:,.0f} pairs/s]'
    )


def _log_pair_grouping_stats(valid_pair_idx):
    """Log whether pairs are grouped by first event."""
    npairs = len(valid_pair_idx)
    if npairs == 0:
        logger.info('Pair grouping: no pairs to verify')
        return
    first = valid_pair_idx[:, 0]
    if npairs == 1:
        logger.info('Pair grouping: single pair, grouping is trivial')
        return
    monotonic = bool(np.all(first[:-1] <= first[1:]))
    boundaries = np.flatnonzero(first[1:] != first[:-1]) + 1
    run_lengths = np.diff(np.concatenate(([0], boundaries, [npairs])))
    logger.info(
        'Pair grouping: '
        f'monotonic_first={monotonic}, '
        f'first-event groups={len(run_lengths):n}, '
        f'avg consecutive pairs per first event='
        f'{run_lengths.mean():.1f}, '
        f'median consecutive pairs per first event='
        f'{np.median(run_lengths):.1f}, '
        f'max consecutive pairs per first event='
        f'{run_lengths.max():n}'
    )
    if not monotonic:
        logger.warning(
            'Pairs are not grouped by first event; waveform reuse may be '
            'degraded.'
        )


def _log_pair_timing_split(
    pair_count,
    elapsed,
    waveform_fetch_time,
    crosscorr_time,
):
    """Log average timing split per pair."""
    if pair_count <= 0:
        return
    avg_elapsed = elapsed / pair_count
    avg_fetch = waveform_fetch_time / pair_count
    avg_crosscorr = crosscorr_time / pair_count
    avg_other = max(avg_elapsed - avg_fetch - avg_crosscorr, 0.0)
    logger.info(
        'Timing split per pair: '
        f'fetch={avg_fetch:.3f}s, '
        f'cc={avg_crosscorr:.3f}s, '
        f'other={avg_other:.3f}s '
        f'(window={pair_count:n} pairs, '
        f'{elapsed:.1f}s total)'
    )


def _log_pair_processing_report(state, analyzed_pairs, elapsed):
    """Log a benchmark-friendly end-of-run processing report."""
    mode = 'serial' if state['nprocs'] == 1 else 'parallel'
    elapsed = max(elapsed, 1e-9)
    rate = analyzed_pairs / elapsed
    avg_fetch = state['waveform_fetch_time'] / analyzed_pairs
    avg_cc = state['crosscorr_time'] / analyzed_pairs
    avg_other = max(elapsed / analyzed_pairs - avg_fetch - avg_cc, 0.0)
    logger.info(
        'Pair processing report: '
        f'mode={mode}, '
        f'workers={state["nprocs"]:n}, '
        f'analyzed_pairs={analyzed_pairs:n}, '
        f'skipped_pairs={state["initial_processed"]:n}, '
        f'total_pairs={state["total_pairs"]:n}, '
        f'elapsed_s={elapsed:.3f}, '
        f'pairs_per_s={rate:.1f}, '
        f'avg_fetch_s={avg_fetch:.4f}, '
        f'avg_cc_s={avg_cc:.4f}, '
        f'avg_other_s={avg_other:.4f}'
    )


def _log_cache_stats(waveform_pair):
    """Log waveform cache hit-rate statistics."""
    stats = waveform_pair.get_cache_stats()
    logger.info(
        'Cache stats: '
        f'trace hits={stats["trace_cache_hits"]:n}, '
        f'misses={stats["trace_cache_misses"]:n}, '
        f'hit rate={stats["trace_cache_hit_rate"]:.1%}, '
        f'sorted-trace-id hits={stats["sorted_trace_ids_cache_hits"]:n}, '
        f'misses={stats["sorted_trace_ids_cache_misses"]:n}, '
        f'hit rate={stats["sorted_trace_ids_cache_hit_rate"]:.1%}, '
        f'skipped-pair hits={stats["skipped_trace_hits"]:n}, '
        f'cache evictions={stats["trace_cache_evictions"]:n}, '
        f'cache size={stats["trace_cache_size"]:n}/'
        f'{stats["max_trace_cache_size"]:n}'
    )
    logger.info(
        'Disk cache stats: '
        f'hits={stats["disk_cache_hits"]:n}, '
        f'misses={stats["disk_cache_misses"]:n}, '
        f'writes={stats["disk_cache_writes"]:n}, '
        f'read errors={stats["disk_cache_read_errors"]:n}, '
        f'write errors={stats["disk_cache_write_errors"]:n}'
    )


def _log_noninteractive_progress(
    processed,
    npairs,
    window_start_time,
    next_log_time,
    window_pair_count,
    window_fetch_time,
    window_crosscorr_time,
    waveform_pair,
    nprocs,
    slurm_context,
):
    """Log non-interactive progress periodically and return next log time."""
    if time.monotonic() < next_log_time:
        return next_log_time
    slurm_suffix = _slurm_progress_suffix(slurm_context)
    logger.info(
        'Processing pairs: '
        f'{_progress_summary(processed, npairs, window_start_time)} '
        f'[workers={nprocs:n}{slurm_suffix}]'
    )
    _log_pair_timing_split(
        window_pair_count,
        time.monotonic() - window_start_time,
        window_fetch_time,
        window_crosscorr_time,
    )
    _log_cache_stats(waveform_pair)
    return next_log_time + 60.0


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


def _init_pair_processing_state(npairs, initial_processed, total_pairs):
    """Build mutable state for pair processing."""
    if total_pairs is None:
        total_pairs = npairs
    start_time = time.monotonic()
    return {
        'start_time': start_time,
        'next_log_time': start_time + 60.0,
        'waveform_fetch_time': 0.0,
        'crosscorr_time': 0.0,
        'window_start_time': start_time,
        'window_pair_count': 0,
        'window_fetch_time': 0.0,
        'window_crosscorr_time': 0.0,
        'initial_processed': initial_processed,
        'total_pairs': total_pairs,
        'nprocs': 1,
        'slurm_context': {},
    }


def _init_progress_bar(state):
    """Initialize progress bar and return (show_pbar, pbar)."""
    show_pbar = sys.stderr.isatty()
    if not show_pbar:
        return show_pbar, None
    pbar = tqdm(
        total=state['total_pairs'],
        unit='pairs',
        unit_scale=True,
        desc=f'Processing {state["total_pairs"]:n} event pairs',
        initial=state['initial_processed'],
    )
    mode = 'serial' if state['nprocs'] == 1 else 'parallel'
    pbar.set_postfix_str(f'workers={state["nprocs"]:n} mode={mode}')
    return show_pbar, pbar


def _update_noninteractive_progress(
    state,
    waveform_pair,
    show_pbar,
    processed,
):
    """Periodically log progress in non-interactive mode."""
    if show_pbar:
        return
    processed_total = state['initial_processed'] + processed
    state['next_log_time'] = _log_noninteractive_progress(
        processed_total,
        state['total_pairs'],
        state['window_start_time'],
        state['next_log_time'],
        state['window_pair_count'],
        state['window_fetch_time'],
        state['window_crosscorr_time'],
        waveform_pair,
        state['nprocs'],
        state['slurm_context'],
    )
    state['window_start_time'] = time.monotonic()
    state['window_pair_count'] = 0
    state['window_fetch_time'] = 0.0
    state['window_crosscorr_time'] = 0.0


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
        # Do not print empty messages
        if str(msg):
            logger.warning(msg)
        batch_of_pairs.append(
            PairRecord(pair[0], pair[1], pair[0].trace_id, None, None)
        )
        _flush_pair_batch_if_needed(batch_of_pairs)


def _mask_existing_pair_indices(valid_pair_idx, existing_pair_ids, nevents):
    """Drop candidate pairs already present in storage."""
    if not existing_pair_ids or len(valid_pair_idx) == 0:
        return valid_pair_idx, 0
    t_mask_start = time.monotonic()
    logger.info('Masking already processed pairs before processing...')
    nevents_u64 = np.uint64(nevents)
    existing_ids = np.fromiter(
        existing_pair_ids,
        dtype=np.uint64,
        count=len(existing_pair_ids),
    )
    candidate_ids = (
        valid_pair_idx[:, 0].astype(np.uint64) * nevents_u64
        + valid_pair_idx[:, 1].astype(np.uint64)
    )
    keep = ~np.isin(candidate_ids, existing_ids)
    skipped = int((~keep).sum())
    filtered = valid_pair_idx[keep]
    mask_dt = time.monotonic() - t_mask_start
    logger.info(
        f'Existing-pair masking completed in {mask_dt:.1f}s'
    )
    return filtered, skipped


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
        summary = _progress_summary(
            state['total_pairs'],
            state['total_pairs'],
            state['start_time'],
        )
        logger.info(
            f'Processing pairs: {summary}'
        )
    if npairs == 0:
        return
    total_elapsed = time.monotonic() - state['start_time']
    _log_pair_timing_split(
        npairs,
        total_elapsed,
        state['waveform_fetch_time'],
        state['crosscorr_time'],
    )
    _log_pair_processing_report(state, npairs, total_elapsed)
    _log_cache_stats(waveform_pair)


def _process_valid_pair_indices(
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
    state = _init_pair_processing_state(npairs, initial_processed, total_pairs)
    state['nprocs'] = nprocs
    state['slurm_context'] = slurm_context or {}
    show_pbar, pbar = _init_progress_bar(state)
    if nprocs > 1 and npairs > 0:
        return _process_valid_pair_indices_parallel(
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
        _update_noninteractive_progress(
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


def _load_existing_pair_ids(catalog):
    """Return packed pair IDs already present in the database."""
    t_read_keys_start = time.monotonic()
    logger.info(
        'Loading existing pair key IDs from db file... '
    )
    event_key_rows = read_event_key_rows()
    existing_pair_key_ids = read_pair_key_ids()
    read_keys_dt = time.monotonic() - t_read_keys_start
    logger.info(
        f'{len(existing_pair_key_ids):n} unique pairs loaded '
        f'in {read_keys_dt:.1f}s '
    )
    if not existing_pair_key_ids:
        return set()
    t_build_id_start = time.monotonic()
    logger.info(
        'Building existing pair IDs for quick lookup... '
    )
    evid_to_idx = {
        ev.evid: idx for idx, ev in enumerate(catalog)
    }
    event_id_to_idx = {}
    for event_id, evid in event_key_rows:
        idx = evid_to_idx.get(evid)
        if idx is not None:
            event_id_to_idx[event_id] = idx
    get_idx = event_id_to_idx.get
    nevents = len(catalog)
    existing_ids = set()
    add_id = existing_ids.add
    for event1_id, event2_id in existing_pair_key_ids:
        idx1 = get_idx(event1_id)
        idx2 = get_idx(event2_id)
        if idx1 is None or idx2 is None:
            continue
        first, second = (idx1, idx2) if idx1 < idx2 else (idx2, idx1)
        add_id(first * nevents + second)
    build_id_dt = time.monotonic() - t_build_id_start
    logger.info(
        f'Existing pair IDs built in {build_id_dt:.1f}s'
    )
    return existing_ids


def _ask_existing_pairs_action(npairs_in_db):
    """Ask the user whether to overwrite or continue an existing scan."""
    args = config.args
    if args.force:
        return 'overwrite'
    if args.force_continue:
        return 'continue'
    if not sys.stdin.isatty():
        logger.error(
            f'Found {npairs_in_db:n} event pairs in db file '
            f'{get_db_path()}.'
        )
        logger.error(
            'Cannot prompt in non-interactive mode. '
            'Use --force to overwrite or --force-continue to resume.'
        )
        rq_exit(1)
    logger.warning(
        f'Found {npairs_in_db:n} existing event pairs in db file '
        f'{get_db_path()}.'
    )
    logger.warning(
        'You can overwrite them and restart, or continue from where '
        'the previous scan stopped.'
    )
    prompt = (
        'Choose action: [o]verwrite, [c]ontinue, [a]bort '
        '(default: abort): '
    )
    choices = {
        'o': 'overwrite',
        'overwrite': 'overwrite',
        'c': 'continue',
        'continue': 'continue',
        'a': 'abort',
        'abort': 'abort',
    }
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            return 'abort'
        action = choices.get(answer)
        if action is not None:
            return action
        print('Invalid choice. Please type o, c, or a.')


def _process_pairs(catalog, continue_scan=False, slurm_context=None):
    """Process event pairs."""
    if not continue_scan:
        write_pair_records([], append=False)
    # Ensure inventory is loaded in the parent process before parent-side
    # writes, so trace_metadata rows keep full interval metadata in
    # parallel mode as in serial mode.
    try:
        load_inventory()
    except (NoMetadataError, MetadataMismatchError) as msg:
        logger.error(msg)
        rq_exit(1)
    # Write trace metadata immediately after tables are created so that
    # the DB is populated even when no pairs are found (e.g. all
    # waveform fetches fail).  Uses the inventory already in config.
    trace_ids = (
        [config.args.traceid]
        if getattr(config.args, 'traceid', None) is not None
        else list(config.catalog_trace_id)
    )
    store_trace_metadata_from_inventory(trace_ids)
    nevents = len(catalog)
    initial_npairs = nevents * (nevents - 1) // 2
    logger.info('Building valid event pairs...')
    t_grouping_start = time.monotonic()
    valid_pair_idx = _build_valid_pair_indices(catalog)
    grouping_dt = time.monotonic() - t_grouping_start
    logger.info(
        f'Valid-pair spatial grouping completed in {grouping_dt:.1f}s'
    )
    skipped_npairs = 0
    candidate_npairs = len(valid_pair_idx)
    if continue_scan:
        logger.info(
            'Continue-scan mode: loading existing pairs for '
            'pre-processing mask'
        )
        t_resume_filter_start = time.monotonic()
        existing_pair_ids = _load_existing_pair_ids(catalog)
        valid_pair_idx, skipped_npairs = _mask_existing_pair_indices(
            valid_pair_idx,
            existing_pair_ids,
            nevents,
        )
        resume_filter_dt = time.monotonic() - t_resume_filter_start
        logger.info(
            'Loading existing pair IDs and applying mask completed in '
            f'{resume_filter_dt:.1f}s'
        )
    npairs = len(valid_pair_idx)
    total_valid_pairs = skipped_npairs + npairs
    nprocs = _resolve_scan_catalog_nprocs(npairs, slurm_context or {})
    ratio = npairs / initial_npairs if initial_npairs > 0 else 0.0
    logger.info(f'Initial pairs: {initial_npairs:n}')
    logger.info(f'Candidate pairs: {candidate_npairs:n}')
    logger.info(f'Final pairs: {npairs:n}')
    logger.info(f'Pair ratio: {ratio:.6f} ({ratio:.2%})')
    _log_pair_grouping_stats(valid_pair_idx)
    logger.info(
        f'Processing {npairs:n} event pairs '
        f'({skipped_npairs:n}/{total_valid_pairs:n} already processed)'
    )
    analyzed_npairs = _process_valid_pair_indices(
        catalog,
        valid_pair_idx,
        npairs,
        initial_processed=skipped_npairs,
        total_pairs=total_valid_pairs,
        nprocs=nprocs,
        slurm_context=slurm_context,
    )
    if continue_scan:
        logger.info(
            f'Skipped {skipped_npairs:n} event pairs already present '
            'in the database'
        )
    return analyzed_npairs


def scan_catalog():
    """Perform cross-correlation on catalog events."""
    slurm_context = _get_slurm_context()
    _log_slurm_runtime_context(slurm_context)
    try:
        catalog = read_stored_catalog()
    except (ValueError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    try:
        fix_non_locatable_events(catalog)
    except MetadataMismatchError as msg:
        logger.error(msg)
        rq_exit(1)
    nevents = len(catalog)
    if nevents < 2:
        logger.error(
            'Not enough events in catalog. '
            'You need at least 2 events to run the scan 😉')
        rq_exit(1)
    logger.info(
        f'{nevents:n} events read from db file {get_db_path()}'
    )
    continue_scan = False
    existing_pairs = count_pairs()
    if existing_pairs > 0:
        action = _ask_existing_pairs_action(existing_pairs)
        if action == 'abort':
            logger.info('Scan aborted by user')
            rq_exit(0)
        continue_scan = action == 'continue'
    npairs = _process_pairs(
        catalog,
        continue_scan=continue_scan,
        slurm_context=slurm_context,
    )
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {get_db_path()}')
