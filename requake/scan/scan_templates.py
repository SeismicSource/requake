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
import numpy as np
from obspy import read
from obspy.signal.cross_correlation import correlate_template
from scipy.signal import find_peaks
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
# Value ObsPy uses for undefined SAC header fields.
SAC_NULL = -12345.0


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


def _bandpass_filter(tr):
    """
    Demean and band-pass a trace for cross-correlation.

    No taper is applied: the continuous data are processed in long chunks,
    where an edge taper would suppress detections near the chunk boundaries.
    The trace is decimated by ``decim_factor`` (with an anti-alias filter)
    when that option is greater than 1.

    :param tr: input trace
    :type tr: :class:`obspy.Trace`
    :return: a filtered copy of the trace
    :rtype: :class:`obspy.Trace`
    """
    freq_min = (
        config.args.freq_band[0] if getattr(config.args, 'freq_band', None)
        else config.cc_freq_min
    )
    freq_max = (
        config.args.freq_band[1] if getattr(config.args, 'freq_band', None)
        else config.cc_freq_max
    )
    tr = tr.copy()
    tr.detrend(type='demean')
    # Zero-phase, 4-corner band-pass: avoids the phase distortion of a
    # one-pass filter, which is the standard choice for template matching.
    tr.filter(
        type='bandpass', freqmin=freq_min, freqmax=freq_max,
        corners=4, zerophase=True)
    if config.decim_factor > 1:
        # ObsPy applies an anti-alias filter before downsampling.
        tr.decimate(config.decim_factor)
    return tr


def _template_s_minus_p(template):
    """
    Return the theoretical S minus P time for a template, in seconds.

    The value is read from the template picks when available (SAC header
    ``t0`` for S and ``a`` for P, both written by ``build_templates``), and
    falls back to a travel-time computation from the station and event
    geometry otherwise. The result is cached on the template so it is computed
    at most once instead of once per detection.

    :param template: template trace
    :type template: :class:`obspy.Trace`
    :return: S minus P time in seconds
    :rtype: float
    """
    cached = template.stats.get('s_minus_p')
    if cached is not None:
        return cached
    sac = template.stats.sac
    s_pick = sac.get('t0')
    p_pick = sac.get('a')
    if s_pick not in (None, SAC_NULL) and p_pick not in (None, SAC_NULL):
        s_minus_p = s_pick - p_pick
    else:
        p_arrival, s_arrival, _distance, _dist_deg = get_arrivals(
            sac.stla, sac.stlo, sac.evla, sac.evlo, sac.evdp)
        s_minus_p = s_arrival.time - p_arrival.time
    template.stats.s_minus_p = s_minus_p
    return s_minus_p


def _ccs_detection(tr, template, p_arrival_absolute_time):
    """
    Compute the S-wave-centered cross-correlation (NCCs) of a detection.

    Both the template and the candidate trace are trimmed to a window around
    the theoretical S arrival before correlating. Returns ``None`` when the
    S arrival cannot be computed (for example when the SAC geometry is
    missing).

    :param tr: continuous trace containing the detection
    :type tr: :class:`obspy.Trace`
    :param template: template trace
    :type template: :class:`obspy.Trace`
    :param p_arrival_absolute_time: absolute time of the P arrival in tr
    :type p_arrival_absolute_time: :class:`obspy.UTCDateTime`
    :return: the S-wave cross-correlation, or None
    :rtype: float or None
    """
    try:
        s_minus_p = _template_s_minus_p(template)
    except Exception:  # pylint: disable=broad-except
        # get_arrivals can fail in many ways; skip the S-wave correlation
        return None
    pre_s = config.cc_pre_S
    length = config.cc_S_trace_length
    template_s_time = template.stats.sac.a + s_minus_p
    template_s = template.copy().trim(
        template.stats.starttime + template_s_time - pre_s,
        template.stats.starttime + template_s_time - pre_s + length)
    s_absolute_time = p_arrival_absolute_time + s_minus_p
    tr_s = tr.copy().trim(
        s_absolute_time - pre_s, s_absolute_time - pre_s + length)
    if len(template_s) == 0 or len(tr_s) == 0:
        return None
    _, _, ccs = cc_waveform_pair(tr_s, template_s)
    return ccs


def _accept_detection(cc_max, ccs):
    """
    Apply the cross-correlation acceptance criterion.

    A detection is kept when ``cc_max > template_cc_min``. When the S-wave
    combined criterion is active, it is also kept when both
    ``cc_max > template_cc_min_combined`` and
    ``ccs > template_ccs_min_combined``. All thresholds come from the config.

    :param cc_max: full cross-correlation (NCC) of the detection
    :type cc_max: float
    :param ccs: S-wave cross-correlation (NCCs), or None
    :type ccs: float or None
    :return: True when the detection is accepted
    :rtype: bool
    """
    if cc_max > config.template_cc_min:
        return True
    if (
        ccs is not None
        and cc_max > config.template_cc_min_combined
        and ccs > config.template_ccs_min_combined
    ):
        return True
    return False


def _parabolic_offset(values, index):
    """
    Sub-sample offset of a discrete peak by parabolic interpolation.

    A parabola is fitted to the peak sample and its two neighbours; the offset
    of its vertex is returned, in samples, in the range [-0.5, 0.5].

    :param values: array in which the peak was found
    :type values: numpy.ndarray
    :param index: index of the discrete peak
    :type index: int
    :return: sub-sample offset, in samples
    :rtype: float
    """
    if index <= 0 or index >= len(values) - 1:
        return 0.0
    y_0 = float(values[index - 1])
    y_1 = float(values[index])
    y_2 = float(values[index + 1])
    denominator = y_0 - 2.0 * y_1 + y_2
    if denominator == 0.0:
        return 0.0
    return 0.5 * (y_0 - y_2) / denominator


def _scan_family_template(template, t0, t1):
    """
    Scan one template over one time chunk and return all detections.

    A normalized sliding cross-correlation (NCC) of the template against the
    continuous data is computed with
    :func:`obspy.signal.cross_correlation.correlate_template`. Every NCC peak
    above the detection threshold is kept, so more than one event can be
    detected in a single chunk. Peaks are restricted to the nominal
    (non-overlap) part of the chunk so that an event straddling the boundary
    with the next chunk is counted only once.

    :param template: template trace
    :type template: :class:`obspy.Trace`
    :param t0: start of the chunk
    :type t0: :class:`obspy.UTCDateTime`
    :param t1: end of the chunk (nominal end plus overlap)
    :type t1: :class:`obspy.UTCDateTime`
    :return: list of detection tuples
        (family_number, trace_id, event, cc_max, ccs)
    :rtype: list
    """
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
    data = _bandpass_filter(tr)
    template_filtered = _bandpass_filter(template)
    if data.stats.sampling_rate != template_filtered.stats.sampling_rate:
        logger.warning(
            'Different sampling rates for %s and its template; '
            'skipping chunk %s - %s', trace_id, t0, t1)
        return []
    fs = data.stats.sampling_rate
    template_array = template_filtered.data.astype(np.float64)
    template_length = len(template_array)
    if len(data.data) <= template_length:
        return []
    ncc = correlate_template(
        data.data.astype(np.float64), template_array,
        mode='valid', normalize='full', demean=True)
    ncc = np.clip(ncc, -1.0, 1.0)
    # Keep only peaks whose template start falls in the nominal part of the
    # chunk (before the overlap), so an event is detected in a single chunk.
    # The overlap must cover the template length so that a template starting
    # near the end of the nominal window is still fully correlated.
    nominal_stop = min(t0 + config.time_chunk, t1)
    n_nominal = int((nominal_stop - tr.stats.starttime) * fs)
    if n_nominal <= 0:
        return []
    ncc_valid = ncc[:n_nominal]
    # find_peaks height is the lowest cross-correlation that can be accepted:
    # template_cc_min, or template_cc_min_combined when the S-wave combined
    # criterion is active. Peaks closer than t_min are merged.
    threshold = (
        config.template_cc_min_combined if config.template_use_swave_cc
        else config.template_cc_min
    )
    distance = max(1, int(round(config.t_min * fs)))
    peak_metric = np.abs(ncc_valid) if config.cc_allow_negative else ncc_valid
    peaks, _props = find_peaks(
        peak_metric, height=threshold, distance=distance)
    detections = []
    for index in peaks:
        cc_max = round(float(ncc_valid[index]), 2)
        # Refine the peak to sub-sample precision (parabolic interpolation)
        # for a more accurate origin time; the template P pick is at sac.a.
        offset = _parabolic_offset(peak_metric, index)
        p_arrival_absolute_time = (
            tr.stats.starttime + (index + offset) / fs
            + template.stats.sac.a)
        ccs = None
        if config.template_use_swave_cc:
            ccs = _ccs_detection(tr, template, p_arrival_absolute_time)
            if not _accept_detection(cc_max, ccs):
                continue
        ev = _build_event(tr, template, p_arrival_absolute_time)
        detections.append((
            template.stats.family_number,
            trace_id,
            ev,
            cc_max,
            round(ccs, 2) if ccs is not None else None,
        ))
    return detections


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
                detections.extend(
                    _scan_family_template(template, t0, t1))
            except NoWaveformError as msg:
                logger.warning(msg)
                continue
        if detections:
            write_template_detections(detections, append=True)
        trace_cache.clear()
        time += time_chunk
