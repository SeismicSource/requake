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
from pathlib import Path

from obspy import UTCDateTime
from obspy.geodetics import gps2dist_azimuth
from tqdm import tqdm

from ..config import config, rq_exit
from ..config.parse_arguments import _timespec_to_sec
from .storage import (
    begin_cache_write_batch,
    clear_waveform_failure,
    commit_cache_write_batch,
    list_waveform_cache_rows,
    read_waveform_cache_summary,
    read_waveform_from_cache,
    register_waveform_failure,
    reset_waveform_failures,
    run_wal_checkpoint,
    should_skip_waveform_download,
    write_cache_meta,
    write_waveform_to_cache,
)

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def wfcache_prefetch():
    """Prefetch waveform windows from stored catalog into cache."""
    dependencies = _load_prefetch_dependencies()
    catalog = _read_prefetch_catalog(
        dependencies['read_stored_catalog'],
        dependencies['fix_non_locatable_events'],
    )
    event_ids = _collect_prefetch_event_ids()
    trace_ids, filtered_catalog = _prepare_prefetch_scope(catalog, event_ids)

    nevents = len(filtered_catalog)
    if nevents == 0:
        print('No catalog events matched prefetch filters.')
        rq_exit(0)

    batch_size = max(int(getattr(config.args, 'batch_size', 500)), 1)
    group_window_s = _resolve_group_window_seconds()
    total_attempts = nevents * len(trace_ids)
    counters = {
        'fetched': 0,
        'unavailable': 0,
        'unexpected_errors': 0,
        'attempted': 0,
    }

    logger.info(
        f'Prefetching {total_attempts:n} waveform windows '
        f'({nevents:n} events x {len(trace_ids):n} trace IDs).'
    )
    progress_ctx = _init_prefetch_progress(total_attempts)
    pending_by_trace = _prepare_prefetch_pending_requests(
        filtered_catalog,
        trace_ids,
        dependencies,
        progress_ctx,
        total_attempts,
        batch_size,
        counters,
    )
    for trace_id in trace_ids:
        groups = _group_prefetch_requests(
            pending_by_trace[trace_id],
            group_window_s,
        )
        for group in groups:
            statuses = _download_prefetch_group(
                trace_id,
                group,
                dependencies['get_waveform_from_client'],
                dependencies['NoWaveformError'],
            )
            for status in statuses:
                _record_prefetch_status(
                    progress_ctx,
                    total_attempts,
                    batch_size,
                    counters,
                    status,
                )

    pbar = progress_ctx['pbar']
    if pbar is not None:
        pbar.close()

    summary = (
        f'Prefetch complete: attempted={counters["attempted"]:n}, '
        f'fetched={counters["fetched"]:n}, '
        f'unavailable={counters["unavailable"]:n}'
    )
    if counters['unexpected_errors'] > 0:
        summary += (
            ' '
            f'(unexpected errors={counters["unexpected_errors"]:n})'
        )
    print(summary)
    run_wal_checkpoint()
    rq_exit(0 if counters['unexpected_errors'] == 0 else 1)


def _load_prefetch_dependencies():
    """Load prefetch-only imports lazily to avoid circular imports."""
    from ..catalog import fix_non_locatable_events, read_stored_catalog
    from ..waveforms import NoWaveformError, get_waveform_from_client
    from ..waveforms.arrivals import get_arrivals
    from ..waveforms.station_metadata import (
        MetadataMismatchError,
        get_traceid_coords,
    )
    return {
        'fix_non_locatable_events': fix_non_locatable_events,
        'read_stored_catalog': read_stored_catalog,
        'NoWaveformError': NoWaveformError,
        'get_waveform_from_client': get_waveform_from_client,
        'get_arrivals': get_arrivals,
        'MetadataMismatchError': MetadataMismatchError,
        'get_traceid_coords': get_traceid_coords,
    }


def _read_prefetch_catalog(read_catalog_func, fix_catalog_func):
    """Read stored catalog and sanitize non-locatable events."""
    try:
        catalog = read_catalog_func()
    except (ValueError, FileNotFoundError) as err:
        logger.error(err)
        rq_exit(1)
    try:
        fix_catalog_func(catalog)
    except Exception as err:  # pylint: disable=broad-except
        logger.error(err)
        rq_exit(1)
    return catalog


def _collect_prefetch_event_ids():
    """Collect event-id filters from CLI and optional file."""
    event_ids = set(getattr(config.args, 'event_id', []) or [])
    event_id_file = getattr(config.args, 'event_id_file', None)
    if event_id_file:
        event_ids.update(_read_event_ids_file(event_id_file))
    return event_ids


def _prepare_prefetch_scope(catalog, event_ids):
    """Resolve trace IDs and filtered catalog for prefetch."""
    trace_ids = _resolve_prefetch_trace_ids()
    if not trace_ids:
        logger.error('No trace IDs available for prefetch.')
        rq_exit(1)
    filtered_catalog = _filter_prefetch_catalog(catalog, event_ids)
    return trace_ids, filtered_catalog


def _prepare_prefetch_pending_requests(
    filtered_catalog,
    trace_ids,
    dependencies,
    progress_ctx,
    total_attempts,
    batch_size,
    counters,
):
    """Prepare pending grouped requests while accounting cache hits/misses.

    Events are processed in catalog order (chronological by orig_time),
    which matches the order scan_catalog consumes pairs.  This ensures
    that when the two processes run in parallel, the earliest events
    are cached before scan_catalog reaches them.
    """
    pending_by_trace = {
        trace_id: [] for trace_id in trace_ids
    }
    prepared = 0
    queued = 0
    traceid_coords = _resolve_prefetch_trace_coords_map(
        filtered_catalog,
        dependencies['get_traceid_coords'],
        dependencies['MetadataMismatchError'],
    )
    for trace_id in trace_ids:
        trace_coords = None if traceid_coords is None else traceid_coords.get(
            trace_id
        )
        standard_offsets = _compute_prefetch_standard_offsets(
            filtered_catalog,
            trace_id,
            trace_coords,
            dependencies['get_arrivals'],
        )
        # Persist standardized window offsets so that independent
        # processes (e.g. scan_catalog) can use the same window.
        if standard_offsets is not None:
            write_cache_meta(
                f'tp_min_{trace_id}',
                str(standard_offsets['tp_closest_s']),
            )
            write_cache_meta(
                f'tp_max_{trace_id}',
                str(standard_offsets['tp_farthest_s']),
            )
        for event in filtered_catalog:
            if standard_offsets is None:
                status = 'unavailable'
                request = None
            else:
                status, request = _prepare_prefetch_request(
                    event,
                    trace_id,
                    standard_offsets,
                )
            if status == 'pending':
                pending_by_trace[trace_id].append(request)
                queued += 1
            else:
                _record_prefetch_status(
                    progress_ctx,
                    total_attempts,
                    batch_size,
                    counters,
                    status,
                )
            prepared += 1
            _report_prefetch_prepare_progress(
                progress_ctx,
                prepared,
                total_attempts,
                batch_size,
                queued,
            )
    return pending_by_trace


def _resolve_prefetch_trace_coords_map(
    filtered_catalog,
    get_traceid_coords_func,
    metadata_error,
):
    """Resolve trace coordinates once for prefetch execution."""
    if not filtered_catalog:
        return {}
    reference_time = filtered_catalog[0].orig_time
    try:
        return get_traceid_coords_func(reference_time)
    except metadata_error as err:
        logger.warning(
            'Skipping prefetch because trace metadata lookup failed: '
            f'{_safe_error(err)}'
        )
        return None


def _compute_prefetch_standard_offsets(
    filtered_catalog,
    trace_id,
    trace_coords,
    get_arrivals_func,
):
    """Compute standardized P-arrival offsets for one trace id."""
    if trace_coords is None:
        logger.warning(
            'Skipping prefetch for trace '
            f'{trace_id}: missing trace metadata'
        )
        return None
    closest, farthest = _find_closest_and_farthest_events(
        filtered_catalog,
        trace_coords,
    )
    if closest is None or farthest is None:
        logger.warning(
            'Skipping prefetch for trace '
            f'{trace_id}: no catalog events available'
        )
        return None
    tp_closest = _compute_p_arrival_seconds(
        closest,
        trace_id,
        trace_coords,
        get_arrivals_func,
    )
    if tp_closest is None:
        return None
    if closest.evid == farthest.evid:
        tp_farthest = tp_closest
    else:
        tp_farthest = _compute_p_arrival_seconds(
            farthest,
            trace_id,
            trace_coords,
            get_arrivals_func,
        )
        if tp_farthest is None:
            return None
    return {
        'tp_closest_s': min(tp_closest, tp_farthest),
        'tp_farthest_s': max(tp_closest, tp_farthest),
    }


def _find_closest_and_farthest_events(filtered_catalog, trace_coords):
    """Return closest and farthest events by hypocentral distance."""
    closest_event = None
    farthest_event = None
    min_distance = None
    max_distance = None
    for event in filtered_catalog:
        distance = _hypocentral_distance_km(event, trace_coords)
        if min_distance is None or distance < min_distance:
            min_distance = distance
            closest_event = event
        if max_distance is None or distance > max_distance:
            max_distance = distance
            farthest_event = event
    return closest_event, farthest_event


def _hypocentral_distance_km(event, trace_coords):
    """Compute hypocentral distance (km) between event and station."""
    horizontal_m, _, _ = gps2dist_azimuth(
        trace_coords['latitude'],
        trace_coords['longitude'],
        event.lat,
        event.lon,
    )
    horizontal_km = horizontal_m / 1e3
    depth_km = max(float(event.depth), 0.0)
    return (horizontal_km ** 2 + depth_km ** 2) ** 0.5


def _compute_p_arrival_seconds(
    event,
    trace_id,
    trace_coords,
    get_arrivals_func,
):
    """Compute P-arrival travel time (seconds) for one event/trace."""
    ev_depth = max(event.depth, 0)
    try:
        p_arrival, _, _, _ = get_arrivals_func(
            trace_coords['latitude'],
            trace_coords['longitude'],
            event.lat,
            event.lon,
            ev_depth,
        )
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            'Skipping prefetch for trace '
            f'{trace_id}: unable to compute arrival for '
            f'event {event.evid}: {_safe_error(err)}'
        )
        return None
    return float(p_arrival.time)


def _report_prefetch_prepare_progress(
    progress_ctx,
    prepared,
    total_attempts,
    batch_size,
    queued,
):
    """Report prefetch preparation progress before grouped downloads start."""
    if prepared % batch_size != 0 and prepared != total_attempts:
        return
    if progress_ctx['show_pbar']:
        progress_ctx['pbar'].set_postfix_str(
            f'preparing={prepared:n}/{total_attempts:n} '
            f'queued={queued:n}'
        )
        return
    logger.info(
        f'Prefetch preparation: {prepared:n}/{total_attempts:n} '
        f'windows inspected, queued={queued:n}'
    )


def _resolve_group_window_seconds():
    """Parse grouped-download span from CLI arguments."""
    group_window_spec = getattr(config.args, 'group_window', '1h')
    try:
        return max(float(_timespec_to_sec(group_window_spec)), 0.0)
    except ValueError as err:
        logger.error(err)
        rq_exit(2)


def _prepare_prefetch_request(
    event,
    trace_id,
    standard_offsets,
):
    """Prepare one event/trace request, honoring cache and failure state."""
    request = _build_prefetch_request(
        event,
        trace_id,
        standard_offsets,
    )
    if request is None:
        return 'unavailable', None
    cached_trace = _read_prefetch_cache(request)
    if cached_trace is not None:
        return 'fetched', None
    if _should_skip_prefetch_download(request):
        return 'unavailable', None
    return 'pending', request


def _build_prefetch_request(
    event,
    trace_id,
    standard_offsets,
):
    """Build one prefetch request with event and waveform window."""
    t0 = (
        event.orig_time + standard_offsets['tp_closest_s'] - config.cc_pre_P
    )
    t1 = (
        event.orig_time + standard_offsets['tp_farthest_s']
        + config.cc_trace_length
    )
    return {
        'event': event,
        'trace_id': trace_id,
        'start_time': t0,
        'end_time': t1,
    }


def _read_prefetch_cache(request):
    """Read one prefetch request from cache, returning None on miss."""
    event = request['event']
    trace_id = request['trace_id']
    t0 = request['start_time']
    t1 = request['end_time']
    try:
        return read_waveform_from_cache(event.evid, trace_id, t0, t1)
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            'Ignoring unreadable waveform cache row '
            f'for {event.evid}/{trace_id}: {_safe_error(err)}'
        )
        return None


def _should_skip_prefetch_download(request):
    """Check negative cache before attempting a grouped download."""
    event = request['event']
    trace_id = request['trace_id']
    t0 = request['start_time']
    t1 = request['end_time']
    try:
        skip_download, skip_reason = should_skip_waveform_download(
            event.evid,
            trace_id,
            t0,
            t1,
        )
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            'Unable to read waveform failure cache '
            f'for {event.evid}/{trace_id}: {_safe_error(err)}'
        )
        return False
    if skip_download:
        logger.info(
            f'Skipping download for {event.evid}/{trace_id}: {skip_reason}'
        )
    return skip_download


def _group_prefetch_requests(requests, max_span_s):
    """Group pending requests into larger windows for one trace ID."""
    if not requests:
        return []
    sorted_requests = sorted(
        requests,
        key=lambda request: float(request['start_time'].timestamp),
    )
    groups = []
    current_group = None
    for request in sorted_requests:
        if current_group is None:
            current_group = _new_prefetch_group(request)
            continue
        next_end = max(current_group['end_time'], request['end_time'])
        span_s = next_end - current_group['start_time']
        if span_s <= max_span_s:
            current_group['requests'].append(request)
            current_group['end_time'] = next_end
            continue
        groups.append(current_group)
        current_group = _new_prefetch_group(request)
    groups.append(current_group)
    return groups


def _new_prefetch_group(request):
    """Create one grouped-download container."""
    return {
        'start_time': request['start_time'],
        'end_time': request['end_time'],
        'requests': [request],
    }


def _download_prefetch_group(
    trace_id,
    group,
    get_waveform_from_client_func,
    no_waveform_error,
):
    """Download one grouped window and cut/cache all member requests."""
    start_time = group['start_time']
    end_time = group['end_time']
    requests = group['requests']
    try:
        group_trace = get_waveform_from_client_func(
            trace_id,
            start_time,
            end_time,
        )
    except no_waveform_error as err:
        _register_prefetch_group_failure(requests, err)
        return ['unavailable'] * len(requests)
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            'Unexpected prefetch error for grouped request '
            f'{trace_id} {start_time} -> {end_time}: {_safe_error(err)}'
        )
        _register_prefetch_group_failure(requests, err)
        return ['failed'] * len(requests)
    begin_cache_write_batch()
    statuses = [
        _cut_and_cache_prefetch_request(group_trace, request)
        for request in requests
    ]
    commit_cache_write_batch()
    return statuses


def _register_prefetch_group_failure(requests, error):
    """Register one grouped download failure for each member request."""
    error_message = _safe_error(error)
    for request in requests:
        event = request['event']
        trace_id = request['trace_id']
        t0 = request['start_time']
        t1 = request['end_time']
        try:
            register_waveform_failure(
                event.evid,
                trace_id,
                t0,
                t1,
                error_message,
            )
        except Exception as cache_err:  # pylint: disable=broad-except
            logger.warning(
                'Unable to update waveform failure cache: '
                f'{_safe_error(cache_err)}'
            )


def _cut_and_cache_prefetch_request(group_trace, request):
    """Cut one local event window from grouped trace and cache it."""
    event = request['event']
    trace_id = request['trace_id']
    t0 = request['start_time']
    t1 = request['end_time']
    trace_cut = group_trace.copy()
    trace_cut.trim(starttime=t0, endtime=t1)
    if trace_cut.stats.npts <= 0:
        _register_prefetch_group_failure(
            [request],
            ValueError('no samples in grouped download cut'),
        )
        return 'unavailable'
    try:
        write_waveform_to_cache(event.evid, trace_id, t0, t1, trace_cut)
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(
            f'Unable to write waveform cache row for '
            f'{event.evid}/{trace_id}: {_safe_error(err)}'
        )
        return 'failed'
    try:
        clear_waveform_failure(event.evid, trace_id, t0, t1)
    except Exception as cache_err:  # pylint: disable=broad-except
        logger.warning(
            'Unable to clear waveform failure cache: '
            f'{_safe_error(cache_err)}'
        )
    return 'fetched'


def _safe_error(err):
    """Build one-line exception message for logs and failure cache."""
    try:
        return str(err).replace('\n', ' ')
    except Exception as str_err:  # pylint: disable=broad-except
        err_type = type(err).__name__
        str_err_type = type(str_err).__name__
        return (
            f'Unable to format {err_type} message '
            f'({str_err_type} raised while converting to string).'
        )


def _record_prefetch_status(
    progress_ctx,
    total_attempts,
    batch_size,
    counters,
    status,
):
    """Accumulate counters and refresh progress reporting."""
    counters['attempted'] += 1
    if status == 'fetched':
        counters['fetched'] += 1
    elif status == 'unavailable':
        counters['unavailable'] += 1
    else:
        counters['unavailable'] += 1
        counters['unexpected_errors'] += 1
    _update_prefetch_progress(
        progress_ctx,
        counters['attempted'],
        total_attempts,
        batch_size,
        counters['fetched'],
        counters['unavailable'],
        counters['unexpected_errors'],
    )


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

    start_time, end_time = _resolve_filter_time_range()

    return {
        'event_ids': event_ids,
        'trace_ids': trace_ids,
        'start_time': start_time,
        'end_time': end_time,
        'limit': getattr(config.args, 'limit', None),
    }


def _resolve_filter_time_range():
    """Parse optional start/end time filter arguments."""
    start_time = _optional_utcdatetime('start_time')
    end_time = _optional_utcdatetime('end_time')
    return start_time, end_time


def _optional_utcdatetime(attr_name):
    """Return UTCDateTime from config arg or None when missing."""
    value = getattr(config.args, attr_name, None)
    return UTCDateTime(value) if value is not None else None


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
        _print_wfcache_details(summary)
    print(
        'negative cache: '
        f'total={summary["failure_rows"]:n}, '
        f'exhausted={summary["failure_exhausted_rows"]:n}, '
        f'retry-pending={summary["failure_retry_pending_rows"]:n}'
    )
    rq_exit(0)


def _print_wfcache_details(summary):
    """Print waveform-cache details when the cache file exists."""
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
