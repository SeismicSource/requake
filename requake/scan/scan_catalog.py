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
from ..database.pairs import (
    count_pairs as count_pairs_in_db,
    read_pair_keys,
    write_pairs as write_pairs_to_db,
)
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
    waveform_pair
):
    """Log non-interactive progress periodically and return next log time."""
    if time.monotonic() < next_log_time:
        return next_log_time
    logger.info(
        'Processing pairs: '
        f'{_progress_summary(processed, npairs, window_start_time)}'
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
    if len(batch_of_pairs) >= 100:
        write_pairs_to_db(batch_of_pairs, config, append=True)
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
        write_pairs_to_db(batch_of_pairs, config, append=True)
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
    _log_cache_stats(waveform_pair)


def _process_valid_pair_indices(
    catalog,
    valid_pair_idx,
    npairs,
    initial_processed=0,
    total_pairs=None,
):
    """Process valid pairs from index pairs."""
    logger.info('Computing waveform cross-correlation...')
    waveform_pair = WaveformPair()
    batch_of_pairs = []
    state = _init_pair_processing_state(npairs, initial_processed, total_pairs)
    show_pbar, pbar = _init_progress_bar(state)
    for processed, (idx1, idx2) in enumerate(valid_pair_idx, start=1):
        _update_noninteractive_progress(
            state,
            waveform_pair,
            show_pbar,
            processed,
        )
        pair = (catalog[idx1], catalog[idx2])
        if pbar is not None:
            pbar.update()
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
    _finalize_pair_processing(
        batch_of_pairs,
        pbar,
        npairs,
        state,
        waveform_pair,
    )


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


def _filter_existing_pair_indices(catalog, valid_pair_idx):
    """Drop pairs already present in the database."""
    existing_pairs = read_pair_keys(config)
    if not existing_pairs or len(valid_pair_idx) == 0:
        return valid_pair_idx, 0
    evid_to_idx = {
        ev.evid: idx for idx, ev in enumerate(catalog)
    }
    nevents = np.uint64(len(catalog))
    existing_ids = []
    for evid1, evid2 in existing_pairs:
        idx1 = evid_to_idx.get(evid1)
        idx2 = evid_to_idx.get(evid2)
        if idx1 is None or idx2 is None:
            continue
        first = min(idx1, idx2)
        second = max(idx1, idx2)
        pair_id = np.uint64(first) * nevents + np.uint64(second)
        existing_ids.append(pair_id)
    if not existing_ids:
        return valid_pair_idx, 0
    existing_ids = np.asarray(existing_ids, dtype=np.uint64)
    candidate_ids = (
        valid_pair_idx[:, 0].astype(np.uint64) * nevents
        + valid_pair_idx[:, 1].astype(np.uint64)
    )
    keep = ~np.isin(candidate_ids, existing_ids)
    skipped = int((~keep).sum())
    return valid_pair_idx[keep], skipped


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
            f'{get_db_path(config)}.'
        )
        logger.error(
            'Cannot prompt in non-interactive mode. '
            'Use --force to overwrite or --force-continue to resume.'
        )
        rq_exit(1)
    logger.warning(
        f'Found {npairs_in_db:n} existing event pairs in db file '
        f'{get_db_path(config)}.'
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


def _process_pairs(catalog, continue_scan=False):
    """Process event pairs."""
    if not continue_scan:
        write_pairs_to_db([], config, append=False)
    nevents = len(catalog)
    initial_npairs = nevents * (nevents - 1) // 2
    logger.info('Building valid event pairs...')
    valid_pair_idx = _build_valid_pair_indices(catalog)
    skipped_npairs = 0
    if continue_scan:
        valid_pair_idx, skipped_npairs = _filter_existing_pair_indices(
            catalog, valid_pair_idx
        )
    already_processed = skipped_npairs
    npairs = len(valid_pair_idx)
    total_valid_pairs = already_processed + npairs
    ratio = npairs / initial_npairs if initial_npairs > 0 else 0.0
    logger.info(f'Initial pairs: {initial_npairs:n}')
    logger.info(f'Final pairs: {npairs:n}')
    logger.info(f'Pair ratio: {ratio:.6f} ({ratio:.2%})')
    if continue_scan:
        logger.info(
            'Resume mode: existing event-pair keys were loaded from '
            'the database'
        )
        logger.info(
            f'Skipping {skipped_npairs:n} event pairs already present '
            'in the database'
        )
    _log_pair_grouping_stats(valid_pair_idx)
    logger.info(
        f'Processing {npairs:n} event pairs '
        f'({already_processed:n}/{total_valid_pairs:n} already processed)'
    )
    _process_valid_pair_indices(
        catalog,
        valid_pair_idx,
        npairs,
        initial_processed=already_processed,
        total_pairs=total_valid_pairs,
    )
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
    continue_scan = False
    existing_pairs = count_pairs_in_db(config)
    if existing_pairs > 0:
        action = _ask_existing_pairs_action(existing_pairs)
        if action == 'abort':
            logger.info('Scan aborted by user')
            rq_exit(0)
        continue_scan = action == 'continue'
    npairs = _process_pairs(catalog, continue_scan=continue_scan)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {get_db_path(config)}')
