# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for downloading and processing waveforms.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import contextlib
import logging
from itertools import combinations
import numpy as np
from obspy import Stream, UTCDateTime
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
from obspy.signal.cross_correlation import correlate, xcorr_max
from obspy.clients.fdsn.header import FDSNNoDataException
from scipy.stats import median_abs_deviation
from .station_metadata import get_traceid_coords
from .arrivals import get_arrivals
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
model = TauPyModel(model='ak135')


class NoWaveformError(Exception):
    """Exception raised for missing waveform data."""


def _get_trace_id(config, ev):
    """
    Get trace id to use with the given event.

    If there is only one trace_id in the config file, return it.
    If there are multiple trace_ids, return the one closest to the event.

    :param config: a Config object
    :type config: config.Config
    :param ev: an event
    :type ev: RequakeEvent
    :return: the trace_id to use
    :rtype: str
    """
    trace_ids = config.catalog_trace_id
    if len(trace_ids) == 1:
        return trace_ids[0]
    ev_lat = ev.lat
    ev_lon = ev.lon
    orig_time = ev.orig_time
    traceid_coords = get_traceid_coords(config, orig_time)
    distances = {}
    for trace_id, coords in traceid_coords.items():
        trace_lat = coords['latitude']
        trace_lon = coords['longitude']
        distance, _, _ = gps2dist_azimuth(
            trace_lat, trace_lon, ev_lat, ev_lon)
        distances[trace_id] = distance
    # return the trace_id for the closest trace
    return min(distances, key=distances.get)


def get_waveform(config, traceid, starttime, endtime):
    """Download waveform for a given traceid, start and end time."""
    cl = config.fdsn_dataselect_client
    net, sta, loc, chan = traceid.split('.')
    try:
        st = cl.get_waveforms(
            network=net, station=sta, location=loc, channel=chan,
            starttime=starttime, endtime=endtime
        )
    except FDSNNoDataException as m:
        msg = str(m).replace('\n', ' ')
        raise NoWaveformError(
            f'Unable to download waveform data for trace id: {traceid}.\n'
            f'Error message: {msg}'
        ) from m
    # webservices sometimes return longer traces: trim to be sure
    st.trim(starttime=starttime, endtime=endtime)
    st.merge(fill_value='interpolate')
    tr = st[0]
    tr.detrend(type='demean')
    return tr


def get_event_waveform(config, ev):
    """Download waveform for a given event at a given trace_id."""
    evid = ev.evid
    ev_lat = ev.lat
    ev_lon = ev.lon
    # avoid negative depths
    ev_depth = max(ev.depth, 0)
    orig_time = ev.orig_time
    mag = ev.mag
    mag_type = ev.mag_type
    traceid = ev.trace_id if config.args.traceid is None\
        else config.args.traceid
    traceid_coords = get_traceid_coords(config, orig_time)
    trace_lat = traceid_coords[traceid]['latitude']
    trace_lon = traceid_coords[traceid]['longitude']
    p_arrival, s_arrival, distance, dist_deg = get_arrivals(
        trace_lat, trace_lon, ev_lat, ev_lon, ev_depth)
    p_arrival_time = orig_time + p_arrival.time
    s_arrival_time = orig_time + s_arrival.time
    pre_p = config.cc_pre_P
    trace_length = config.cc_trace_length
    t0 = p_arrival_time - pre_p
    t1 = t0 + trace_length
    tr = get_waveform(config, traceid, t0, t1)
    tr.stats.evid = evid
    tr.stats.ev_lat = ev_lat
    tr.stats.ev_lon = ev_lon
    tr.stats.ev_depth = ev_depth
    tr.stats.orig_time = orig_time
    tr.stats.mag = mag
    tr.stats.mag_type = mag_type
    tr.stats.coords = traceid_coords[traceid]
    tr.stats.dist_deg = dist_deg
    tr.stats.distance = distance
    tr.stats.P_arrival_time = p_arrival_time
    tr.stats.S_arrival_time = s_arrival_time
    return tr


def process_waveforms(config, st):
    """Demean and filter a waveform trace or stream."""
    st = st.copy()
    st.detrend(type='demean')
    st.taper(max_percentage=0.05)
    st.filter(
        type='bandpass',
        freqmin=config.cc_freq_min,
        freqmax=config.cc_freq_max)
    return st


skipped_evids = []
tr_cache = {}
old_cache_key = None


def get_waveform_pair(config, pair):
    """
    Download traces for a given pair.

    :param config: requake config object
    :type config: config.Config
    :param pair: pair of events
    :type pair: tuple of RequakeEvent
    :return: stream containing the two traces
    :rtype: obspy.Stream
    """
    ev1, ev2 = pair
    ev1.trace_id = ev2.trace_id = _get_trace_id(config, ev1)
    st = Stream()
    global skipped_evids
    global tr_cache
    global old_cache_key
    cache_key = '_'.join((ev1.evid, ev1.trace_id))
    # remove trace from cache when evid and/or trace_id changes
    if old_cache_key is not None and cache_key != old_cache_key:
        with contextlib.suppress(KeyError):
            del tr_cache[cache_key]
    old_cache_key = cache_key
    for ev in pair:
        if ev.evid in skipped_evids:
            raise NoWaveformError
        # use cached trace, if possible
        cache_key = '_'.join((ev.evid, ev.trace_id))
        with contextlib.suppress(KeyError):
            st.append(tr_cache[cache_key])
            continue
        try:
            tr = get_event_waveform(config, ev)
            tr_cache[cache_key] = tr
            st.append(tr)
        except NoWaveformError as m:
            skipped_evids.append(ev.evid)
            msg = str(m).replace('\n', ' ')
            raise NoWaveformError(
                f'Unable to download waveform data for event {ev.evid} '
                f'and trace_id {ev.trace_id}. '
                'Skipping all pairs containig this event.\n'
                f'Error message: {msg}'
            ) from m
    return st


def cc_waveform_pair(config, tr1, tr2, mode='events'):
    """Perform cross-correlation."""
    dt1 = tr1.stats.delta
    dt2 = tr2.stats.delta
    if dt1 != dt2:
        if mode == 'events':
            evid1 = tr1.stats.evid
            evid2 = tr2.stats.evid
            logger.warning(
                f'{evid1} {evid2} - '
                'The two traces have a different sampling interval. '
                'Skipping pair.'
            )
        elif mode == 'scan':
            logger.error(
                'The two traces have a different sampling interval.')
            rq_exit(1)
    tr1 = process_waveforms(config, tr1)
    tr2 = process_waveforms(config, tr2)
    shift = int(config.cc_max_shift/dt1)
    cc = correlate(tr1, tr2, shift)
    abs_max = bool(config.cc_allow_negative)
    lag, cc_max = xcorr_max(cc, abs_max)
    lag_sec = lag*dt1
    if mode != 'scan':
        return lag, lag_sec, cc_max
    # compute median absolute deviation for the non-zero portion of cc
    cc_mad = median_abs_deviation(cc[np.abs(cc) > 1e-5])
    return lag, lag_sec, cc_max, cc_mad


def align_pair(config, tr1, tr2):
    """Align tr2 respect to tr1 using cross-correlation."""
    lag, lag_sec, cc_max = cc_waveform_pair(config, tr1, tr2)
    # apply lag to trace #2
    # if lag is positive, trace #2 is delayed
    if lag > 0:
        data2 = np.zeros_like(tr2.data)
        data2[lag:] = tr2.data[:-lag]
    # if lag is negative, trace #2 is advanced
    elif lag < 0:
        data2 = np.zeros_like(tr2.data)
        data2[:lag] = tr2.data[-lag:]
    else:
        data2 = tr2.data
    tr2.data = data2
    tr2.stats.P_arrival_time += lag_sec
    tr2.stats.S_arrival_time += lag_sec
    return lag, lag_sec, cc_max


def align_traces(config, st):
    """Align traces in stream using cross-correlation."""
    for tr in st:
        tr.stats.cc_mean = 0
        tr.stats.cc_npairs = 0
    for tr1, tr2 in combinations(st, 2):
        _, _, cc_max = align_pair(config, tr1, tr2)
        tr1.stats.cc_mean += cc_max
        tr1.stats.cc_npairs += 1
        tr2.stats.cc_mean += cc_max
        tr2.stats.cc_npairs += 1
    for tr in st:
        tr.stats.cc_mean /= tr.stats.cc_npairs


def build_template(config, st, family):
    """
    Build template by averaging traces.

    Assumes that the stream is realigned.
    """
    tr_template = st[0].copy()
    tr_template.data *= 0.
    P_arrival = 0.
    S_arrival = 0.
    for tr in st:
        data = tr.data
        if config.normalize_traces_before_averaging:
            data /= abs(tr.max())
        tr_template.data += data
        P_arrival += tr.stats.P_arrival_time - tr.stats.starttime
        S_arrival += tr.stats.S_arrival_time - tr.stats.starttime
    tr_template.data /= len(st)
    P_arrival /= len(st)
    S_arrival /= len(st)
    tr_template.stats.evid = f'average{family.number:02d}'
    tr_template.stats.ev_lat = family.lat
    tr_template.stats.ev_lon = family.lon
    tr_template.stats.ev_depth = family.depth
    tr_template.stats.orig_time = UTCDateTime('1900/01/01T00:00:00')
    tr_template.stats.mag = 0
    tr_template.stats.mag_type = ''
    trace_lat = tr_template.stats.coords['latitude']
    trace_lon = tr_template.stats.coords['longitude']
    dist_deg = locations2degrees(
        trace_lat, trace_lon, family.lat, family.lon)
    distance, _, _ = gps2dist_azimuth(
        trace_lat, trace_lon, family.lat, family.lon)
    distance /= 1e3
    tr_template.stats.dist_deg = dist_deg
    tr_template.stats.distance = distance
    tr_template.stats.starttime = UTCDateTime('1900/01/01T00:00:00')
    tr_template.stats.P_arrival_time = tr_template.stats.starttime + P_arrival
    tr_template.stats.S_arrival_time = tr_template.stats.starttime + S_arrival
    tr_template.stats.cc_mean = 0
    tr_template.stats.cc_npairs = 0
    st.append(tr_template)
