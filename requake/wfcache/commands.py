# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
CLI commands for waveform cache management.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import json
import logging
from pathlib import Path

from obspy import UTCDateTime

from ..config import config, rq_exit
from ..config.parse_arguments import _timespec_to_sec
from .storage import (
    list_waveform_cache_rows,
    read_waveform_cache_summary,
    reset_waveform_failures,
)

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def wfcache_prefetch():
    """Return a placeholder error for explicit prefetch command."""
    logger.error(
        'wfcache prefetch is not implemented yet. '
        'This command will be added in a later phase.'
    )
    rq_exit(1)


def wfcache_extract():
    """Return a placeholder error for extraction command."""
    logger.error(
        'wfcache extract is not implemented yet. '
        'Use "requake wfcache print" with the same filters to preview '
        'matching rows.'
    )
    rq_exit(1)


def _collect_row_filters():
    """Collect common row filters shared by print and extract."""
    event_ids = list(getattr(config.args, 'event_id', []) or [])
    event_id_file = getattr(config.args, 'event_id_file', None)
    if event_id_file:
        event_ids.extend(_read_event_ids_file(event_id_file))

    trace_ids = list(getattr(config.args, 'trace_id', []) or [])

    start_time = None
    start_time_str = getattr(config.args, 'start_time', None)
    if start_time_str is not None:
        start_time = UTCDateTime(start_time_str)

    end_time = None
    end_time_str = getattr(config.args, 'end_time', None)
    if end_time_str is not None:
        end_time = UTCDateTime(end_time_str)

    return {
        'event_ids': event_ids,
        'trace_ids': trace_ids,
        'start_time': start_time,
        'end_time': end_time,
        'limit': getattr(config.args, 'limit', None),
    }


def wfcache_print():
    """Print cached waveform rows as file-like entries."""
    try:
        row_filters = _collect_row_filters()
    except Exception as err:  # pylint: disable=broad-except
        logger.error(err)
        rq_exit(2)
    rows = list_waveform_cache_rows(**row_filters)
    if bool(getattr(config.args, 'json', False)):
        print(json.dumps(rows, indent=2, sort_keys=True))
        rq_exit(0)
    if not rows:
        print('No cached waveform rows found.')
        rq_exit(0)
    for row in rows:
        print(row['entry'])
    rq_exit(0)


def wfcache_inspect():
    """Print waveform-cache diagnostics and summary."""
    summary = read_waveform_cache_summary(
        integrity=bool(getattr(config.args, 'integrity', False))
    )
    if bool(getattr(config.args, 'json', False)):
        print(json.dumps(summary, indent=2, sort_keys=True))
        rq_exit(0)
    print(f'waveform cache path: {summary["path"]}')
    print(f'cache exists: {summary["exists"]}')
    if summary['exists']:
        size_mib = summary['file_size_bytes'] / (1024.0 * 1024.0)
        print(f'file size: {size_mib:.3f} MiB')
        print(f'schema version: {summary["schema_version"]}')
        print(f'waveform rows: {summary["waveform_rows"]:n}')
        print(
            'time span: '
            f'{summary["time_span_start"]} -> {summary["time_span_end"]}'
        )
        top_trace_ids = summary['top_trace_ids']
        if top_trace_ids:
            print('top trace IDs:')
            for row in top_trace_ids:
                print(f'  {row["trace_id"]}: {row["rows"]:n}')
        if summary['integrity_check'] is not None:
            print(f'integrity check: {summary["integrity_check"]}')
    print(
        'negative cache: '
        f'total={summary["failure_rows"]:n}, '
        f'exhausted={summary["failure_exhausted_rows"]:n}, '
        f'retry-pending={summary["failure_retry_pending_rows"]:n}'
    )
    rq_exit(0)


def _read_event_ids_file(path):
    """Read event IDs from a text file."""
    event_ids = []
    with Path(path).open('r', encoding='utf8') as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            event_ids.append(line)
    return event_ids


def wfcache_reset_failures():
    """Reset persistent waveform failure-cache records."""
    event_ids = list(getattr(config.args, 'event_id', []) or [])
    event_id_file = getattr(config.args, 'event_id_file', None)
    if event_id_file:
        event_ids.extend(_read_event_ids_file(event_id_file))
    clear_all = bool(getattr(config.args, 'all', False))
    older_than_spec = getattr(config.args, 'older_than', None)
    older_than_s = None
    if older_than_spec is not None:
        try:
            older_than_s = _timespec_to_sec(older_than_spec)
        except ValueError as err:
            logger.error(err)
            rq_exit(2)
    affected = reset_waveform_failures(
        event_ids=event_ids,
        older_than_s=older_than_s,
        dry_run=bool(getattr(config.args, 'dry_run', False)),
        clear_all=clear_all,
    )
    mode = 'would reset' if config.args.dry_run else 'reset'
    print(f'{mode} {affected:n} waveform failure-cache rows')
    rq_exit(0)
