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
import io
import logging
import os
import sys
from obspy import read
from ..config import config, rq_exit
from ..config.utils import confirm_action
from ..database.templates import (
    clear_template_detections,
    has_template_detections,
    write_template_detections,
)
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
    ev.author = f'requake{get_versions()["version"]}'
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


def _scan_family_template(template, t0, t1):
    """Scan one template against one time chunk and return a detection."""
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
    cc_peak = cc_max / cc_mad
    if cc_peak > config.min_cc_mad_ratio:
        cc_max, p_arrival_absolute_time = _cc_detection(tr, template, lag_sec)
        ev = _build_event(tr, template, p_arrival_absolute_time)
        return (
            template.stats.family_number,
            trace_id,
            ev,
            round(cc_max, 2),
        )
    return None


def _read_template_from_file():
    """Read a template from a file provided by the user."""
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
    Read templates from the template directory or a user-provided file.

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


# ---------------------------------------------------------------------------
# Optional parallel scan over time chunks.
#
# Time chunks are independent units of work: each chunk scans all templates
# over one time window. Workers run in separate processes so the CPU-bound
# cross-correlation is spread across cores and the FDSN download I/O of
# different chunks overlaps. The config singleton is rebuilt inside each
# worker from a pickle-safe snapshot, because the network clients it holds
# are not pickleable. Detections produced twice in the overlap between
# adjacent chunks are deduplicated by the database UNIQUE constraint on
# (family_number, trace_id, evid), exactly as in the serial scan.
# ---------------------------------------------------------------------------
_worker_templates = []


def _template_time_chunks():
    """
    Build the list of (t0, t1) windows scanned by the template scan.

    The windows match the serial scan exactly: a new window starts every
    ``time_chunk`` seconds and spans ``time_chunk + time_chunk_overlap``.

    :return: list of (starttime, endtime) tuples
    :rtype: list
    """
    chunks = []
    time = config.template_start_time
    time_chunk = config.time_chunk
    overlap = config.time_chunk_overlap
    while time <= config.template_end_time:
        chunks.append((time, time + time_chunk + overlap))
        time += time_chunk
    return chunks


def _resolve_template_scan_nprocs(nchunks):
    """
    Resolve the effective number of worker processes for the template scan.

    The value comes from the ``--nprocs`` command-line option, falling back
    to the ``template_scan_nprocs`` config parameter. A value of 0 selects the
    number of available CPUs (minus one when more than one is available) and a
    value of 1 disables parallelism. The result is capped by ``nchunks``.

    :param nchunks: number of time chunks to process
    :type nchunks: int
    :return: effective number of worker processes (at least 1)
    :rtype: int
    """
    import multiprocessing
    cli_nprocs = getattr(config.args, 'nprocs', None)
    config_nprocs = getattr(config, 'template_scan_nprocs', 0)
    requested = cli_nprocs if cli_nprocs is not None else config_nprocs
    if requested is None or requested < 0:
        requested = 0
    if requested == 0:
        base_nprocs = multiprocessing.cpu_count()
        if base_nprocs > 1:
            base_nprocs -= 1
    else:
        base_nprocs = requested
    return min(max(1, base_nprocs), max(1, nchunks))


def _scan_templates_worker_initializer(cfg_dict, templates):
    """
    Initialize a worker process for the parallel template scan.

    The pickle-safe config snapshot is restored into the module-level config
    singleton, the network clients are recreated inside the worker process and
    the templates are stored for reuse across the chunks handled by the worker.

    The client-connection and logging helpers are shared with the catalog scan
    to keep a single definition of how a worker connects to data services.

    :param cfg_dict: pickle-safe config snapshot from
        :func:`requake.config.to_picklable_config_dict`
    :type cfg_dict: dict
    :param templates: list of template traces
    :type templates: list
    """
    import signal
    from ..config import from_picklable_config_dict
    from .scan_catalog_workers import (
        _connect_worker_clients, _silence_worker_console_logging
    )
    global _worker_templates
    _silence_worker_console_logging()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    restored_cfg = from_picklable_config_dict(cfg_dict)
    config.clear()
    config.update(restored_cfg)
    _connect_worker_clients()
    _worker_templates = templates


def _scan_chunk_worker(time_range):
    """
    Scan all templates over one time chunk (worker process entry point).

    The same :func:`_scan_family_template` used by the serial scan is called
    here, so the detection logic is identical. Progress written to stdout by
    that function is suppressed in the worker to keep the parent progress line
    readable.

    :param time_range: (starttime, endtime) of the chunk
    :type time_range: tuple
    :return: list of detection tuples (family_number, trace_id, event, cc_max)
    :rtype: list
    """
    import contextlib
    t0, t1 = time_range
    detections = []
    with contextlib.redirect_stdout(io.StringIO()):
        for template in _worker_templates:
            try:
                detection = _scan_family_template(template, t0, t1)
            except NoWaveformError:
                continue
            if detection is not None:
                detections.append(detection)
    trace_cache.clear()
    return detections


def _scan_templates_parallel(templates, nprocs):
    """
    Scan templates over continuous data using a pool of worker processes.

    Each time chunk is dispatched to a worker that scans all templates over
    that window. Detections are collected in the parent process and written to
    the database in a single transaction. Duplicate detections from the
    overlap between adjacent chunks are removed by the database UNIQUE
    constraint.

    :param templates: list of template traces
    :type templates: list
    :param nprocs: number of worker processes
    :type nprocs: int
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from ..config import to_picklable_config_dict
    chunks = _template_time_chunks()
    cfg_dict = to_picklable_config_dict(config)
    logger.info(
        'Parallel template scan: %d time chunks, %d worker processes',
        len(chunks), nprocs
    )
    with ProcessPoolExecutor(
        max_workers=nprocs,
        initializer=_scan_templates_worker_initializer,
        initargs=(cfg_dict, templates),
    ) as executor:
        futures = {
            executor.submit(_scan_chunk_worker, chunk): idx
            for idx, chunk in enumerate(chunks)
        }
        ordered = [None] * len(chunks)
        for done, future in enumerate(as_completed(futures), start=1):
            ordered[futures[future]] = future.result()
            sys.stdout.write(f'Scanned {done}/{len(chunks)} time chunks\r')
    sys.stdout.write('\n')
    # Flatten in chunk order so that, for detections seen twice in the overlap
    # between two chunks, the later chunk wins the database REPLACE, matching
    # the serial scan order.
    detections = [
        detection for chunk_detections in ordered
        for detection in chunk_detections
    ]
    if detections:
        write_template_detections(detections, append=True)


def scan_templates():
    """Scan a continuous waveform stream using one or more templates."""
    try:
        templates = _read_templates()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if has_template_detections():
        logger.warning(
            'Existing template detections from previous scans will be '
            'removed before starting a new scan'
        )
        if not confirm_action('Continue and clear previous detections?'):
            logger.info('Scan aborted by user; previous detections kept')
            rq_exit(0)
    clear_template_detections()
    nchunks = len(_template_time_chunks())
    nprocs = _resolve_template_scan_nprocs(nchunks)
    if nprocs > 1:
        _scan_templates_parallel(templates, nprocs)
        return
    time = config.template_start_time
    time_chunk = config.time_chunk
    overlap = config.time_chunk_overlap
    while time <= config.template_end_time:
        detections = []
        for template in templates:
            try:
                t0 = time
                t1 = time + time_chunk + overlap
                detection = _scan_family_template(template, t0, t1)
                if detection is not None:
                    detections.append(detection)
            except NoWaveformError as msg:
                logger.warning(msg)
                continue
        if detections:
            write_template_detections(detections, append=True)
        trace_cache.clear()
        time += time_chunk
