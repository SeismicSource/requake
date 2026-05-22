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


def _candidate_pairs(catalog):
    """Return candidate index pairs using a KD-tree on unit sphere."""
    range_km = config.catalog_search_range
    if range_km <= 0:
        return np.empty((0, 2), dtype=np.int64)
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
    return tree.query_pairs(chord_dist, output_type='ndarray')


def _build_valid_pair_indices(catalog):
    """Build and return valid event-pair index array."""
    candidates = _candidate_pairs(catalog)
    return (
        np.empty((0, 2), dtype=np.int64)
        if len(candidates) == 0
        else candidates
    )


def _progress_summary(current, total, start_time):
    """Return a compact progress summary string."""
    elapsed = max(time.monotonic() - start_time, 1e-9)
    rate = current / elapsed
    percent = 100.0 * current / total if total else 0.0
    return (
        f'{current:n}/{total:n} ({percent:.1f}%) '
        f'[{rate:,.0f} pairs/s]'
    )


def _process_valid_pair_indices(catalog, valid_pair_idx, npairs):
    """Process valid pairs from index pairs."""
    logger.info('Computing waveform cross-correlation...')
    waveform_pair = WaveformPair()
    batch_of_pairs = []
    start_time = time.monotonic()
    next_log_time = start_time + 60.0
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
        if not show_pbar and time.monotonic() >= next_log_time:
            logger.info(
                'Processing pairs: '
                f'{_progress_summary(processed, npairs, start_time)}'
            )
            next_log_time += 60.0
        pair = (catalog[idx1], catalog[idx2])
        if pbar is not None:
            pbar.update()
        try:
            pair_st = waveform_pair.get_waveform_pair(pair)
            tr1, tr2 = pair_st.traces
            lag, lag_sec, cc_max = cc_waveform_pair(tr1, tr2)
            stats1 = tr1.stats
            stats2 = tr2.stats
            _fix_trace_id(stats1)
            _fix_trace_id(stats2)
            batch_of_pairs.append(
                RequakeEventPair(
                    pair[0],
                    pair[1],
                    tr1.id,
                    lag,
                    lag_sec,
                    cc_max,
                )
            )
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
        f'{nevents} events read from db file {get_db_path(config)}'
    )
    npairs = _process_pairs(catalog)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {get_db_path(config)}')
