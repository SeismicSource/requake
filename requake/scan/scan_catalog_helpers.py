# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Runtime helpers for catalog-based repeater scans.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
import sys
import time
from contextlib import suppress

from tqdm import tqdm

from ..config import config, rq_exit

logger = logging.getLogger('scan_catalog')

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


def get_slurm_context():
    """Return current Slurm environment variables that are set."""
    context = {}
    for key in SLURM_CONTEXT_KEYS:
        value = os.environ.get(key)
        if value:
            context[key] = value
    return context


def log_slurm_runtime_context(slurm_context):
    """Log Slurm runtime details when available."""
    if not slurm_context:
        return
    details = ', '.join(
        f'{key}={slurm_context[key]}'
        for key in SLURM_CONTEXT_KEYS
        if key in slurm_context
    )
    logger.info(f'Slurm runtime context: {details}')


def slurm_progress_suffix(slurm_context):
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
        with suppress(OSError):
            return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def resolve_scan_catalog_nprocs(npairs, slurm_context):
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


def progress_summary(current, total, start_time):
    """Return a compact progress summary string."""
    elapsed = max(time.monotonic() - start_time, 1e-9)
    rate = current / elapsed
    percent = 100.0 * current / total if total else 0.0
    return (
        f'{current:n}/{total:n} ({percent:.1f}%) '
        f'[{rate:,.0f} pairs/s]'
    )


def log_pair_timing_split(
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


def log_pair_processing_report(state, analyzed_pairs, elapsed):
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


def log_cache_stats(waveform_pair):
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
    slurm_suffix = slurm_progress_suffix(slurm_context)
    logger.info(
        'Processing pairs: '
        f'{progress_summary(processed, npairs, window_start_time)} '
        f'[workers={nprocs:n}{slurm_suffix}]'
    )
    log_pair_timing_split(
        window_pair_count,
        time.monotonic() - window_start_time,
        window_fetch_time,
        window_crosscorr_time,
    )
    log_cache_stats(waveform_pair)
    return next_log_time + 60.0


def init_pair_processing_state(npairs, initial_processed, total_pairs):
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


def init_progress_bar(state):
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


def update_noninteractive_progress(
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
