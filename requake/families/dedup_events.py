# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Detect duplicate events from close event pairs.

Two events are considered duplicates when their pair has a high
cross-correlation coefficient, a small origin-time difference and a small
horizontal distance.  Within each group of duplicates, one event is kept
and the others are flagged as duplicates in the catalog.  All pairs
involving a duplicated event are then flagged as invalid, so that they
are ignored when families are built.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from tabulate import tabulate
from obspy.geodetics import gps2dist_azimuth
from ..config import config, rq_exit
from ..config.utils import run_with_spinner
from ..catalog import read_stored_catalog
from ..terminal import style
from ..database.db import DatabaseCorruptError, get_db_path
from ..database.catalog import (
    count_duplicate_events,
    reset_duplicate_flags,
    update_events_duplicate,
)
from ..database.pairs import (
    PairsMetadataError,
    PairsSchemaError,
    PairsTableNotFoundError,
    count_invalid_pairs,
    mark_duplicate_pairs_invalid,
    read_pairs,
    reset_invalid_pair_flags,
)
from ..database.catalogs import CatalogNotFoundError
from ..database.scans import (
    ScanNotFoundError,
    resolve_scan_id,
    scan_catalog_id,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


# Maximum number of table rows and duplicate event IDs per row printed
# in the final report, to keep it compact for large catalogs.
_MAX_REPORT_ROWS = 20
_MAX_REPORT_EVIDS = 10


class _UnionFind:
    """Union-find data structure over hashable items."""

    def __init__(self):
        self._parent = {}

    def _add(self, item):
        """Register *item* as its own root, if not already present."""
        self._parent.setdefault(item, item)

    def find(self, item):
        """Return the root of *item*, compressing the path."""
        self._add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, item1, item2):
        """Merge the sets containing *item1* and *item2*."""
        self._add(item1)
        self._add(item2)
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            self._parent[root2] = root1

    def groups(self):
        """Return the list of connected components."""
        groups = {}
        for item in self._parent:
            groups.setdefault(self.find(item), []).append(item)
        return list(groups.values())


def _distance_km(event1, event2):
    """
    Return the horizontal distance between two events in km.

    Returns ``None`` when one of the events has no coordinates.
    """
    if None in (event1.lon, event1.lat, event2.lon, event2.lat):
        return None
    distance_m, _, _ = gps2dist_azimuth(
        event1.lat, event1.lon, event2.lat, event2.lon
    )
    return distance_m / 1e3


def _completeness(event):
    """Return the number of non-missing attributes of an event."""
    values = (
        event.evid, event.orig_time, event.lon, event.lat, event.depth,
        event.mag_type, event.mag,
    )
    return sum(value is not None for value in values)


def _select_kept_event(events):
    """
    Return the event to keep among the events of a duplicate group.

    The kept event is chosen with the following preference order:

    1. events not already flagged as duplicate;
    2. higher magnitude;
    3. more complete metadata;
    4. earlier origin time;
    5. smaller event ID (for determinism).
    """
    candidates = sorted(events, key=lambda event: str(event.evid))
    return max(
        candidates,
        key=lambda event: (
            not event.duplicate,
            event.mag if event.mag is not None else float('-inf'),
            _completeness(event),
            -float(event.orig_time),
        ),
    )


def _find_duplicate_pairs(pairs, max_time_diff, max_distance_km):
    """
    Select duplicate-suspect pairs and group the events they connect.

    :param pairs: candidate event pairs, already filtered by
        cross-correlation coefficient
    :type pairs: list of RequakeEventPair
    :param max_time_diff: maximum origin-time difference (s)
    :type max_time_diff: float
    :param max_distance_km: maximum horizontal distance (km)
    :type max_distance_km: float
    :return: a ``(duplicate_pairs, groups, n_missing_location)`` tuple,
        where ``duplicate_pairs`` is a list of per-event-pair dictionaries,
        ``groups`` is a list of connected components (lists of event IDs)
        and ``n_missing_location`` is the number of pairs skipped because
        of missing coordinates
    :rtype: tuple
    """
    duplicate_pairs = {}
    union_find = _UnionFind()
    n_missing_location = 0
    for pair in pairs:
        evid1 = pair.event1.evid
        evid2 = pair.event2.evid
        time_diff = abs(pair.event1.orig_time - pair.event2.orig_time)
        if time_diff > max_time_diff:
            continue
        distance_km = _distance_km(pair.event1, pair.event2)
        if distance_km is None:
            n_missing_location += 1
            continue
        if distance_km > max_distance_km:
            continue
        key = (evid1, evid2) if evid1 <= evid2 else (evid2, evid1)
        entry = duplicate_pairs.get(key)
        if entry is None:
            duplicate_pairs[key] = {
                'evid1': key[0],
                'evid2': key[1],
                'cc_max': pair.cc_max,
                'time_diff': time_diff,
                'distance_km': distance_km,
            }
        elif pair.cc_max > entry['cc_max']:
            entry['cc_max'] = pair.cc_max
        union_find.union(evid1, evid2)
    sorted_pairs = [duplicate_pairs[key] for key in sorted(duplicate_pairs)]
    return sorted_pairs, union_find.groups(), n_missing_location


def _group_duplicates(groups, events):
    """
    Build the list of duplicate groups with their kept event.

    :param groups: connected components of event IDs
    :type groups: list of list
    :param events: mapping from event ID to event
    :type events: dict
    :return: a ``(groups_info, duplicate_evids)`` tuple, where
        ``groups_info`` is a list of ``(kept_evid, duplicate_evids)``
        tuples and ``duplicate_evids`` is the set of all duplicated events
    :rtype: tuple
    """
    groups_info = []
    duplicate_evids = set()
    for group in groups:
        group_events = [
            events[evid] for evid in sorted(group) if evid in events
        ]
        if not group_events:
            continue
        kept = _select_kept_event(group_events)
        duplicates = sorted(
            event.evid for event in group_events if event.evid != kept.evid
        )
        groups_info.append((kept.evid, duplicates))
        duplicate_evids.update(duplicates)
    groups_info.sort()
    return groups_info, duplicate_evids


def _table_title(name, count):
    """Return a table title, mentioning truncation when needed."""
    if count > _MAX_REPORT_ROWS:
        return f'{name} (first {_MAX_REPORT_ROWS} of {count})'
    return name


def _compact_evids(evids):
    """Return a compact string for a list of event IDs."""
    if len(evids) <= _MAX_REPORT_EVIDS:
        return ', '.join(evids)
    shown = ', '.join(evids[:_MAX_REPORT_EVIDS])
    remaining = len(evids) - _MAX_REPORT_EVIDS
    return f'{shown}, ... (+{remaining} more)'


def _print_pairs_table(duplicate_pairs, duplicate_evids):
    """Print a (possibly truncated) table of duplicate event pairs."""
    headers = [
        'evid1', 'evid2', 'cc max', 'time diff (s)',
        'distance (km)', 'duplicate evid'
    ]
    rows = []
    for entry in duplicate_pairs[:_MAX_REPORT_ROWS]:
        duplicated = ','.join(
            evid for evid in (entry['evid1'], entry['evid2'])
            if evid in duplicate_evids
        )
        rows.append([
            entry['evid1'], entry['evid2'], entry['cc_max'],
            entry['time_diff'], entry['distance_km'], duplicated,
        ])
    print(style(_table_title('Duplicate pairs', len(duplicate_pairs)), 'bold'))
    print(tabulate(
        rows, headers=headers, tablefmt='simple',
        floatfmt=('.6g', '.6g', '.2f', '.3f', '.3f', '.6g'),
    ))


def _print_groups_table(groups_info):
    """Print a (possibly truncated) table of duplicate groups."""
    headers = ['group', 'kept evid', 'duplicate evids']
    rows = [
        [index, kept_evid, _compact_evids(duplicates)]
        for index, (kept_evid, duplicates) in enumerate(
            groups_info[:_MAX_REPORT_ROWS], start=1
        )
    ]
    print(style(_table_title('Duplicate groups', len(groups_info)), 'bold'))
    print(tabulate(rows, headers=headers, tablefmt='simple'))


def _print_report(report):
    """Print the deduplication report to screen."""
    title = 'Duplicate events report'
    print()
    print(style(title, 'bold'))
    print('-' * len(title))
    print(
        f'Thresholds: cc >= {report["cc_min"]:.2f}, '
        f'time difference <= {report["max_time_diff"]:g} s, '
        f'distance <= {report["max_distance_km"]:g} km'
    )
    print(f'Pairs analyzed: {report["n_pairs"]}')
    if report['n_missing_location']:
        print(
            'Pairs skipped for missing coordinates: '
            f'{report["n_missing_location"]}'
        )
    print(f'Duplicate pairs found: {len(report["duplicate_pairs"])}')
    print(f'Duplicate groups found: {len(report["groups_info"])}')
    print(
        'Events identified as duplicate: '
        f'{len(report["duplicate_evids"])}'
    )
    if report['dry_run']:
        print(style('Dry run: the database was not modified.', 'dim'))
    else:
        print(f'Catalog events updated: {report["n_flagged"]}')
        print(f'Event pairs flagged as invalid: {report["n_invalid"]}')
    if report['duplicate_pairs']:
        print()
        _print_pairs_table(
            report['duplicate_pairs'], report['duplicate_evids']
        )
    if report['groups_info']:
        print()
        _print_groups_table(report['groups_info'])


def _reset_flags(dry_run, scan_id, catalog_id):
    """
    Reset the duplicate and invalid flags.

    This scans the whole event-pairs table, so on large catalogs it can
    take a while: an animated progress indicator is shown while it runs.

    :param dry_run: when True, only count the flagged rows
    :type dry_run: bool
    :param scan_id: scan whose pairs are considered
    :type scan_id: int
    :param catalog_id: catalog whose events are considered
    :type catalog_id: int
    :return: a ``(n_events, n_pairs)`` tuple
    :rtype: tuple
    """
    if dry_run:
        return run_with_spinner(
            'Counting flagged events and invalid event pairs...',
            lambda: (
                count_duplicate_events(catalog_id),
                count_invalid_pairs(scan_id),
            ),
        )
    return run_with_spinner(
        'Resetting duplicate and invalid flags...',
        lambda: (
            reset_duplicate_flags(catalog_id),
            reset_invalid_pair_flags(scan_id),
        ),
    )


def _print_reset_report(n_events, n_pairs, dry_run):
    """Print the flag-reset report to screen."""
    title = 'Duplicate events report'
    print()
    print(style(title, 'bold'))
    print('-' * len(title))
    if dry_run:
        print('Reset mode: duplicate and invalid flags would be cleared, '
              'no detection performed.')
        print(f'Catalog events to un-flag: {n_events}')
        print(f'Event pairs to un-flag: {n_pairs}')
        print(style('Dry run: the database was not modified.', 'dim'))
    else:
        print('Reset mode: duplicate and invalid flags cleared, '
              'no detection performed.')
        print(f'Catalog events un-flagged: {n_events}')
        print(f'Event pairs un-flagged: {n_pairs}')


def dedup_events():
    """Find duplicate events from close pairs and flag them."""
    dry_run = config.args.dry_run
    try:
        scan_id = resolve_scan_id(getattr(config.args, 'scan_id', None))
        catalog_id = scan_catalog_id(scan_id)
    except (ScanNotFoundError, CatalogNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if config.args.reset:
        n_events, n_pairs = _reset_flags(dry_run, scan_id, catalog_id)
        _print_reset_report(n_events, n_pairs, dry_run)
        if dry_run:
            logger.info(
                f'{n_events} events and {n_pairs} event pairs would be reset'
            )
        else:
            logger.info(f'{n_events} events and {n_pairs} event pairs reset')
        return
    cc_min = config.args.cc_min
    max_time_diff = config.args.max_time_diff
    max_distance_km = config.args.max_distance
    try:
        catalog = run_with_spinner(
            'Reading event catalog...',
            lambda: read_stored_catalog(catalog_id=catalog_id),
        )
    except (ValueError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    pairs_message = (
        f'Reading event pairs of scan {scan_id} with cc >= {cc_min:.2f} '
        f'from db file {get_db_path()}...'
    )
    try:
        pairs = run_with_spinner(
            pairs_message,
            lambda: read_pairs(scan_id=scan_id, cc_min=cc_min),
        )
    except (
        DatabaseCorruptError,
        FileNotFoundError,
        PairsMetadataError,
        PairsSchemaError,
        PairsTableNotFoundError,
    ) as msg:
        logger.error(msg)
        rq_exit(1)
    detection_message = (
        f'Looking for duplicate events in {len(pairs):n} event pairs...'
    )
    duplicate_pairs, groups, n_missing_location = run_with_spinner(
        detection_message,
        lambda: _find_duplicate_pairs(
            pairs, max_time_diff, max_distance_km
        ),
    )
    events = {event.evid: event for event in catalog}
    groups_info, duplicate_evids = _group_duplicates(groups, events)
    n_flagged = 0
    n_invalid = 0
    if not dry_run and duplicate_evids:
        flag_message = (
            f'Flagging {len(duplicate_evids)} events as duplicate...'
        )
        n_flagged, n_invalid = run_with_spinner(
            flag_message,
            lambda: (
                update_events_duplicate(duplicate_evids, catalog_id),
                mark_duplicate_pairs_invalid(scan_id),
            ),
        )
    report = {
        'cc_min': cc_min,
        'max_time_diff': max_time_diff,
        'max_distance_km': max_distance_km,
        'n_pairs': len(pairs),
        'n_missing_location': n_missing_location,
        'duplicate_pairs': duplicate_pairs,
        'groups_info': groups_info,
        'duplicate_evids': duplicate_evids,
        'n_flagged': n_flagged,
        'n_invalid': n_invalid,
        'dry_run': dry_run,
    }
    _print_report(report)
    if not dry_run:
        logger.info(
            f'{n_flagged} events flagged as duplicate, '
            f'{n_invalid} event pairs flagged as invalid'
        )
