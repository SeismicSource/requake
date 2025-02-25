# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for downloading and processing waveforms.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import contextlib
import logging
from itertools import combinations
from pathlib import Path
import numpy as np
from obspy import read
from obspy import Stream, UTCDateTime
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
from obspy.signal.cross_correlation import correlate, xcorr_max
from obspy.clients.fdsn.header import FDSNNoDataException
from scipy.stats import median_abs_deviation
from ..config import config, rq_exit
from .station_metadata import get_traceid_coords, MetadataMismatchError
from .arrivals import get_arrivals
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
model = TauPyModel(model='ak135')


class NoWaveformError(Exception):
    """Exception raised for missing waveform data."""


def _get_trace_id(ev):
    """
    Get trace id to use with the given event.

    If there is only one trace_id in the config file, return it.
    If there are multiple trace_ids, return the one closest to the event.

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
    traceid_coords = get_traceid_coords(orig_time)
    distances = {}
    for trace_id, coords in traceid_coords.items():
        trace_lat = coords['latitude']
        trace_lon = coords['longitude']
        distance, _, _ = gps2dist_azimuth(
            trace_lat, trace_lon, ev_lat, ev_lon)
        distances[trace_id] = distance
    # return the trace_id for the closest trace
    return min(distances, key=distances.get)


def get_waveform_from_client(traceid, starttime, endtime):
    """
    Get a waveform from a FDSN or SDS client.

    :param traceid: trace id
    :type traceid: str
    :param starttime: start time
    :type starttime: obspy.UTCDateTime
    :param endtime: end time
    :type endtime: obspy.UTCDateTime

    :return: waveform trace
    :rtype: obspy.Trace
    """
    client = config.dataselect_client
    if client is None:
        raise NoWaveformError(
            'No dataselect_client defined in the config file')
    net, sta, loc, chan = traceid.split('.')
    try:
        st = client.get_waveforms(
            network=net, station=sta, location=loc, channel=chan,
            starttime=starttime, endtime=endtime
        )
    except FDSNNoDataException as err:
        msg = str(err).replace('\n', ' ')
        raise NoWaveformError(
            f'No waveform data for trace id: {traceid} '
            f'between {starttime} and {endtime}\n'
            f'Error message: {msg}'
        ) from err
    # webservices sometimes return longer traces: trim to be sure
    st.trim(starttime=starttime, endtime=endtime)
    st.merge(fill_value='interpolate')
    if not st:
        raise NoWaveformError(
            f'No waveform data for trace id: {traceid} '
            f'between {starttime} and {endtime}'
        )
    tr = st[0]
    tr.detrend(type='demean')
    return tr


def _get_arrivals_and_distance(
        trace_lat, trace_lon, ev_lat, ev_lon, ev_depth, orig_time):
    """
    Get arrivals and distance for a given trace and event

    :param trace_lat: latitude of the trace
    :type trace_lat: float
    :param trace_lon: longitude of the trace
    :type trace_lon: float
    :param ev_lat: latitude of the event
    :type ev_lat: float
    :param ev_lon: longitude of the event
    :type ev_lon: float
    :param ev_depth: depth of the event
    :type ev_depth: float
    :param orig_time: origin time of the event
    :type orig_time: obspy.UTCDateTime

    :return: P and S arrivals and distance
    :rtype: tuple of obspy.taup.Arrival, obspy.taup.Arrival, float, float
    """
    try:
        p_arrival, s_arrival, distance, dist_deg = get_arrivals(
            trace_lat, trace_lon, ev_lat, ev_lon, ev_depth)
    except Exception as err:  # pylint: disable=broad-except
        # Here we catch a broad exception because get_arrivals can raise
        # different types of exceptions
        raise ValueError(err) from err
    p_arrival_time = orig_time + p_arrival.time  # pylint: disable=no-member
    s_arrival_time = orig_time + s_arrival.time  # pylint: disable=no-member
    return p_arrival_time, s_arrival_time, distance, dist_deg


def _get_event_waveform_from_client(evid, traceid, p_arrival_time):
    """
    Get a waveform for a given event and traceid through
    an FDSN or SDS client.

    :param evid: event id
    :type evid: str
    :param traceid: trace id
    :type traceid: str
    :param p_arrival_time: P arrival time
    :type p_arrival_time: obspy.UTCDateTime

    :return: waveform trace
    :rtype: obspy.Trace

    :raises NoWaveformError: if no waveform data is available
    """
    pre_p = config.cc_pre_P
    trace_length = config.cc_trace_length
    t0 = p_arrival_time - pre_p
    t1 = t0 + trace_length
    try:
        return get_waveform_from_client(traceid, t0, t1)
    except NoWaveformError as err:
        msg = str(err).replace('\n', ' ')
        raise NoWaveformError(
            f'Unable to download waveform data for event {evid} '
            f'and trace_id {traceid}. '
            'Skipping event.\n'
            f'Error message: {msg}'
        ) from err


def _get_event_waveform_from_event_data_path(evid, traceid):
    """
    Get a waveform for a given event and traceid by selecting a pre-cut
    trace from the event_data_path defined in the config.

    :param evid: event id
    :type evid: str
    :param traceid: trace id
    :type traceid: str

    :return: waveform trace
    :rtype: obspy.Trace

    :raises NoWaveformError: if no waveform data is available
    """
    event_data_path = config.event_data_path
    if event_data_path is None:
        raise NoWaveformError('No event_data_path defined in the config file')
    event_data_path = Path(event_data_path)
    if not event_data_path.exists():
        raise NoWaveformError(
            f'Event data path "{event_data_path}" does not exist'
        )
    event_dir = next(
        (subdir for subdir in event_data_path.iterdir()
            if evid in subdir.name),
        None)
    if event_dir is None:
        raise NoWaveformError(
            f'No waveform data for event {evid} in "{event_data_path}"'
        )
    net, sta, loc, chan = traceid.split('.')
    # replace '@@' with an empty network code
    net = net if net != '@@' else ''
    # if station name contains an underscore or a dot, replace it with a jolly
    # character (question mark)
    sta = sta.replace('_', '?').replace('.', '?')
    # an empty channel means all channels, replace with a wildcard
    if chan == '':
        chan = '*'
    st = read(event_dir / '*').select(
        network=net, station=sta, location=loc, channel=chan)
    if not st:
        raise NoWaveformError(
            f'No waveform data for trace id: {traceid} in "{event_dir}"'
        )
    return st[0]


def get_event_waveform(ev):
    """
    Download waveform for a given event and for trace_id defined in the config.

    :param ev: an event
    :type ev: RequakeEvent

    :return: waveform trace
    :rtype: obspy.Trace

    :raises NoWaveformError: if no waveform data is available
    """
    evid = ev.evid
    ev_lat = ev.lat
    ev_lon = ev.lon
    # avoid negative depths
    ev_depth = max(ev.depth, 0)
    orig_time = ev.orig_time
    mag = ev.mag
    mag_type = ev.mag_type
    traceid = (
        ev.trace_id if config.args.traceid is None
        else config.args.traceid
    )
    try:
        traceid_coords = get_traceid_coords(orig_time)
    except MetadataMismatchError as err:
        msg = str(err).replace('\n', ' ')
        raise NoWaveformError(
            f'Unable to download waveform data for event {evid} '
            f'and trace_id {traceid}. '
            'Skipping event.\n'
            f'Error message: {msg}'
        ) from err
    try:
        coords = traceid_coords[traceid]
    except KeyError as err:
        msg = str(err).replace('\n', ' ')
        raise NoWaveformError(
            f'No metadata for trace_id {traceid} '
            'in the metadata file. Skipping event.\n'
            f'Error message: {msg}'
        ) from err
    trace_lat = coords['latitude']
    trace_lon = coords['longitude']
    try:
        p_arrival_time, s_arrival_time, distance, dist_deg =\
            _get_arrivals_and_distance(
                trace_lat, trace_lon, ev_lat, ev_lon, ev_depth, orig_time)
    except ValueError as err:
        msg = str(err).replace('\n', ' ')
        raise NoWaveformError(
            f'Unable to compute arrival times for event {evid} '
            f'and trace_id {traceid}. '
            'Skipping event.\n'
            f'Error message: {msg}'
        ) from err
    try:
        tr = _get_event_waveform_from_event_data_path(evid, traceid)
    except NoWaveformError as err:
        logger.warning(err)
        tr = _get_event_waveform_from_client(evid, traceid, p_arrival_time)
    tr_stats = {
        'evid': evid,
        'ev_lat': ev_lat,
        'ev_lon': ev_lon,
        'ev_depth': ev_depth,
        'orig_time': orig_time,
        'mag': mag,
        'mag_type': mag_type,
        'coords': coords,
        'dist_deg': dist_deg,
        'distance': distance,
        'P_arrival_time': p_arrival_time,
        'S_arrival_time': s_arrival_time
    }
    tr.stats.update(tr_stats)
    return tr


def process_waveforms(tr_or_st):
    """
    Demean and filter a waveform trace or stream.

    :param tr_or_st: waveform stream or trace
    :type tr_or_st: obspy.Stream or obspy.Trace

    :return: processed waveform stream or trace
    :rtype: obspy.Stream or obspy.Trace
    """
    tr_or_st = tr_or_st.copy()
    tr_or_st.detrend(type='demean')
    tr_or_st.taper(max_percentage=0.05, type='cosine')
    freq_min = (
        config.args.freq_band[0] if getattr(config.args, 'freq_band', None)
        else config.cc_freq_min
    )
    freq_max = (
        config.args.freq_band[1] if getattr(config.args, 'freq_band', None)
        else config.cc_freq_max
    )
    tr_or_st.filter(
        type='bandpass',
        freqmin=freq_min,
        freqmax=freq_max)
    if isinstance(tr_or_st, Stream):
        for tr in tr_or_st:
            tr.stats.freq_min = freq_min
            tr.stats.freq_max = freq_max
    else:
        tr_or_st.stats.freq_min = freq_min
        tr_or_st.stats.freq_max = freq_max
    return tr_or_st


skipped_evids = []
tr_cache = {}
old_cache_key = None


def get_waveform_pair(pair):
    """
    Download traces for a given pair.

    :param pair: pair of events
    :type pair: tuple of RequakeEvent
    :return: stream containing the two traces
    :rtype: obspy.Stream

    :raises NoWaveformError: if no waveform data is available
    """
    ev1, ev2 = pair
    ev1.trace_id = ev2.trace_id = _get_trace_id(ev1)
    st = Stream()
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
            tr = get_event_waveform(ev)
            tr_cache[cache_key] = tr
            st.append(tr)
        except NoWaveformError as err:
            skipped_evids.append(ev.evid)
            msg = str(err).replace('\n', ' ')
            raise NoWaveformError(
                f'Unable to get waveform data for event {ev.evid} '
                f'and trace_id {ev.trace_id}. '
                'Skipping all pairs containig this event.\n'
                f'Error message: {msg}'
            ) from err
    return st


def cc_waveform_pair(tr1, tr2, mode='events'):
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
    tr1 = process_waveforms(tr1)
    tr2 = process_waveforms(tr2)
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


def align_pair(tr1, tr2):
    """Align tr2 respect to tr1 using cross-correlation."""
    lag, lag_sec, cc_max = cc_waveform_pair(tr1, tr2)
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


def align_traces(st):
    """
    Align traces in stream using cross-correlation.

    :param st: stream of traces
    :type st: obspy.Stream
    """
    # first, align all traces to the first one
    tr0 = st[0]
    for tr in st[1:]:
        _, _, cc_max = align_pair(tr0, tr)
    # then, align all traces to the stacked trace; repeat twice
    for _ in range(2):
        tr_stack = _stack_traces(st)
        for tr in st:
            _, _, cc_max = align_pair(tr_stack, tr)
            tr.stats.cc_mean = cc_max


def _stack_traces(st):
    """
    Stack traces in stream.

    :param st: stream of traces
    :type st: obspy.Stream

    :return: stacked trace
    :rtype: obspy.Trace
    """
    tr_stack = st[0].copy()
    tr_stack.data *= 0.
    p_arrival = 0.
    s_arrival = 0.
    for tr in st:
        tr.detrend('demean')
        data = tr.data
        if config.normalize_traces_before_averaging:
            data /= abs(tr.max())
        tr_stack.data += data
        p_arrival += tr.stats.P_arrival_time - tr.stats.starttime
        s_arrival += tr.stats.S_arrival_time - tr.stats.starttime
    tr_stack.data /= len(st)
    p_arrival /= len(st)
    s_arrival /= len(st)
    tr_stack.stats.starttime = UTCDateTime('1900/01/01T00:00:00')
    tr_stack.stats.P_arrival_time = tr_stack.stats.starttime + p_arrival
    tr_stack.stats.S_arrival_time = tr_stack.stats.starttime + s_arrival
    tr_stack.stats.cc_mean = 0
    tr_stack.stats.cc_npairs = 0
    return tr_stack


def build_template(st, family):
    """
    Build template by averaging traces.

    Assumes that the stream is realigned.
    """
    tr_template = _stack_traces(st)
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
    st.append(tr_template)
