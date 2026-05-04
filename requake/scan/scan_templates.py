# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Scan a continuous waveform stream using one or more templates.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
import sys
from obspy import read
from ..config import config, rq_exit
from ..families import (
    read_families, read_selected_families,
    FamilyNotFoundError
)
from ..waveforms import (
    get_waveform_from_client, cc_waveform_pair, get_arrivals,
    NoWaveformError
)
from ..catalog import RequakeEvent, generate_evid
from .._version import get_versions
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
trace_cache = {}


def _build_event(tr, template, p_arrival_absolute_time):
    """Build metadata for matched event, using metadata from template."""
    try:
        trace_lat = template.stats.sac.stla
        trace_lon = template.stats.sac.stlo
        ev_lat = template.stats.sac.evla
        ev_lon = template.stats.sac.evlo
        ev_depth = template.stats.sac.evdp
        p_arrival, _s_arrival, _distance, _dist_deg = get_arrivals(
            trace_lat, trace_lon, ev_lat, ev_lon, ev_depth)
        orig_time = p_arrival_absolute_time - p_arrival.time
    except Exception:  # pylint: disable=broad-except
        # Here we catch a broad exception because get_arrivals can fail
        # in many ways, and we don't want to stop the scan
        orig_time = p_arrival_absolute_time
        ev_lon = ev_lat = ev_depth = None
    ev = RequakeEvent()
    ev.orig_time = orig_time
    ev.lon = ev_lon
    ev.lat = ev_lat
    ev.depth = ev_depth
    ev.trace_id = tr.id
    ev.evid = generate_evid(orig_time)
    ev.author = f"requake{get_versions()['version']}"
    return ev


def _cc_detection(tr, template, lag_sec):
    """Compute cross-correlation between detected event and template."""
    # shorter trace is zero-padded on both sides
    #   --aaaa--
    #   bbbbbbbb
    d_len = 0.5 * (len(tr) - len(template)) * tr.stats.delta
    lag_sec += d_len
    p_arrival = lag_sec + template.stats.sac.a
    p_arrival_absolute_time = tr.stats.starttime + p_arrival
    t0 = p_arrival_absolute_time - config.cc_pre_P
    t1 = t0 + config.cc_trace_length
    tr2 = tr.copy().trim(t0, t1)
    _, _, cc_max = cc_waveform_pair(tr2, template)
    return cc_max, p_arrival_absolute_time


def _scan_family_template(template, catalog_file, t0, t1):
    trace_id = template.id
    key = f'{t0}_{trace_id}'
    try:
        tr = trace_cache[key]
    except KeyError:
        try:
            tr = get_waveform_from_client(trace_id, t0, t1)
            trace_cache[key] = tr
        except NoWaveformError as err:
            raise NoWaveformError(
                f'No data for {trace_id} : {t0} - {t1}'
            ) from err
    sys.stdout.write(str(tr) + '\r')
    # We use the time_chunk length as max shift
    config.cc_max_shift = config.time_chunk
    _lag, lag_sec, cc_max, cc_mad = cc_waveform_pair(tr, template, mode='scan')
    cc_peak = cc_max/cc_mad
    if cc_peak > config.min_cc_mad_ratio:
        cc_max, p_arrival_absolute_time = _cc_detection(tr, template, lag_sec)
        ev = _build_event(tr, template, p_arrival_absolute_time)
        catalog_file.write(f'{ev.fdsn_text()}|{cc_max:.2f}\n')
        catalog_file.flush()


def _read_template_from_file():
    """
    Read a template from a file provided by the user.
    """
    families = read_families()
    try:
        family_number = sorted(f.number for f in families)[-1] + 1
    except IndexError:
        family_number = 0
    templates = []
    try:
        tr = read(config.args.template_file)[0]
        tr.stats.family_number = family_number
        templates.append(tr)
    except (FileNotFoundError, TypeError) as msg:
        logger.warning(msg)
    return templates


def _read_templates():
    """
    Read templates from files in the template directory or from a file
    provided by the user.
    """
    if config.args.template_file is not None:
        return _read_template_from_file()
    families = read_selected_families()
    templates = []
    for family in families:
        trace_id = family[0].trace_id
        template_file = f'template{family.number:02d}.{trace_id}.sac'
        template_file = os.path.join(config.template_dir, template_file)
        try:
            tr = read(template_file)[0]
            tr.stats.family_number = family.number
            templates.append(tr)
        except (FileNotFoundError, TypeError) as msg:
            logger.warning(msg)
    return templates


def _template_catalog_files(templates):
    """
    Create a catalog file for each template.

    Note: the returned dictionary contains file pointers, not file names.
    These file pointers must be closed by the caller.

    :param templates: list of templates
    :type templates: list of obspy.Trace objects
    :return: dictionary of file pointers
    :rtype: dict
    """
    catalog_files = {}
    for template in templates:
        template_catalog_dir = os.path.join(
            config.args.outdir, 'template_catalogs'
        )
        if not os.path.exists(template_catalog_dir):
            os.makedirs(template_catalog_dir)
        template_signature =\
            f'{template.stats.family_number:02d}.{template.id}'
        template_catalog_file_name = os.path.join(
            template_catalog_dir, f'catalog{template_signature}.txt'
        )
        catalog_files[template_signature] = open(
            template_catalog_file_name, 'w', encoding='utf-8')
    return catalog_files


# ---------------------------------------------------------------------------
# Parallel processing helpers
# Added by Marius Yvard (feature/parallel-processing)
# ---------------------------------------------------------------------------
# Note: we use ThreadPoolExecutor rather than ProcessPoolExecutor here because
# `config` is a module-level singleton that is not pickleable. Threading keeps
# all threads in the same process and shares the singleton safely.
# The main benefit is overlapping FDSN download I/O across time chunks.
# For CPU-bound NCC parallelism, process-based parallelism via
# parallel_utils.parallel_map() is more appropriate and can be applied to
# scan_catalog.py where pairs are fully serialisable.
# ---------------------------------------------------------------------------

def _split_time_range(starttime, endtime, chunk_hours=24, margin_seconds=120):
    """
    Split a time range into overlapping chunks for parallel processing.

    A margin equal to the template duration is added at each chunk boundary
    to avoid cutting a detection that straddles two consecutive chunks.
    The ``_merge_detections()`` function removes resulting duplicates.

    :param starttime: start of the full time range
    :type starttime: :class:`obspy.UTCDateTime`
    :param endtime: end of the full time range
    :type endtime: :class:`obspy.UTCDateTime`
    :param chunk_hours: duration of each chunk in hours (default: 24)
    :type chunk_hours: int or float
    :param margin_seconds: overlap margin in seconds, should be >= template
        duration (default: 120)
    :type margin_seconds: int or float
    :returns: list of (chunk_start, chunk_end) tuples
    :rtype: list of tuple
    """
    from obspy import UTCDateTime
    chunks = []
    step = chunk_hours * 3600.0
    margin = float(margin_seconds)
    current = float(starttime)
    end = float(endtime)
    while current < end:
        chunk_end = min(current + step + margin, end)
        chunks.append((UTCDateTime(current), UTCDateTime(chunk_end)))
        current += step - margin
    return chunks


def _merge_detections(chunk_results, margin_seconds=120):
    """
    Merge detection strings from overlapping chunks, removing duplicates.

    Each detection is represented as an FDSN-format string with a trailing
    ``|cc_max`` field. When two detections from adjacent chunks fall within
    ``margin_seconds`` of each other, only the one with the higher CC value
    is kept.

    :param chunk_results: list of lists of (template_signature, event_text)
        strings, one list per chunk
    :type chunk_results: list of list of tuple
    :param margin_seconds: time window within which two detections are
        considered duplicates (default: 120 s)
    :type margin_seconds: int or float
    :returns: dict mapping template_signature to list of deduplicated
        event lines, time-sorted
    :rtype: dict
    """
    from obspy import UTCDateTime
    # Flatten and group by template signature
    by_template = {}
    for chunk in chunk_results:
        for signature, line in chunk:
            by_template.setdefault(signature, []).append(line)
    merged = {}
    for signature, lines in by_template.items():
        # Parse time and CC from FDSN text lines
        parsed = []
        for line in lines:
            try:
                # FDSN line format ends with |cc_max
                parts = line.strip().split('|')
                cc = float(parts[-1])
                # Time is the first field of the FDSN text (pipe-separated)
                t = UTCDateTime(parts[0].split('|')[0].strip())
                parsed.append((t, cc, line))
            except Exception:  # pylint: disable=broad-except
                parsed.append((UTCDateTime(0), 0.0, line))
        parsed.sort(key=lambda x: x[0])
        deduped = [parsed[0]]
        for item in parsed[1:]:
            last = deduped[-1]
            if abs(float(item[0]) - float(last[0])) < margin_seconds:
                if item[1] > last[1]:
                    deduped[-1] = item
            else:
                deduped.append(item)
        merged[signature] = [item[2] for item in deduped]
    return merged


def _scan_chunk_threaded(args):
    """
    Scan all templates over one time chunk (thread worker).

    Returns a list of (template_signature, event_line) tuples so that the
    main thread can write results to catalog files without race conditions.
    Uses a thread-local trace cache to avoid cross-thread cache pollution.

    :param args: tuple of (templates, t0, t1)
    :type args: tuple
    :returns: list of (signature, fdsn_line) tuples
    :rtype: list of tuple
    """
    import threading
    templates, t0, t1 = args
    local_cache = getattr(threading.current_thread(), '_trace_cache', {})
    threading.current_thread()._trace_cache = local_cache
    results = []
    config.cc_max_shift = config.time_chunk
    for template in templates:
        trace_id = template.id
        key = f'{t0}_{trace_id}'
        try:
            tr = local_cache.get(key)
            if tr is None:
                tr = get_waveform_from_client(trace_id, t0, t1)
                local_cache[key] = tr
        except NoWaveformError as msg:
            logger.warning(msg)
            continue
        _lag, lag_sec, cc_max, cc_mad = cc_waveform_pair(
            tr, template, mode='scan')
        cc_peak = cc_max / cc_mad
        if cc_peak > config.min_cc_mad_ratio:
            cc_max_det, p_arr = _cc_detection(tr, template, lag_sec)
            ev = _build_event(tr, template, p_arr)
            signature = f'{template.stats.family_number:02d}.{template.id}'
            results.append((signature, f'{ev.fdsn_text()}|{cc_max_det:.2f}\n'))
    local_cache.clear()
    return results


def scan_templates():
    """
    Scan a continuous waveform stream using one or more templates.

    When ``config.n_jobs`` > 1, time chunks are dispatched to a thread pool
    so that FDSN download I/O overlaps across chunks. Results are collected
    in the main thread and written to catalog files after deduplication of
    detections in chunk overlap zones.

    When ``config.n_jobs`` == 1 (default), the original sequential behaviour
    is preserved unchanged.
    """
    # pylint: disable=import-outside-toplevel
    try:
        templates = _read_templates()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    catalog_files = _template_catalog_files(templates)

    # ── Read parallel settings (fall back gracefully if not in config) ──
    try:
        n_jobs = int(getattr(config, 'n_jobs', 1) or 1)
    except (ValueError, TypeError):
        n_jobs = 1
    try:
        chunk_hours = float(getattr(config, 'chunk_hours', 24) or 24)
    except (ValueError, TypeError):
        chunk_hours = 24
    try:
        margin = float(getattr(config, 'template_margin_seconds', 120) or 120)
    except (ValueError, TypeError):
        margin = 120

    if n_jobs == 1:
        # ── Sequential mode (original behaviour, unchanged) ──────────────
        time = config.template_start_time
        time_chunk = config.time_chunk
        overlap = config.time_chunk_overlap
        while time <= config.template_end_time:
            for template in templates:
                template_signature = \
                    f'{template.stats.family_number:02d}.{template.id}'
                catalog_file = catalog_files[template_signature]
                try:
                    t0 = time
                    t1 = time + time_chunk + overlap
                    _scan_family_template(template, catalog_file, t0, t1)
                except NoWaveformError as msg:
                    logger.warning(msg)
                    continue
            trace_cache.clear()
            time += time_chunk
    else:
        # ── Parallel mode (ThreadPoolExecutor, n_jobs > 1) ────────────────
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import multiprocessing as mp
        if n_jobs < 0:
            n_jobs = max(1, mp.cpu_count() + 1 + n_jobs)
        chunks = _split_time_range(
            config.template_start_time,
            config.template_end_time,
            chunk_hours=chunk_hours,
            margin_seconds=margin,
        )
        tasks = [(templates, t0, t1) for t0, t1 in chunks]
        logger.info(
            'Parallel scan: %d chunks, %d workers', len(tasks), n_jobs
        )
        chunk_results = []
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            future_to_idx = {
                executor.submit(_scan_chunk_threaded, task): idx
                for idx, task in enumerate(tasks)
            }
            ordered = [None] * len(tasks)
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    ordered[idx] = future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning('Chunk %d failed: %s', idx, exc)
                    ordered[idx] = []
            chunk_results = ordered
        merged = _merge_detections(chunk_results, margin_seconds=margin)
        for signature, lines in merged.items():
            fp = catalog_files.get(signature)
            if fp is not None:
                fp.writelines(lines)
                fp.flush()

    for fp in catalog_files.values():
        fp.close()
