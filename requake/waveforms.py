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
    for trace_id in config.catalog_trace_id:
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


def get_trace_id(config, ev):
    """Get trace id to use with ev."""
    trace_ids = config.catalog_trace_id
    if len(trace_ids) == 1:
        return trace_ids[0]
    ev_lat = ev.lat
    ev_lon = ev.lon
    orig_time = ev.orig_time
    distances = []
    for trace_id in trace_ids:
        coords = config.inventory.get_coordinates(trace_id, orig_time)
        trace_lat = coords['latitude']
        trace_lon = coords['longitude']
        distance, _, _ = gps2dist_azimuth(
            trace_lat, trace_lon, ev_lat, ev_lon)
        distances.append(distance)
    closest_trace = min(zip(trace_ids, distances), key=lambda x: x[1])[0]
    return closest_trace


def download_and_process_waveform(config, ev, trace_id):
    """Download and process waveform for a given event at a given trace_id."""
    evid = ev.evid
    ev_lat = ev.lat
    ev_lon = ev.lon
    ev_depth = ev.depth
    orig_time = ev.orig_time
    mag = ev.mag
    mag_type = ev.mag_type
    coords = config.inventory.get_coordinates(trace_id, orig_time)
    trace_lat = coords['latitude']
    trace_lon = coords['longitude']
    dist_deg = locations2degrees(trace_lat, trace_lon, ev_lat, ev_lon)
    arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['p', 'P'])
    # these two values are hardcoded, for the moment
    pre_P = config.cc_pre_P
    trace_length = config.cc_trace_length
    t0 = orig_time + arrivals[0].time - pre_P
    cl = config.fdsn_dataselect_client
    net, sta, loc, chan = trace_id.split('.')
    st = cl.get_waveforms(
        network=net, station=sta, location=loc, channel=chan,
        starttime=t0, endtime=t0+trace_length
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
    return tr


skipped_evids = list()
tr_cache = dict()
old_evid1 = None


def get_waveform_pair(config, pair):
    """Download traces for a given pair."""
    if config.inventory is None:
        get_metadata(config)
    trace_id = get_trace_id(config, pair[0])
    st = Stream()
    global skipped_evids
    global tr_cache
    global old_evid1
    # remove trace from cache when ev1 changes
    evid1 = pair[0].evid
    if old_evid1 is not None and evid1 != old_evid1:
        try:
            del tr_cache[old_evid1]
        except KeyError:
            pass
    old_evid1 = evid1
    for ev in pair:
        if ev.evid in skipped_evids:
            raise Exception
        # use cached trace, if possible
        try:
            st.append(tr_cache[ev.evid])
            continue
        except KeyError:
            pass
        try:
            tr = download_and_process_waveform(config, ev, trace_id)
            tr_cache[ev.evid] = tr
            st.append(tr)
        except Exception as m:
            skipped_evids.append(ev.evid)
            m = str(m).replace('\n', ' ')
            msg = (
                'Unable to download waveform data for '
                'event {} and trace_id {}. '
                'Skipping all pairs containig '
                'this event.\n'
                'Error message: {}'.format(ev.evid, trace_id, m)
            )
            raise Exception(msg)
    return st


def cc_waveform_pair(config, st):
    """Perform cross-correlation."""
    evids = [tr.stats.evid for tr in st]
    tr1 = st[0]
    tr2 = st[1]
    dt1 = tr1.stats.delta
    dt2 = tr2.stats.delta
    if dt1 != dt2:
        logger.warning(
            '{} {} - The two traces have a different sampling interval.'
            'Skipping pair.'.format(*evids))
        raise
    shift = int(config.cc_max_shift/dt1)
    cc = correlate(tr1, tr2, shift)
    lag, cc_max = xcorr_max(cc)
    lag_sec = lag*dt1
    return lag, lag_sec, cc_max
