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
import math
import time
import logging
import numpy as np
from tqdm import tqdm
from scipy.spatial import cKDTree
from ..config import config, rq_exit
from ..database.db import get_db_path
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..families.pairs import RequakeEventPair
from ..database.pairs import write_pairs as write_pairs_to_db
from ..waveforms import (
    WaveformPair, cc_waveform_pair,
    NoWaveformError, NoMetadataError, MetadataMismatchError
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
EARTH_RADIUS_KM = 6371.0088


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


def _log_timing_split(start_time, waveform_fetch_time, crosscorr_time):
    """Log cumulative timing split for waveform fetch and correlation."""
    elapsed = max(time.monotonic() - start_time, 1e-9)
    timed = waveform_fetch_time + crosscorr_time
    other_time = max(elapsed - timed, 0.0)
    logger.info(
        'Timing split: '
        f'fetch={waveform_fetch_time:.1f}s '
        f'({waveform_fetch_time / elapsed:.1%}), '
        f'cc={crosscorr_time:.1f}s '
        f'({crosscorr_time / elapsed:.1%}), '
        f'other={other_time:.1f}s '
        f'({other_time / elapsed:.1%})'
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


def _log_noninteractive_progress(
    processed,
    npairs,
    start_time,
    next_log_time,
    waveform_fetch_time,
    crosscorr_time,
    waveform_pair
):
    """Log non-interactive progress periodically and return next log time."""
    if time.monotonic() < next_log_time:
        return next_log_time
    logger.info(
        'Processing pairs: '
        f'{_progress_summary(processed, npairs, start_time)}'
    )
    _log_timing_split(start_time, waveform_fetch_time, crosscorr_time)
    _log_cache_stats(waveform_pair)
    return next_log_time + 60.0


def _process_pair(pair, waveform_pair):
    """Process a single pair and return result plus timing."""
    t_fetch_start = time.monotonic()
    pair_st = waveform_pair.get_waveform_pair(pair)
    waveform_fetch_dt = time.monotonic() - t_fetch_start
    tr1, tr2 = pair_st.traces
    t_cc_start = time.monotonic()
    lag, lag_sec, cc_max = cc_waveform_pair(tr1, tr2)
    crosscorr_dt = time.monotonic() - t_cc_start
    stats1 = tr1.stats
    stats2 = tr2.stats
    _fix_trace_id(stats1)
    _fix_trace_id(stats2)
    pair_out = RequakeEventPair(
        pair[0],
        pair[1],
        tr1.id,
        lag,
        lag_sec,
        cc_max,
    )
    return pair_out, waveform_fetch_dt, crosscorr_dt


def _process_valid_pair_indices(catalog, valid_pair_idx, npairs):
    """Process valid pairs from index pairs."""
    logger.info('Computing waveform cross-correlation...')
    waveform_pair = WaveformPair()
    batch_of_pairs = []
    start_time = time.monotonic()
    next_log_time = start_time + 60.0
    waveform_fetch_time = 0.0
    crosscorr_time = 0.0
    show_pbar = sys.stderr.isatty()
    if show_pbar:
        pbar = tqdm(
            total=npairs,
            unit='pairs',
            unit_scale=True,
            desc=f'Processing {npairs:n} event pairs'
        )
    else:
        pbar = None
    for processed, (idx1, idx2) in enumerate(valid_pair_idx, start=1):
        if not show_pbar:
            next_log_time = _log_noninteractive_progress(
                processed,
                npairs,
                start_time,
                next_log_time,
                waveform_fetch_time,
                crosscorr_time,
                waveform_pair
            )
        pair = (catalog[idx1], catalog[idx2])
        if pbar is not None:
            pbar.update()
        try:
            pair_out, fetch_dt, crosscorr_dt = _process_pair(
                pair, waveform_pair
            )
            waveform_fetch_time += fetch_dt
            crosscorr_time += crosscorr_dt
            batch_of_pairs.append(pair_out)
            if len(batch_of_pairs) >= 100:
                write_pairs_to_db(batch_of_pairs, config, append=True)
                batch_of_pairs = []
        except (NoMetadataError, MetadataMismatchError) as msg:
            logger.error(msg)
            rq_exit(1)
        except NoWaveformError as msg:
            # Do not print empty messages
            if str(msg):
                logger.warning(msg)
    if batch_of_pairs:
        write_pairs_to_db(batch_of_pairs, config, append=True)
    if pbar is not None:
        pbar.close()
    elif npairs > 0:
        logger.info(
            'Processing pairs: '
            f'{_progress_summary(npairs, npairs, start_time)}'
        )
    if npairs > 0:
        _log_timing_split(start_time, waveform_fetch_time, crosscorr_time)
        _log_cache_stats(waveform_pair)


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


def _process_pairs(catalog):
    """Process event pairs."""
    write_pairs_to_db([], config, append=False)
    nevents = len(catalog)
    initial_npairs = nevents * (nevents - 1) // 2
    logger.info('Building valid event pairs...')
    valid_pair_idx = _build_valid_pair_indices(catalog)
    npairs = len(valid_pair_idx)
    ratio = npairs / initial_npairs if initial_npairs > 0 else 0.0
    logger.info(f'Initial pairs: {initial_npairs:n}')
    logger.info(f'Final pairs: {npairs:n}')
    logger.info(f'Pair ratio: {ratio:.6f} ({ratio:.2%})')
    _log_pair_grouping_stats(valid_pair_idx)
    logger.info(f'Processing {npairs:n} event pairs')
    _process_valid_pair_indices(catalog, valid_pair_idx, npairs)
    return npairs


def scan_catalog():
    """Perform cross-correlation on catalog events."""
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
        f'{nevents:n} events read from db file {get_db_path(config)}'
    )
    npairs = _process_pairs(catalog)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {get_db_path(config)}')
