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
