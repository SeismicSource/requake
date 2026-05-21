# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import logging
from itertools import combinations
from tqdm import tqdm
from obspy.geodetics import gps2dist_azimuth
from ..config import config, rq_exit
from ..database.db import get_db_path
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..families.pairs import RequakeEventPair
from ..database.pairs import write_pairs as write_pairs_to_db
from ..waveforms import (
    WaveformPair, cc_waveform_pair,
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
    Fix trace_id in an ObsPy stats object by replacing dots.

    This makes trace_id compliant with the FDSN standard.

    The fixes are done in place.

    :param stats: ObsPy stats object
    :type stats: ObsPy AttribDict
    """
    stats.network = stats.network.replace('.', '_')
    stats.station = stats.station.replace('.', '_')
    stats.location = stats.location.replace('.', '_')
    stats.channel = stats.channel.replace('.', '_')


def _process_pairs(catalog):
    """Process event pairs."""
    write_pairs_to_db([], config, append=False)
    logger.info('Precomputing valid event pairs...')
    valid_pairs = [
        pair for pair in combinations(catalog, 2) if _pair_ok(pair)
    ]
    npairs = len(valid_pairs)
    logger.info(f'Processing {npairs:n} event pairs')
    # Only show progress bar if running in a terminal
    pbar = (
        tqdm(total=npairs, unit='pairs', unit_scale=True)
        if sys.stderr.isatty()
        else None
    )
    waveform_pair = WaveformPair()
    batch_of_pairs = []
    for pair in valid_pairs:
        if pbar is not None:
            pbar.update()
        try:
            pair_st = waveform_pair.get_waveform_pair(pair)
            tr1, tr2 = pair_st.traces
            lag, lag_sec, cc_max = cc_waveform_pair(tr1, tr2)
            stats1 = tr1.stats
            stats2 = tr2.stats
            _fix_trace_id(stats1)
            _fix_trace_id(stats2)
            batch_of_pairs.append(
                RequakeEventPair(
                    pair[0],
                    pair[1],
                    tr1.id,
                    lag,
                    lag_sec,
                    cc_max,
                )
            )
            if len(batch_of_pairs) >= 100:
                write_pairs_to_db(batch_of_pairs, config, append=True)
                batch_of_pairs = []
        except (NoMetadataError, MetadataMismatchError) as msg:
            logger.error(msg)
            rq_exit(1)
        except NoWaveformError as msg:
            # Do not print empty messages
            if str(msg):
                logger.warning(msg)
    if batch_of_pairs:
        write_pairs_to_db(batch_of_pairs, config, append=True)
    return npairs


def scan_catalog():
    """Perform cross-correlation on catalog events."""
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
    logger.info(
        f'{nevents} events read from db file {get_db_path(config)}'
    )
    logger.info('Building event pairs...')
    logger.info('Computing waveform cross-correlation...')
    npairs = _process_pairs(catalog)
    logger.info(f'Processed {npairs:n} event pairs')
    logger.info(f'Done! Output written to {get_db_path(config)}')
