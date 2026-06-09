# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Pair-index helpers for catalog-based repeater scans.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import math
import time
import logging
import numpy as np
from scipy.spatial import cKDTree
from ..config import config
from ..database.pairs import read_event_key_rows, read_pair_key_ids

logger = logging.getLogger('scan_catalog')
_EARTH_RADIUS_KM = 6371.0088


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
    angular_dist = range_km / _EARTH_RADIUS_KM
    chord_dist = 2.0 * math.sin(angular_dist / 2.0)
    return coords, tree, chord_dist


def build_valid_pair_indices(catalog):
    """Build grouped event-pair indices using int32 storage."""
    nevents = len(catalog)
    coords, tree, chord_dist = _build_spatial_index(catalog)
    if coords is None:
        return np.empty((0, 2), dtype=np.int32)
    logger.info(
        '[rq:pairs] Grouping valid pairs while building '
        'the spatial index...'
    )
    counts = np.empty(nevents, dtype=np.int32)
    grouped_seconds = []
    npairs = 0
    for idx, coord in enumerate(coords):
        neighbors = np.asarray(
            tree.query_ball_point(coord, chord_dist),
            dtype=np.int32,
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


def log_pair_grouping_stats(valid_pair_idx):
    """Log whether pairs are grouped by first event."""
    npairs = len(valid_pair_idx)
    if npairs == 0:
        logger.info('[rq:pairs] Pair grouping: no pairs to verify')
        return
    first = valid_pair_idx[:, 0]
    if npairs == 1:
        logger.info(
            '[rq:pairs] Pair grouping: '
            'single pair, grouping is trivial'
        )
        return
    monotonic = bool(np.all(first[:-1] <= first[1:]))
    boundaries = np.flatnonzero(first[1:] != first[:-1]) + 1
    run_lengths = np.diff(np.concatenate(([0], boundaries, [npairs])))
    logger.info(
        f'[rq:pairs] Pair grouping: '
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
            '[rq:pairs] Pairs are not grouped by first event; '
            'waveform reuse may be degraded.'
        )


def load_existing_pair_ids(catalog):
    """Return packed pair IDs already present in the database."""
    t_read_keys_start = time.monotonic()
    logger.info(
        '[rq:pairs] Loading existing pair key IDs from db file...'
    )
    event_key_rows = read_event_key_rows()
    existing_pair_key_ids = read_pair_key_ids()
    read_keys_dt = time.monotonic() - t_read_keys_start
    logger.info(
        f'[rq:pairs] {len(existing_pair_key_ids):n} unique pairs '
        f'loaded in {read_keys_dt:.1f}s'
    )
    if not existing_pair_key_ids:
        return set()
    t_build_id_start = time.monotonic()
    logger.info(
        '[rq:pairs] Building existing pair IDs for quick lookup...'
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
        f'[rq:pairs] Existing pair IDs built in {build_id_dt:.1f}s'
    )
    return existing_ids


def mask_existing_pair_indices(valid_pair_idx, existing_pair_ids, nevents):
    """Drop candidate pairs already present in storage."""
    if not existing_pair_ids or len(valid_pair_idx) == 0:
        return valid_pair_idx, 0
    t_mask_start = time.monotonic()
    logger.info(
        '[rq:pairs] Masking already processed pairs '
        'before processing...'
    )
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
        f'[rq:pairs] Existing-pair masking completed in {mask_dt:.1f}s'
    )
    return filtered, skipped
