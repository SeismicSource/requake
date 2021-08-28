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
from obspy import Catalog
from obspy.geodetics import gps2dist_azimuth
from obspy.taup import TauPyModel
model = TauPyModel(model='ak135')
from .waveforms import get_waveform_pair, cc_waveform_pair
from .rq_setup import rq_exit
from .utils import update_progress


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
    # Final update to progressbar
    update_progress(1.)
    fp_out.close()
    logger.info(
        'Done! Output written to {}'.format(config.scan_catalog_outfile))
