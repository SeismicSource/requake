# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import logging
import csv
from math import factorial
from itertools import combinations
from tqdm import tqdm
from obspy.geodetics import gps2dist_azimuth
from ..config import config, rq_exit
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..waveforms import (
    get_waveform_pair, cc_waveform_pair,
    NoWaveformError, NoMetadataError, MetadataMismatchError
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _pair_ok(pair):
    """Check if events in pair are close enough."""
    ev1, ev2 = pair
    distance, _, _ = gps2dist_azimuth(ev1.lat, ev1.lon, ev2.lat, ev2.lon)
    distance /= 1e3
    return distance <= config.catalog_search_range


def _fix_trace_id(stats):
    """
    Fix trace_id in a ObsPy stats object by replacing dots with underscores.
    This makes trace_id compliant with the FDSN standard.

    The fixes are done in place.

    :param stats: ObsPy stats object
    :type stats: ObsPy AttribDict
    """
    stats.network = stats.network.replace('.', '_')
    stats.station = stats.station.replace('.', '_')
    stats.location = stats.location.replace('.', '_')
    stats.channel = stats.channel.replace('.', '_')


def _process_pairs(fp_out, nevents, catalog):
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
    # Only show progress bar if running in a terminal
    pbar = (
        tqdm(total=npairs, unit='pairs', unit_scale=True)
        if sys.stderr.isatty()
        else None
    )
    for pair in combinations(catalog, 2):
        if pbar is not None:
            pbar.update()
        if not _pair_ok(pair):
            continue
        try:
            pair_st = get_waveform_pair(pair)
            tr1, tr2 = pair_st.traces
            lag, lag_sec, cc_max = cc_waveform_pair(tr1, tr2)
            stats1 = tr1.stats
            stats2 = tr2.stats
            _fix_trace_id(stats1)
            _fix_trace_id(stats2)
            writer.writerow([
                stats1.evid, stats2.evid, tr1.id,
                stats1.orig_time, stats1.ev_lon, stats1.ev_lat,
                stats1.ev_depth, stats1.mag_type, stats1.mag,
                stats2.orig_time, stats2.ev_lon, stats2.ev_lat,
                stats2.ev_depth, stats2.mag_type, stats2.mag,
                lag, lag_sec, cc_max
            ])
        except (NoMetadataError, MetadataMismatchError) as msg:
            logger.error(msg)
            rq_exit(1)
        except NoWaveformError as msg:
            # Do not print empty messages
            if str(msg):
                logger.warning(msg)
    return npairs


def scan_catalog():
    """
    Perform cross-correlation on catalog events.
    """
    try:
        catalog = read_stored_catalog()
    except (ValueError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    try:
        fix_non_locatable_events(catalog)
    except MetadataMismatchError as msg:
        logger.error(msg)
        rq_exit(1)
    nevents = len(catalog)
    if nevents < 2:
        logger.error(
            'Not enough events in catalog. '
            'You need at least 2 events to run the scan 😉')
        rq_exit(1)
    logger.info(f'{nevents} events read from catalog file')
    logger.info('Building event pairs...')
    logger.info('Computing waveform cross-correlation...')
    with open(config.scan_catalog_pairs_file, 'w', encoding='utf-8') as fp_out:
        npairs = _process_pairs(fp_out, nevents, catalog)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {config.scan_catalog_pairs_file}')
