# -*- coding: utf8 -*-
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import contextlib
import logging
import csv
from math import factorial
from itertools import combinations
from tqdm import tqdm
from obspy.geodetics import gps2dist_azimuth
from .catalog import RequakeCatalog, get_events, read_events
from .waveforms import get_waveform_pair, cc_waveform_pair
from .rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _get_catalog(config):
    """
    Download events based on user-defined criteria.

    Reads a cached catalog file, if available.
    """
    with contextlib.suppress(Exception):
        cat = read_events(config.scan_catalog_file)
        logger.info(f'{len(cat)} events read from catalog file')
        return cat
    logger.info('Downloading events...')
    cat_info = zip(
        config.catalog_fdsn_event_urls,
        config.catalog_start_times,
        config.catalog_end_times)
    catalog = []
    for url, start_time, end_time in cat_info:
        try:
            catalog += get_events(
                url,
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
        except Exception as m:
            logger.warning(
                f'Unable to download events from {url} for period '
                f'{start_time} - {end_time}. {m}'
            )
    if not catalog:
        logger.error('No event downloaded')
        rq_exit(1)
    # Sort catalog in increasing time order
    cat = RequakeCatalog(sorted(catalog, key=lambda ev: ev.orig_time))
    cat.write(config.scan_catalog_file)
    logger.info(f'{len(cat)} events downloaded')
    return cat


def _pair_ok(config, pair):
    """Check if events in pair are close enough."""
    ev1, ev2 = pair
    distance, _, _ = gps2dist_azimuth(ev1.lat, ev1.lon, ev2.lat, ev2.lon)
    distance /= 1e3
    return distance <= config.catalog_search_range


def _process_pairs(fp_out, nevents, catalog, config):
    """Process event pairs."""
    fieldnames = [
        'evid1', 'evid2', 'trace_id',
        'orig_time1', 'lon1', 'lat1', 'depth_km1', 'mag_type1', 'mag1',
        'orig_time2', 'lon2', 'lat2', 'depth_km2', 'mag_type2', 'mag2',
        'lag_samples', 'lag_sec', 'cc_max'
    ]
    writer = csv.writer(fp_out)
    writer.writerow(fieldnames)
    npairs = int(factorial(nevents)/(factorial(2)*factorial(nevents-2)))
    logger.info(f'Processing {npairs:n} event pairs')
    with tqdm(total=npairs, unit='pairs', unit_scale=True) as pbar:
        for pair in combinations(catalog, 2):
            pbar.update()
            if not _pair_ok(config, pair):
                continue
            try:
                pair_st = get_waveform_pair(config, pair)
                tr1, tr2 = pair_st.traces
                lag, lag_sec, cc_max = cc_waveform_pair(config, tr1, tr2)
                stats1 = tr1.stats
                stats2 = tr2.stats
                writer.writerow([
                    stats1.evid, stats2.evid, tr1.id,
                    stats1.orig_time, stats1.ev_lon, stats1.ev_lat,
                    stats1.ev_depth, stats1.mag_type, stats1.mag,
                    stats2.orig_time, stats2.ev_lon, stats2.ev_lat,
                    stats2.ev_depth, stats2.mag_type, stats2.mag,
                    lag, lag_sec, cc_max
                ])
            except Exception as m:
                # Do not print empty messages
                if str(m):
                    logger.warning(str(m))
    return npairs


def scan_catalog(config):
    """
    Perform cross-correlation on catalog events.

    :param config: Configuration object.
    :type config: config.Config
    """
    catalog = _get_catalog(config)
    nevents = len(catalog)
    logger.info('Building event pairs...')
    logger.info('Computing waveform cross-correlation...')
    with open(config.scan_catalog_pairs_file, 'w', encoding='utf-8') as fp_out:
        npairs = _process_pairs(fp_out, nevents, catalog, config)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {config.scan_catalog_pairs_file}')
