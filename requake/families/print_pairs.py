# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print pairs to screen.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import sys
from ..config import config, rq_exit
from ..config.generic_printer import _display_table
from ..config.utils import status, run_with_spinner
from ..terminal import style, warning
from ..database.db import DatabaseCorruptError
from ..database.pairs import (
    PairsMetadataError,
    PairsSchemaError,
    PairsTableNotFoundError,
    count_pairs_up_to,
    read_pairs,
)
from ..database.catalogs import CatalogNotFoundError
from ..database.scans import ScanNotFoundError, resolve_scan_id
from ..pager import DatabaseDataSource
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

# Warn when there are more pairs than this threshold.
_PAIRS_WARNING_THRESHOLD = 10_000
_COPY_FN = lambda r: f'{r[0]} {r[1]}'  # noqa: E731


_WARNING_HEADLINE = 'There are {count} pairs to display.'
_WARNING_BODY = (
    'This may be slow and memory-intensive.\n'
    'Consider using --cc_min and --cc_max to reduce the number '
    'of pairs.\n'
    'Use --force to skip this warning.\n'
)
_WARNING_PROMPT = 'Continue? [y/N] '


# Mapping from column index to SQL ORDER BY expression for
# database-backed pager sorting.
_PAIRS_SORT_COLUMNS = [
    'e1.evid',       # 0: evid1
    'e2.evid',       # 1: evid2
    'tk.trace_id',   # 2: trace id
    'c1.orig_time',  # 3: origin time1
    'c1.lon',        # 4: lon1
    'c1.lat',        # 5: lat1
    'c1.depth_km',   # 6: depth1
    'c1.mag_type',   # 7: mag1 type
    'c1.mag',        # 8: mag1
    'c2.orig_time',   # 9: origin time2
    'c2.lon',         # 10: lon2
    'c2.lat',         # 11: lat2
    'c2.depth_km',    # 12: depth2
    'c2.mag_type',    # 13: mag2 type
    'c2.mag',         # 14: mag2
    'p.lag_samples',  # 15: lag (samp)
    'p.lag_samples',  # 16: lag (sec) — approximate, same order
    'p.cc_x100',      # 17: cc max
    'p.invalid',      # 18: invalid
]


_PAIRS_FIELDS = [
    'evid1', 'evid2', 'trace id',
    'origin time1', 'lon1', 'lat1', 'depth1 (km)',
    'mag1 type', 'mag1',
    'origin time2', 'lon2', 'lat2', 'depth2 (km)',
    'mag2 type', 'mag2',
    'lag (samp)', 'lag (sec)', 'cc max'
]

_INVALID_FIELD = 'invalid'


def _pairs_fields(include_invalid):
    """Return the table fields, optionally including the invalid flag."""
    fields = list(_PAIRS_FIELDS)
    if include_invalid:
        fields.append(_INVALID_FIELD)
    return fields


def _row_from_pair(pair, include_invalid=False):
    """Convert a RequakeEventPair to a flat row list."""
    row = [
        pair.event1.evid,
        pair.event2.evid,
        pair.trace_id,
        pair.event1.orig_time,
        pair.event1.lon,
        pair.event1.lat,
        pair.event1.depth,
        pair.event1.mag_type,
        pair.event1.mag,
        pair.event2.orig_time,
        pair.event2.lon,
        pair.event2.lat,
        pair.event2.depth,
        pair.event2.mag_type,
        pair.event2.mag,
        pair.lag_samples,
        pair.lag_sec,
        pair.cc_max
    ]
    if include_invalid:
        row.append(pair.invalid)
    return row


def _build_pairs_db_source(scan_id, cc_min, cc_max, include_invalid=False,
                           total_count=None):
    """Build a DatabaseDataSource for pairs.

    When *total_count* is provided it is used directly, avoiding
    a separate ``COUNT(*)`` query.
    """
    def query_fn(sort_col, sort_asc, offset, limit):
        order_by = None
        if sort_col is not None and sort_col < len(_PAIRS_SORT_COLUMNS):
            order_by = (_PAIRS_SORT_COLUMNS[sort_col], sort_asc)
        pairs = read_pairs(
            scan_id=scan_id, cc_min=cc_min, cc_max=cc_max,
            offset=offset, limit=limit, order_by=order_by,
            include_invalid=include_invalid
        )
        return [_row_from_pair(p, include_invalid) for p in pairs]

    def count_fn():
        if total_count is not None:
            return total_count
        return read_pairs(
            scan_id=scan_id, cc_min=cc_min, cc_max=cc_max, count_only=True,
            include_invalid=include_invalid
        )

    return DatabaseDataSource(_pairs_fields(include_invalid), query_fn,
                              count_fn)


def print_pairs():
    """Print pairs to screen."""
    status('Preparing pairs table...')
    cc_min = config.args.cc_min
    cc_max = config.args.cc_max
    include_invalid = getattr(config.args, 'include_invalid', False)
    try:
        scan_id = resolve_scan_id(getattr(config.args, 'scan_id', None))
        count = run_with_spinner(
            'Counting matching pairs...',
            lambda: count_pairs_up_to(
                scan_id, cc_min, cc_max, _PAIRS_WARNING_THRESHOLD,
                include_invalid=include_invalid
            ),
        )
        if (
            count > _PAIRS_WARNING_THRESHOLD
            and not getattr(config.args, 'force', False)
        ):
            _ask_large_dataset_confirmation()
        _print_pairs_table(
            scan_id, cc_min, cc_max, count, include_invalid
        )
    except (
        DatabaseCorruptError,
        FileNotFoundError,
        PairsMetadataError,
        PairsSchemaError,
        PairsTableNotFoundError,
        ScanNotFoundError,
        CatalogNotFoundError,
    ) as msg:
        logger.error(msg)
        rq_exit(1)


def _print_pairs_table(scan_id, cc_min, cc_max, count,
                       include_invalid=False):
    """Display pairs, using in-memory mode for small result sets."""
    if count <= _PAIRS_WARNING_THRESHOLD:
        pairs = run_with_spinner(
            f'Loading {count} pairs...',
            lambda: read_pairs(
                scan_id=scan_id, cc_min=cc_min, cc_max=cc_max,
                include_invalid=include_invalid
            ),
        )
        rows = [_row_from_pair(p, include_invalid) for p in pairs]
        headers_fmt = [(f, None) for f in _pairs_fields(include_invalid)]
        _display_table(
            headers_fmt, rows,
            row_label='Pairs',
            copy_label='evid1 evid2',
            copy_fn=_COPY_FN,
            detail_title='Pair Details',
        )
    else:
        # Use database-backed pager for large result sets.
        db_source = _build_pairs_db_source(
            scan_id, cc_min, cc_max, include_invalid=include_invalid,
            total_count=count
        )
        _display_table(
            None, data_source=db_source,
            row_label='Pairs',
            copy_label='evid1 evid2',
            copy_fn=_COPY_FN,
            detail_title='Pair Details',
        )


def _ask_large_dataset_confirmation():
    """Ask the user to confirm browsing a large dataset."""
    if not sys.stdout.isatty():
        return  # pipe/redirect: proceed silently
    try:
        headline = warning(
            _WARNING_HEADLINE.format(
                count=f'more than {_PAIRS_WARNING_THRESHOLD:,}'
            )
        )
        prompt = (
            f'\n{headline}\n{_WARNING_BODY}'
            f'{style(_WARNING_PROMPT, "dim")}'
        )
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        rq_exit(1)
    if answer.strip().lower() not in ('y', 'yes'):
        rq_exit(0)
