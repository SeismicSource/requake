# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Low-overhead diagnostics for parallel ProcessPoolExecutor workloads.

Active whenever parallel processing is used, regardless of SLURM.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
from collections import deque
from contextlib import suppress
from time import perf_counter as _perf_counter

logger = logging.getLogger('scan_catalog.parallel_diag')

# ---------------------------------------------------------------------------
# RSS helper
# ---------------------------------------------------------------------------


def parallel_rss_gb():
    """Return current process RSS in GiB, or -1.0 on failure."""
    with suppress(Exception):
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)
    return -1.0


# ---------------------------------------------------------------------------
# Worker metrics (per-process, emitted every 5 minutes)
# ---------------------------------------------------------------------------


class ParallelWorkerDiagnostics:
    """Per-worker metrics collector.

    Each worker process owns one instance.  Every 5 minutes it emits a
    structured ``WORKER_STATS`` log line.
    """

    _LOG_INTERVAL = 300.0  # seconds

    def __init__(self):
        """Initialize per-worker counters and timers."""
        self.pid = os.getpid()
        self.pairs_processed = 0
        self.worker_start_time = _perf_counter()
        self.waveform_fetch_count = 0
        self.waveform_fetch_time_total = 0.0
        self.correlation_count = 0
        self.correlation_time_total = 0.0
        self._peak_rss_gb = 0.0
        self._last_log_time = _perf_counter()

    def _update_peak_rss(self, rss):
        if rss > self._peak_rss_gb:
            self._peak_rss_gb = rss

    def record_fetch(self, elapsed):
        """Accumulate one waveform-fetch timing sample."""
        self.waveform_fetch_count += 1
        self.waveform_fetch_time_total += elapsed

    def record_correlation(self, elapsed):
        """Accumulate one cross-correlation timing sample."""
        self.correlation_count += 1
        self.correlation_time_total += elapsed

    def maybe_log(self):
        """Emit ``WORKER_STATS`` if the log interval has elapsed."""
        now = _perf_counter()
        if now - self._last_log_time < self._LOG_INTERVAL:
            return
        self._last_log_time = now
        rss = parallel_rss_gb()
        self._update_peak_rss(rss)
        logger.info(
            f'[rq:parallel] WORKER_STATS pid={self.pid} '
            f'rss_gb={rss:.3f} peak_gb={self._peak_rss_gb:.3f} '
            f'pairs={self.pairs_processed:n} '
            f'db_fetches={self.waveform_fetch_count:n} '
            f'db_time_s={self.waveform_fetch_time_total:.3f} '
            f'corrs={self.correlation_count:n} '
            f'corr_time_s={self.correlation_time_total:.3f}'
        )


# ---------------------------------------------------------------------------
# SQLite diagnostics (per worker, one-shot at startup)
# ---------------------------------------------------------------------------


def _waveform_cache_db_path():
    """Return the waveform-cache SQLite file path, or ``None``."""
    with suppress(Exception):
        from ..config import config
        from pathlib import Path

        if not bool(
            getattr(config, 'catalog_waveform_disk_cache_enabled', True)
        ):
            return None
        args = getattr(config, 'args', None)
        outdir = getattr(args, 'outdir', None)
        return (
            None if outdir is None
            else str(Path(outdir) / 'waveform_cache.sqlite')
        )
    return None


def parallel_log_sqlite_info():
    """Log SQLite database file size and page info once per worker."""
    db_path = _waveform_cache_db_path()
    if db_path is None or not os.path.exists(db_path):
        return
    db_size_gb = os.path.getsize(db_path) / (1024 ** 3)
    page_count = '?'
    page_size = '?'
    with suppress(Exception):
        import sqlite3
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            page_count = conn.execute('PRAGMA page_count').fetchone()[0]
            page_size = conn.execute('PRAGMA page_size').fetchone()[0]
        finally:
            conn.close()
    logger.info(
        f'[rq:parallel] SQLITE_INFO pid={os.getpid()} '
        f'db_size_gb={db_size_gb:.3f} '
        f'page_count={page_count} page_size_bytes={page_size}'
    )


# ---------------------------------------------------------------------------
# Chunk-level diagnostics (emitted by parent after each recycle chunk)
# ---------------------------------------------------------------------------


def parallel_log_chunk_summary(
    chunk_id,
    pairs_processed,
    elapsed,
    results_in_chunk,
):
    """Emit ``CHUNK_SUMMARY`` after a worker-recycle chunk completes."""
    throughput = pairs_processed / elapsed if elapsed > 0 else 0.0
    logger.info(
        f'[rq:parallel] CHUNK_SUMMARY chunk={chunk_id} '
        f'pairs_processed={pairs_processed:n} '
        f'elapsed_s={elapsed:.3f} '
        f'throughput_pairs_per_s={throughput:.1f} '
        f'results_in_chunk={results_in_chunk}'
    )


def parallel_log_pool_recycle(chunk_id, startup, shutdown):
    """Emit ``POOL_RECYCLE`` with pool creation and shutdown timings."""
    logger.info(
        f'[rq:parallel] POOL_RECYCLE chunk={chunk_id} '
        f'startup_s={startup:.3f} shutdown_s={shutdown:.3f}'
    )


def parallel_log_result_buffer(chunk_id, batch_len, rss_parent_gb):
    """Emit ``RESULT_BUFFER`` to track batch growth."""
    logger.info(
        f'[rq:parallel] RESULT_BUFFER chunk={chunk_id} '
        f'len_batch_of_pairs={batch_len} '
        f'rss_parent_gb={rss_parent_gb:.3f}'
    )


# ---------------------------------------------------------------------------
# System snapshots (parent process, every 10 minutes)
# ---------------------------------------------------------------------------


class ParallelSystemSnapshot:
    """Periodic system-level diagnostics for the parent process."""

    _LOG_INTERVAL = 600.0  # 10 minutes

    def __init__(self):
        """Initialize system-snapshot state."""
        self._last_log_time = _perf_counter()
        self._prev_pairs = 0
        self._prev_snap_time = _perf_counter()

    def maybe_log(self, total_pairs_processed, slurm_context=None):
        """Emit ``SYSTEM_STATS`` every 10 minutes."""
        now = _perf_counter()
        if now - self._last_log_time < self._LOG_INTERVAL:
            return
        self._last_log_time = now
        interval = max(now - self._prev_snap_time, 1e-9)
        pairs_delta = total_pairs_processed - self._prev_pairs
        throughput = pairs_delta / interval
        self._prev_pairs = total_pairs_processed
        self._prev_snap_time = now
        rss = parallel_rss_gb()
        loadavg = '?'
        with suppress(Exception):
            lavg = os.getloadavg()
            loadavg = f'{lavg[0]:.2f},{lavg[1]:.2f},{lavg[2]:.2f}'
        num_children = 0
        if slurm_context:
            with suppress(ValueError):
                num_children = int(
                    slurm_context.get('SLURM_NTASKS', 0)
                )
        logger.info(
            f'[rq:parallel] SYSTEM_STATS rss_parent_gb={rss:.3f} '
            f'num_children={num_children} '
            f'pairs_processed={total_pairs_processed:n} '
            f'throughput_pairs_per_s={throughput:.1f} '
            f'loadavg_1m_5m_15m={loadavg}'
        )


# ---------------------------------------------------------------------------
# Slow-task detection
# ---------------------------------------------------------------------------


class ParallelSlowTaskDetector:
    """Detect tasks whose duration far exceeds the rolling median.

    Rate-limited to avoid log noise on multi-day runs.
    """

    # Emit at most one SLOW_TASK message per this many seconds.
    _RATE_LIMIT_S = 30.0
    # Task is "slow" when duration > _FACTOR × rolling median.
    _FACTOR = 10.0
    # Rolling window size.
    _WINDOW = 256

    def __init__(self):
        """Initialize slow-task detector with empty rolling window."""
        self._durations = deque(maxlen=self._WINDOW)
        self._last_emit = 0.0

    def record(self, duration, pair_id=None):
        """Record a task duration and maybe emit ``SLOW_TASK``."""
        self._durations.append(duration)
        if len(self._durations) < 16:
            # Not enough samples for a stable median yet.
            return
        sorted_d = sorted(self._durations)
        mid = len(sorted_d) // 2
        median = (
            sorted_d[mid]
            if len(sorted_d) % 2 == 1
            else (sorted_d[mid - 1] + sorted_d[mid]) / 2.0
        )
        if median <= 0 or duration <= self._FACTOR * median:
            return
        now = _perf_counter()
        if now - self._last_emit < self._RATE_LIMIT_S:
            return
        self._last_emit = now
        logger.info(
            f'[rq:parallel] SLOW_TASK pid={os.getpid()} '
            f'duration_s={duration:.3f} '
            f'pair={pair_id if pair_id is not None else "?"}'
        )
