# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed trace metadata persistence.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from obspy import UTCDateTime
from ..config.config import config
from .db import (
    execute_with_retry,
    get_db_connection,
)

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

TRACE_METADATA_TABLE = 'trace_metadata'
MISSING_TRACE_METADATA_TABLE = f'no such table: {TRACE_METADATA_TABLE}'
# Default validity start when no channel start_date is available in
# the inventory; effectively means "since the beginning of time".
TRACE_METADATA_VALID_FROM = '1900-01-01T00:00:00'
# Tolerances for detecting meaningful changes on metadata refresh.
# See pairs_schema_simplification_plan.md for calibration approach.
SAMPLING_RATE_REL_TOL = 1e-6
SAMPLING_RATE_ABS_TOL = 1e-9
TRACE_COORDS_ABS_TOL = 1e-6
TRACE_DEPTH_ABS_TOL = 1e-6


class PairsMetadataError(RuntimeError):
    """Raised when trace metadata for stored pairs is missing or invalid."""


TRACE_METADATA_SCHEMA_STATEMENTS = [
    f'''
    CREATE TABLE IF NOT EXISTS {TRACE_METADATA_TABLE} (
      trace_id          TEXT NOT NULL,
      valid_from_utc    TEXT NOT NULL,
      valid_to_utc      TEXT,
      sampling_rate_hz  REAL NOT NULL,
      trace_lon         REAL,
      trace_lat         REAL,
      elevation         REAL,
      local_depth       REAL,
      updated_at        TEXT,
      PRIMARY KEY (trace_id, valid_from_utc)
    )
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_trace_metadata_lookup '
        f'ON {TRACE_METADATA_TABLE}('
        'trace_id, valid_from_utc, valid_to_utc)'
    ),
]


def _is_missing_trace_metadata_table_error(err):
    """Return True when a sqlite error means the metadata table is absent."""
    return MISSING_TRACE_METADATA_TABLE in str(err)


def _float_differs(value1, value2, abs_tol, rel_tol=0.0):
    """Return True when floats differ beyond configured tolerances."""
    if value1 is None or value2 is None:
        return value1 != value2
    limit = max(abs_tol, rel_tol * max(abs(value1), abs(value2)))
    return abs(value1 - value2) > limit


def _trace_metadata_value_differs(existing, candidate):
    """Return True when persisted metadata differs from new metadata."""
    sampling_rate_changed = _float_differs(
        existing['sampling_rate_hz'],
        candidate['sampling_rate_hz'],
        SAMPLING_RATE_ABS_TOL,
        SAMPLING_RATE_REL_TOL,
    )
    lon_changed = _float_differs(
        existing['trace_lon'], candidate['trace_lon'], TRACE_COORDS_ABS_TOL
    )
    lat_changed = _float_differs(
        existing['trace_lat'], candidate['trace_lat'], TRACE_COORDS_ABS_TOL
    )
    elevation_changed = _float_differs(
        existing['elevation'], candidate['elevation'], TRACE_DEPTH_ABS_TOL
    )
    local_depth_changed = _float_differs(
        existing['local_depth'],
        candidate['local_depth'],
        TRACE_DEPTH_ABS_TOL,
    )
    return (
        sampling_rate_changed
        or lon_changed
        or lat_changed
        or elevation_changed
        or local_depth_changed
    )


def _infer_sampling_rate(pair):
    """Infer sampling rate from the pair when inventory metadata is absent."""
    if getattr(pair, 'sampling_rate_hz', None) is not None:
        return float(pair.sampling_rate_hz)
    lag_sec = getattr(pair, 'lag_sec', None)
    if lag_sec and pair.lag_samples:
        return abs(pair.lag_samples / lag_sec)
    raise PairsMetadataError(
        'Unable to infer sampling rate for '
        f'trace_id {pair.trace_id}. Inventory metadata is missing.'
    )


def _trace_metadata_from_inventory(trace_id):
    """Extract time-valid trace metadata rows from a loaded inventory."""
    inventory = getattr(config, 'inventory', None)
    if inventory is None:
        return []
    net, sta, loc, chan = trace_id.split('.')
    if not net:
        net = '@@'
    selected = inventory.select(
        network=net, station=sta, location=loc, channel=chan
    )
    rows = []
    default_start = UTCDateTime(TRACE_METADATA_VALID_FROM)
    for network in selected:
        for station in network:
            for channel in station:
                sampling_rate = getattr(channel, 'sample_rate', None)
                if sampling_rate is None:
                    continue
                rows.append(
                    {
                        'trace_id': trace_id,
                        'valid_from_utc': str(
                            channel.start_date or default_start
                        ),
                        'valid_to_utc': (
                            None
                            if channel.end_date is None
                            else str(channel.end_date)
                        ),
                        'sampling_rate_hz': float(sampling_rate),
                        'trace_lon': getattr(channel, 'longitude', None),
                        'trace_lat': getattr(channel, 'latitude', None),
                        'elevation': getattr(channel, 'elevation', None),
                        'local_depth': getattr(channel, 'depth', None),
                        'updated_at': str(UTCDateTime()),
                    }
                )
    return rows


def _trace_metadata_fallback_rows(pairs):
    """Build fallback metadata rows directly from stored pair objects."""
    rows = []
    seen_trace_ids = set()
    for pair in pairs:
        if pair.trace_id in seen_trace_ids:
            continue
        seen_trace_ids.add(pair.trace_id)
        try:
            sampling_rate_hz = _infer_sampling_rate(pair)
        except PairsMetadataError as err:
            logger.warning(
                'Skipping trace_metadata fallback row for trace_id '
                f'{pair.trace_id}: {err}'
            )
            continue
        rows.append(
            {
                'trace_id': pair.trace_id,
                'valid_from_utc': TRACE_METADATA_VALID_FROM,
                'valid_to_utc': None,
                'sampling_rate_hz': sampling_rate_hz,
                'trace_lon': None,
                'trace_lat': None,
                'elevation': None,
                'local_depth': None,
                'updated_at': str(UTCDateTime()),
            }
        )
    return rows


def _trace_metadata_rows(pairs):
    """Build metadata rows needed by the current pair batch."""
    rows = []
    pairs_by_trace_id = {}
    for pair in pairs:
        pairs_by_trace_id.setdefault(pair.trace_id, []).append(pair)
    for trace_id, trace_pairs in pairs_by_trace_id.items():
        inventory_rows = _trace_metadata_from_inventory(trace_id)
        if inventory_rows:
            rows.extend(inventory_rows)
        else:
            rows.extend(_trace_metadata_fallback_rows(trace_pairs))
    return rows


def _intervals_overlap(existing, candidate):
    """Return True when two half-open metadata intervals overlap."""
    start1 = UTCDateTime(existing['valid_from_utc'])
    start2 = UTCDateTime(candidate['valid_from_utc'])
    end1 = (
        None
        if existing['valid_to_utc'] is None
        else UTCDateTime(existing['valid_to_utc'])
    )
    end2 = (
        None
        if candidate['valid_to_utc'] is None
        else UTCDateTime(candidate['valid_to_utc'])
    )
    if end1 is not None and end1 <= start2:
        return False
    return end2 is None or end2 > start1


def _warn_trace_metadata_change(existing, candidate):
    """Warn when refreshed metadata differs from stored values."""
    changed_fields = []
    for key in (
        'sampling_rate_hz',
        'trace_lon',
        'trace_lat',
        'elevation',
        'local_depth',
    ):
        if key == 'sampling_rate_hz':
            differs = _float_differs(
                existing[key],
                candidate[key],
                SAMPLING_RATE_ABS_TOL,
                SAMPLING_RATE_REL_TOL,
            )
        elif key in ('trace_lon', 'trace_lat'):
            differs = _float_differs(
                existing[key], candidate[key], TRACE_COORDS_ABS_TOL
            )
        else:
            differs = _float_differs(
                existing[key], candidate[key], TRACE_DEPTH_ABS_TOL
            )
        if differs:
            changed_fields.append(
                f'{key}: stored={existing[key]} new={candidate[key]}'
            )
    if changed_fields:
        logger.warning(
            'Trace metadata differs from stored values for '
            f'{candidate["trace_id"]} '
            f'[{candidate["valid_from_utc"]}, '
            f'{candidate["valid_to_utc"]}): '
            + '; '.join(changed_fields)
        )


def _insert_trace_metadata_row(cursor, row):
    """Insert one trace metadata row, respecting interval invariants."""
    existing_rows = cursor.execute(
        f'''
        SELECT * FROM {TRACE_METADATA_TABLE}
        WHERE trace_id = ?
        ORDER BY valid_from_utc
        ''',
        (row['trace_id'],),
    ).fetchall()
    matched_existing = None
    for existing in existing_rows:
        existing_dict = dict(existing)
        if existing_dict['valid_from_utc'] == row['valid_from_utc']:
            matched_existing = existing_dict
            break
        if _intervals_overlap(existing_dict, row):
            raise PairsMetadataError(
                'Overlapping trace metadata intervals found for '
                f'{row["trace_id"]}'
            )
    if matched_existing is not None:
        if _trace_metadata_value_differs(matched_existing, row):
            _warn_trace_metadata_change(matched_existing, row)
        return
    execute_with_retry(
        lambda row=row: cursor.execute(
            f'''
            INSERT INTO {TRACE_METADATA_TABLE} (
              trace_id, valid_from_utc, valid_to_utc,
              sampling_rate_hz, trace_lon, trace_lat,
              elevation, local_depth, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                row['trace_id'],
                row['valid_from_utc'],
                row['valid_to_utc'],
                row['sampling_rate_hz'],
                row['trace_lon'],
                row['trace_lat'],
                row['elevation'],
                row['local_depth'],
                row['updated_at'],
            ),
        ),
        'insert trace metadata row',
    )


def _store_trace_metadata(cursor, pairs):
    """Insert trace metadata rows for a batch of pairs."""
    for row in _trace_metadata_rows(pairs):
        _insert_trace_metadata_row(cursor, row)


def store_trace_metadata_from_inventory(trace_ids):
    """
    Persist trace metadata rows for the given trace IDs.

    Called after the tables are initialised and the inventory is loaded,
    so that trace_metadata is populated even when no pairs are written
    (e.g. all waveform fetches fail).

    :param trace_ids: iterable of trace IDs to store metadata for
    """
    conn = get_db_connection(initdb=False)
    try:
        cursor = conn.cursor()
        for trace_id in trace_ids:
            rows = _trace_metadata_from_inventory(trace_id)
            if not rows:
                # inventory absent or trace_id not found; skip silently
                continue
            for row in rows:
                _insert_trace_metadata_row(cursor, row)
        conn.commit()
    finally:
        conn.close()
