#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Functions for downloading and processing waveforms.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import numpy as np
from obspy import Inventory, Stream
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
model = TauPyModel(model='ak135')
from obspy.signal.cross_correlation import correlate, xcorr_max
from .rq_setup import rq_exit


def get_metadata(config):
    """Download metadata for the trace_ids specified in config file."""
    logger.info('Downloading station metadata...')
    inv = Inventory()
    cl = config.fdsn_station_client
    start_time = min(config.catalog_start_times)
    end_time = max(config.catalog_end_times)
    if config.args.traceid is not None:
        trace_ids = [config.args.traceid, ]
    else:
        trace_ids = config.catalog_trace_id
    for trace_id in trace_ids:
        net, sta, loc, chan = trace_id.split('.')
        try:
            inv += cl.get_stations(
                network=net, station=sta, location=loc, channel=chan,
                starttime=start_time, endtime=end_time, level='channel'
            )
        except Exception as m:
            logger.error('Unable to download station metadata. ' + str(m))
            rq_exit(1)
    channels = inv.get_contents()['channels']
    unique_channels = set(channels)
    channel_count = [channels.count(id) for id in unique_channels]
    for channel, count in zip(unique_channels, channel_count):
        if count > 1:
            logger.warning(
                'Channel {} is present {} times in inventory'.format(
                    channel, count
                )
            )
    config.inventory = inv
    logger.info('Metadata downloaded for channels: {}'.format(
        set(config.inventory.get_contents()['channels'])))


def _get_trace_id(config, ev):
    """Get trace id to use with ev."""
    trace_ids = config.catalog_trace_id
    if len(trace_ids) == 1:
        return trace_ids[0]
    ev_lat = ev.lat
    ev_lon = ev.lon
    orig_time = ev.orig_time
    distances = []
    for trace_id in trace_ids:
        try:
            coords = config.inventory.get_coordinates(trace_id, orig_time)
        except Exception:
            logger.error(
                'Unable to find coordinates for trace {} at time {}'.format(
                    trace_id, orig_time
                ))
            rq_exit(1)
        trace_lat = coords['latitude']
        trace_lon = coords['longitude']
        distance, _, _ = gps2dist_azimuth(
            trace_lat, trace_lon, ev_lat, ev_lon)
        distances.append(distance)
    closest_trace = min(zip(trace_ids, distances), key=lambda x: x[1])[0]
    return closest_trace


def download_and_process_waveform(config, ev):
    """Download and process waveform for a given event at a given trace_id."""
    evid = ev.evid
    ev_lat = ev.lat
    ev_lon = ev.lon
    ev_depth = ev.depth
    orig_time = ev.orig_time
    mag = ev.mag
    mag_type = ev.mag_type
    if config.args.traceid is not None:
        trace_id = config.args.traceid
    else:
        trace_id = ev.trace_id
    coords = config.inventory.get_coordinates(trace_id, orig_time)
    trace_lat = coords['latitude']
    trace_lon = coords['longitude']
    dist_deg = locations2degrees(trace_lat, trace_lon, ev_lat, ev_lon)
    P_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['p', 'P'])
    P_arrival_time = orig_time + P_arrivals[0].time
    S_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['s', 'S'])
    S_arrival_time = orig_time + S_arrivals[0].time
    pre_P = config.cc_pre_P
    trace_length = config.cc_trace_length
    t0 = P_arrival_time - pre_P
    t1 = t0 + trace_length
    cl = config.fdsn_dataselect_client
    net, sta, loc, chan = trace_id.split('.')
    st = cl.get_waveforms(
        network=net, station=sta, location=loc, channel=chan,
        starttime=t0, endtime=t1
    )
    st.taper(max_percentage=0.05)
    st.filter(
        type='bandpass',
        freqmin=config.cc_freq_min,
        freqmax=config.cc_freq_max)
    st.merge(fill_value='interpolate')
    tr = st[0]
    tr.stats.evid = evid
    tr.stats.ev_lat = ev_lat
    tr.stats.ev_lon = ev_lon
    tr.stats.ev_depth = ev_depth
    tr.stats.orig_time = orig_time
    tr.stats.mag = mag
    tr.stats.mag_type = mag_type
    tr.stats.P_arrival_time = P_arrival_time
    tr.stats.S_arrival_time = S_arrival_time
    return tr


skipped_evids = list()
tr_cache = dict()
old_cache_key = None


def get_waveform_pair(config, pair):
    """Download traces for a given pair."""
    if config.inventory is None:
        get_metadata(config)
    ev1, ev2 = pair
    ev1.trace_id = ev2.trace_id = _get_trace_id(config, ev1)
    st = Stream()
    global skipped_evids
    global tr_cache
    global old_cache_key
    cache_key = '_'.join((ev1.evid, ev1.trace_id))
    # remove trace from cache when evid and/or trace_id changes
    if old_cache_key is not None and cache_key != old_cache_key:
        try:
            del tr_cache[cache_key]
        except KeyError:
            pass
    old_cache_key = cache_key
    for ev in pair:
        if ev.evid in skipped_evids:
            raise Exception
        # use cached trace, if possible
        cache_key = '_'.join((ev.evid, ev.trace_id))
        try:
            st.append(tr_cache[cache_key])
            continue
        except KeyError:
            pass
        try:
            tr = download_and_process_waveform(config, ev)
            tr_cache[cache_key] = tr
            st.append(tr)
        except Exception as m:
            skipped_evids.append(ev.evid)
            m = str(m).replace('\n', ' ')
            msg = (
                'Unable to download waveform data for '
                'event {} and trace_id {}. '
                'Skipping all pairs containig '
                'this event.\n'
                'Error message: {}'.format(ev.evid, ev.trace_id, m)
            )
            raise Exception(msg)
    return st


def cc_waveform_pair(config, tr1, tr2):
    """Perform cross-correlation."""
    evid1 = tr1.stats.evid
    evid2 = tr2.stats.evid
    dt1 = tr1.stats.delta
    dt2 = tr2.stats.delta
    if dt1 != dt2:
        logger.warning(
            '{} {} - The two traces have a different sampling interval.'
            'Skipping pair.'.format(evid1, evid2))
        raise
    shift = int(config.cc_max_shift/dt1)
    cc = correlate(tr1, tr2, shift)
    lag, cc_max = xcorr_max(cc)
    lag_sec = lag*dt1
    return lag, lag_sec, cc_max


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
    return lag, lag_sec, cc_max


def align_traces(config, st):
    """Align traces in stream using cross-correlation."""
    tr1 = st[0]
    for tr2 in st[1:]:
        align_pair(config, tr1, tr2)
