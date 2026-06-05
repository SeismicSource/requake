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

_MEMORY_LOG_INTERVAL_S = 300.0  # log memory every 5 minutes


def _get_memory_mb(fast=False):
    """Return current process memory usage in MiB, or -1 when unavailable.

    Memory metrics glossary
    -----------------------
    **VmRSS** (``/proc/self/status``) — Resident Set Size: total
    physical RAM currently occupied by the process.  Includes shared
    pages (libraries, fork-copied data) at their full size, so it
    double-counts memory shared across workers.

    **RSS** (``psutil``) — same as VmRSS, but obtained via the
    cross-platform ``psutil`` library.

    **Pss** (``/proc/self/smaps_rollup``) — Proportional Set Size:
    like RSS, but shared pages are divided evenly among the processes
    that share them.  In a fork-heavy workload (e.g. 64 workers that
    all inherited the parent's catalog), each worker's Pss credits it
    with only 1/65 of those shared pages.  This gives a much more
    realistic measure of per-worker memory cost.

    .. warning::

       Reading ``smaps_rollup`` is expensive — the kernel must walk
       the process page table.  When *fast* is ``True``, Pss is
       skipped entirely.  Use ``fast=True`` in hot paths (e.g. worker
       loops) and ``fast=False`` for periodic parent-side logging.

    Fallback order
    --------------
    1. ``/proc/self/smaps_rollup`` Pss (Linux; skipped when
       ``fast=True``)
    2. ``psutil`` RSS (cross-platform)
    3. ``/proc/self/status`` VmRSS (Linux, no psutil)
    4. Return -1 (no memory data available — logging is silently
       suppressed)
    """
    # Linux-only: Pss is the most accurate metric for fork-heavy
    # workloads, but reading smaps_rollup walks the page table and is
    # too slow for per-pair worker calls.
    if not fast:
        with suppress(Exception):
            with open(
                '/proc/self/smaps_rollup', 'r', encoding='utf-8',
            ) as fh:
                for line in fh:
                    if line.startswith('Pss:'):
                        parts = line.split()
                        return float(parts[1]) / 1024.0  # kB -> MiB
    # Cross-platform: psutil works on Linux, macOS, and Windows.
    with suppress(Exception):
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    # Linux fallback when psutil is not installed.
    with suppress(Exception):
        with open('/proc/self/status', 'r', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('VmRSS:'):
                    parts = line.split()
                    return float(parts[1]) / 1024.0  # kB -> MiB
    return -1.0


def log_memory_usage(prefix=''):
    """Log current process memory usage (Pss on Linux, RSS elsewhere)."""
    mem_mb = _get_memory_mb(fast=False)
    if mem_mb < 0:
        return
    label = f'{prefix} ' if prefix else ''
    logger.info(f'[MEM] {label}{mem_mb:,.0f} MiB')


SLURM_CONTEXT_KEYS = (
    'SLURM_JOB_ID',
    'SLURM_JOB_NAME',
    'SLURM_CLUSTER_NAME',
    'SLURM_CPUS_PER_TASK',
    'SLURM_CPUS_ON_NODE',
    'SLURM_JOB_CPUS_PER_NODE',
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


def _parse_slurm_cpu_count(value):
    """Parse a Slurm CPU count value into an integer."""
    if value is None:
        return None
    with suppress(ValueError):
        return int(value)
    head = value.split('(', 1)[0].split(',', 1)[0].strip()
    with suppress(ValueError):
        return int(head)
    return None


def resolve_scan_catalog_nprocs(npairs, slurm_context):
    """Resolve effective worker count for scan_catalog."""
    cli_nprocs = getattr(config.args, 'nprocs', None)
    config_nprocs = getattr(config, 'catalog_scan_nprocs', 0)
    requested = cli_nprocs if cli_nprocs is not None else config_nprocs
    if requested < 0:
        logger.error('catalog_scan_nprocs must be >= 0')
        rq_exit(1)
    if requested == 0:
        slurm_cpu_sources = (
            'SLURM_CPUS_PER_TASK',
            'SLURM_CPUS_ON_NODE',
            'SLURM_JOB_CPUS_PER_NODE',
        )
        base_nprocs = None
        for key in slurm_cpu_sources:
            slurm_cpus = slurm_context.get(key)
            parsed_cpus = _parse_slurm_cpu_count(slurm_cpus)
            if parsed_cpus is None:
                if slurm_cpus is not None:
                    logger.warning(
                        f'Invalid {key} value {slurm_cpus!r}; '
                        'trying fallback CPU count'
                    )
                continue
            base_nprocs = parsed_cpus
            break
        if base_nprocs is None:
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


def progress_summary(current, total, start_time, rate=None):
    """Return a compact progress summary string.

    When *rate* is ``None`` (default), the pairs-per-second rate is
    computed as ``current / elapsed``.  Pass an explicit *rate* to
    override this, e.g. to report a window-based rate that excludes
    pairs processed before the current run.
    """
    if rate is None:
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
    """Log non-interactive progress periodically.

    Returns ``(next_log_time, did_log)`` where ``did_log`` is ``True``
    only when the message was actually emitted.
    """
    if time.monotonic() < next_log_time:
        return next_log_time, False
    window_elapsed = max(time.monotonic() - window_start_time, 1e-9)
    window_rate = window_pair_count / window_elapsed
    slurm_suffix = slurm_progress_suffix(slurm_context)
    summary = progress_summary(
        processed, npairs, window_start_time, rate=window_rate,
    )
    logger.info(
        f'Processing pairs: {summary} '
        f'[workers={nprocs:n}{slurm_suffix}]'
    )
    log_pair_timing_split(
        window_pair_count,
        window_elapsed,
        window_fetch_time,
        window_crosscorr_time,
    )
    log_cache_stats(waveform_pair)
    return next_log_time + 60.0, True


def _log_memory_if_due(state, label=''):
    """Log memory usage when the configured interval has elapsed."""
    now = time.monotonic()
    if now < state['next_memory_log_time']:
        return
    state['next_memory_log_time'] = now + _MEMORY_LOG_INTERVAL_S
    log_memory_usage(prefix=label)


def init_pair_processing_state(npairs, initial_processed, total_pairs):
    """Build mutable state for pair processing."""
    if total_pairs is None:
        total_pairs = npairs
    start_time = time.monotonic()
    return {
        'start_time': start_time,
        'next_log_time': start_time + 60.0,
        'next_memory_log_time': start_time + _MEMORY_LOG_INTERVAL_S,
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
        _log_memory_if_due(state, label='[parent]')
        return
    processed_total = state['initial_processed'] + processed
    next_log_time, did_log = _log_noninteractive_progress(
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
    state['next_log_time'] = next_log_time
    if did_log:
        state['window_start_time'] = time.monotonic()
        state['window_pair_count'] = 0
        state['window_fetch_time'] = 0.0
        state['window_crosscorr_time'] = 0.0
    _log_memory_if_due(state, label='[parent]')
