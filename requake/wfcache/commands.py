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
import sys
from copy import copy
from pathlib import Path

from obspy import UTCDateTime
from tqdm import tqdm

from ..config import config, rq_exit
from ..config.parse_arguments import _timespec_to_sec
from .storage import (
    list_waveform_cache_rows,
    read_waveform_cache_summary,
    read_waveform_from_cache,
    reset_waveform_failures,
)

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def wfcache_prefetch():
    """Prefetch waveform windows from stored catalog into cache."""
    from ..catalog import fix_non_locatable_events, read_stored_catalog
    from ..waveforms import NoWaveformError, get_event_waveform

    try:
        catalog = read_stored_catalog()
    except (ValueError, FileNotFoundError) as err:
        logger.error(err)
        rq_exit(1)
    try:
        fix_non_locatable_events(catalog)
    except Exception as err:  # pylint: disable=broad-except
        logger.error(err)
        rq_exit(1)

    event_ids = set(getattr(config.args, 'event_id', []) or [])
    event_id_file = getattr(config.args, 'event_id_file', None)
    if event_id_file:
        event_ids.update(_read_event_ids_file(event_id_file))

    trace_ids = _resolve_prefetch_trace_ids()
    if not trace_ids:
        logger.error('No trace IDs available for prefetch.')
        rq_exit(1)

    filtered_catalog = _filter_prefetch_catalog(catalog, event_ids)

    nevents = len(filtered_catalog)
    if nevents == 0:
        print('No catalog events matched prefetch filters.')
        rq_exit(0)

    batch_size = max(int(getattr(config.args, 'batch_size', 500)), 1)
    total_attempts = nevents * len(trace_ids)
    fetched = 0
    unavailable = 0
    unexpected_errors = 0
    attempted = 0

    logger.info(
        f'Prefetching {total_attempts:n} waveform windows '
        f'({nevents:n} events x {len(trace_ids):n} trace IDs).'
    )
    progress_ctx = _init_prefetch_progress(total_attempts)
    for event in filtered_catalog:
        for trace_id in trace_ids:
            attempted += 1
            status = _prefetch_one_waveform(
                event,
                trace_id,
                get_event_waveform,
                NoWaveformError,
            )
            if status == 'fetched':
                fetched += 1
            elif status == 'unavailable':
                unavailable += 1
            else:
                unavailable += 1
                unexpected_errors += 1
            _update_prefetch_progress(
                progress_ctx,
                attempted,
                total_attempts,
                batch_size,
                fetched,
                unavailable,
                unexpected_errors,
            )

    pbar = progress_ctx['pbar']
    if pbar is not None:
        pbar.close()

    summary = (
        f'Prefetch complete: attempted={attempted:n}, '
        f'fetched={fetched:n}, unavailable={unavailable:n}'
    )
    if unexpected_errors > 0:
        summary += f' (unexpected errors={unexpected_errors:n})'
    print(summary)
    rq_exit(0 if unexpected_errors == 0 else 1)


def _resolve_prefetch_trace_ids():
    """Resolve trace IDs to use for prefetch."""
    trace_ids = list(getattr(config.args, 'trace_id', []) or [])
    return trace_ids or list(getattr(config, 'catalog_trace_id', []))


def _init_prefetch_progress(total_attempts):
    """Initialize progress context for prefetch command."""
    show_pbar = sys.stderr.isatty()
    pbar = None
    if show_pbar:
        pbar = tqdm(
            total=total_attempts,
            unit='traces',
            unit_scale=True,
            desc=f'Prefetching {total_attempts:n} waveform windows',
        )
    return {
        'show_pbar': show_pbar,
        'pbar': pbar,
    }


def _update_prefetch_progress(
    progress_ctx,
    attempted,
    total_attempts,
    batch_size,
    fetched,
    unavailable,
    unexpected_errors,
):
    """Update prefetch progress display/logging."""
    if progress_ctx['show_pbar']:
        pbar = progress_ctx['pbar']
        pbar.update(1)
        pbar.set_postfix_str(
            f'fetched={fetched:n} '
            f'unavailable={unavailable:n}'
        )
        return
    _log_prefetch_progress(
        attempted,
        total_attempts,
        batch_size,
        fetched,
        unavailable,
        unexpected_errors,
    )


def _filter_prefetch_catalog(catalog, event_ids):
    """Apply event-id and max-events filters to catalog."""
    filtered_catalog = [
        ev for ev in catalog
        if not event_ids or ev.evid in event_ids
    ]
    max_events = getattr(config.args, 'max_events', None)
    if max_events is not None:
        return filtered_catalog[:max_events]
    return filtered_catalog


def _prefetch_one_waveform(event, trace_id, fetch_func, no_waveform_error):
    """Prefetch one waveform and return status string."""
    event_prefetch = copy(event)
    event_prefetch.trace_id = trace_id
    try:
        trace = fetch_func(event_prefetch)
    except no_waveform_error:
        return 'unavailable'
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            f'Unexpected prefetch error for {event.evid}/{trace_id}: {err}'
        )
        return 'failed'
    return 'fetched' if trace is not None else 'unavailable'


def _log_prefetch_progress(
    attempted,
    total_attempts,
    batch_size,
    fetched,
    unavailable,
    unexpected_errors,
):
    """Log periodic prefetch progress for non-interactive runs."""
    if attempted % batch_size != 0 and attempted != total_attempts:
        return
    logger.info(
        f'Prefetch progress: {attempted:n}/{total_attempts:n} '
        f'(fetched={fetched:n}, unavailable={unavailable:n})'
    )
    if unexpected_errors > 0:
        logger.info(
            f'Prefetch unexpected errors so far: {unexpected_errors:n}'
        )


def wfcache_extract():
    """Extract filtered cached waveform rows to waveform files."""
    try:
        row_filters = _collect_row_filters()
    except Exception as err:  # pylint: disable=broad-except
        logger.error(err)
        rq_exit(2)

    rows = list_waveform_cache_rows(**row_filters)
    if not rows:
        print('No cached waveform rows matched the requested filters.')
        rq_exit(0)

    output_dir = Path(config.args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_format = str(config.args.format).lower()
    file_ext = '.mseed' if output_format == 'mseed' else '.sac'
    obspy_format = 'MSEED' if output_format == 'mseed' else 'SAC'

    written = 0
    missing = 0
    failed = 0
    for row in rows:
        start_time = UTCDateTime(row['start_time'])
        end_time = UTCDateTime(row['end_time'])
        trace = read_waveform_from_cache(
            row['evid'],
            row['trace_id'],
            start_time,
            end_time,
        )
        if trace is None:
            missing += 1
            continue
        output_name = row['entry'].removesuffix('.mseed') + file_ext
        output_path = output_dir / output_name
        try:
            trace.write(str(output_path), format=obspy_format)
        except Exception as err:  # pylint: disable=broad-except
            failed += 1
            logger.error(f'Failed to write {output_path}: {err}')
            continue
        written += 1

    print(
        f'Extracted {written:n} cached waveforms to {output_dir} '
        f'(missing={missing:n}, failed={failed:n}).'
    )
    rq_exit(0 if failed == 0 else 1)


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
