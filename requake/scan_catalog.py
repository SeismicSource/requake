#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import csv
from itertools import combinations
from obspy import Catalog, Inventory, Stream
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
model = TauPyModel(model='ak135')
from obspy.signal.cross_correlation import correlate, xcorr_max
from .rq_setup import rq_exit
from .utils import update_progress


def _get_metadata(config):
    """Download metadata for the trace_ids specified in config file."""
    inv = Inventory()
    cl = config.client_fdsn_station
    start_time = min(config.catalog_start_times)
    end_time = max(config.catalog_end_times)
    for trace_id in config.catalog_trace_id:
        net, sta, loc, chan = trace_id.split('.')
        inv += cl.get_stations(
            network=net, station=sta, location=loc, channel=chan,
            starttime=start_time, endtime=end_time, level='channel'
        )
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


def _get_catalog(config):
    """Download events based on user-defined criteria."""
    cat_info = zip(
        config.clients_fdsn_event,
        config.catalog_start_times,
        config.catalog_end_times)
    catalog = Catalog()
    for cl, start_time, end_time in cat_info:
        catalog += cl.get_events(
            starttime=start_time, endtime=end_time,
            minlatitude=config.catalog_lat_min,
            maxlatitude=config.catalog_lat_max,
            minlongitude=config.catalog_lon_min,
            maxlongitude=config.catalog_lon_max,
            mindepth=config.catalog_depth_min,
            maxdepth=config.catalog_depth_max,
            minmagnitude=config.catalog_mag_min,
            maxmagnitude=config.catalog_mag_max
        )
    # Remove events without preferred_origin
    cat = [ev for ev in catalog if ev.preferred_origin() is not None]
    # Sort catalog in increasing time order and return it
    return Catalog(sorted(cat, key=lambda ev: ev.preferred_origin().time))


def _get_pairs(config, catalog):
    """Get event pairs to check for similarity."""
    pairs = list()
    for ev1, ev2 in combinations(catalog, 2):
        pref_origin1 = ev1.preferred_origin()
        pref_origin2 = ev2.preferred_origin()
        if pref_origin1 is None or pref_origin2 is None:
            continue
        lat1 = pref_origin1.latitude
        lon1 = pref_origin1.longitude
        lat2 = pref_origin2.latitude
        lon2 = pref_origin2.longitude
        distance, _, _ = gps2dist_azimuth(lat1, lon1, lat2, lon2)
        distance /= 1e3
        if distance <= config.catalog_search_range:
            pairs.append((ev1, ev2))
    return pairs


def _get_trace_id(config, pair):
    """Get trace id to use with ev."""
    trace_ids = config.catalog_trace_id
    if len(trace_ids) == 1:
        return trace_ids[0]
    ev1, ev2 = pair
    pref_origin1 = ev1.preferred_origin()
    pref_origin2 = ev2.preferred_origin()
    lat1 = pref_origin1.latitude
    lon1 = pref_origin1.longitude
    orig_time1 = pref_origin1.time
    lat2 = pref_origin2.latitude
    lon2 = pref_origin2.longitude
    latmean = 0.5*(lat1+lat2)
    lonmean = 0.5*(lon1+lon2)
    distances = []
    for trace_id in trace_ids:
        coords = config.inventory.get_coordinates(trace_id, orig_time1)
        trace_lat = coords['latitude']
        trace_lon = coords['longitude']
        distance, _, _ = gps2dist_azimuth(
            trace_lat, trace_lon, latmean, lonmean)
        distances.append(distance)
    closest_trace = min(zip(trace_ids, distances), key=lambda x: x[1])[0]
    return closest_trace


def _download_and_process_waveform(config, ev, trace_id):
    """Download and process waveform for a given event at a given trace_id."""
    evid = str(ev.resource_id).split('/')[-1]
    pref_origin = ev.preferred_origin()
    ev_lat = pref_origin.latitude
    ev_lon = pref_origin.longitude
    ev_depth = pref_origin.depth / 1e3
    orig_time = pref_origin.time
    mag = ev.preferred_magnitude().mag
    mag_type = ev.preferred_magnitude().magnitude_type
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
    cl = config.client_fdsn_dataselect
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


def get_waveform_pair(config, pair):
    """Download traces for a given pair."""
    if config.inventory is None:
        logger.info('Downloading station metadata...')
        try:
            _get_metadata(config)
        except Exception as m:
            logger.error('Unable to download station metadata. ' + str(m))
            rq_exit(1)
        logger.info('Metadata downloaded for channels: {}'.format(
            set(config.inventory.get_contents()['channels'])))
    evids = [str(ev.resource_id).split('/')[-1] for ev in pair]
    trace_id = _get_trace_id(config, pair)
    st = Stream()
    global skipped_evids
    for ev, evid in zip(pair, evids):
        if evid in skipped_evids:
            raise Exception
        try:
            st += _download_and_process_waveform(config, ev, trace_id)
        except Exception as m:
            skipped_evids.append(evid)
            m = str(m).replace('\n', ' ')
            msg = (
                'Unable to download waveform data for '
                'event {} and trace_id {}. '
                'Skipping all pairs containig '
                'this event.\n'
                'Error message: {}'.format(evid, trace_id, m)
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


def scan_catalog(config):
    """Perform cross-correlation on catalog events."""
    logger.info('Downloading events...')
    try:
        catalog = _get_catalog(config)
    except Exception as m:
        logger.error('Unable to download events. ' + str(m))
        rq_exit(1)
    logger.info('{} events downloaded'.format(len(catalog)))
    logger.info('Building event pairs...')
    pairs = _get_pairs(config, catalog)
    npairs = len(pairs)
    logger.info('{} event pairs built'.format(npairs))
    logger.info('Computing waveform cross-correlation...')
    fp_out = open(config.scan_catalog_outfile, 'w')
    fieldnames = [
        'evid1', 'evid2', 'trace_id',
        'orig_time1', 'lon1', 'lat1', 'depth_km1', 'mag_type1', 'mag1',
        'orig_time2', 'lon2', 'lat2', 'depth_km2', 'mag_type2', 'mag2',
        'lag_samples', 'lag_sec', 'cc_max'
    ]
    writer = csv.writer(fp_out)
    writer.writerows([fieldnames])
    for n, pair in enumerate(pairs):
        try:
            st = get_waveform_pair(config, pair)
            lag, lag_sec, cc_max = cc_waveform_pair(config, st)
            stats1, stats2 = [tr.stats for tr in st]
            writer.writerows([[
                stats1.evid, stats2.evid, st[0].id,
                stats1.orig_time, stats1.ev_lon, stats1.ev_lat,
                stats1.ev_depth, stats1.mag_type, stats1.mag,
                stats2.orig_time, stats2.ev_lon, stats2.ev_lat,
                stats2.ev_depth, stats2.mag_type, stats2.mag,
                lag, lag_sec, cc_max
            ]])
        except Exception as m:
            # Do not print empty messages
            if str(m):
                # Need a newline after the progressbar to print
                # the warning message
                update_progress(n/npairs, '\n')
                logger.warning(str(m))
            continue
        update_progress(n/npairs)
    fp_out.close()
    logger.info(
        'Done! Output written to {}'.format(config.scan_catalog_outfile))
