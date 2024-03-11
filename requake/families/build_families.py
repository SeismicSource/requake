# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
from itertools import combinations
from scipy.cluster.hierarchy import average, fcluster
from obspy import UTCDateTime
from ..formulas.conversion import float_or_none
from ..catalog.catalog import RequakeEvent
from .families import Family
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _check_options(config):
    """
    Check the consistency of the configuration options.

    :param config: configuration object
    :type config: config.Config

    :raises ValueError: if the configuration options are inconsistent
    """
    sort_by = config.sort_families_by
    lon0, lat0 = config.distance_from_lon, config.distance_from_lat
    if sort_by == 'distance_from' and (lon0 is None or lat0 is None):
        raise ValueError(
            '"sort_families_by" set to "distance_from", '
            'but "distance_from_lon" and/or "distance_from_lat" '
            'are not specified')


def _read_events_from_pairs_file(config):
    """
    Read events from pairs file.

    :param config: configuration object
    :type config: config.Config
    :return: dictionary of events
    :rtype: dict

    :raises FileNotFoundError: if the pairs file is not found
    """
    events = {}
    with open(config.scan_catalog_pairs_file, 'r', encoding='utf8') as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            cc_max = float(row['cc_max'])
            evid1 = row['evid1']
            try:
                ev1 = events[evid1]
            except KeyError:
                ev1 = RequakeEvent(
                    evid=evid1,
                    orig_time=UTCDateTime(row['orig_time1']),
                    lon=float_or_none(row['lon1']),
                    lat=float_or_none(row['lat1']),
                    depth=float_or_none(row['depth_km1']),
                    mag_type=row['mag_type1'],
                    mag=float_or_none(row['mag1']),
                    trace_id=row['trace_id']
                )
                events[evid1] = ev1
            evid2 = row['evid2']
            try:
                ev2 = events[evid2]
            except KeyError:
                ev2 = RequakeEvent(
                    evid=evid2,
                    orig_time=UTCDateTime(row['orig_time2']),
                    lon=float_or_none(row['lon2']),
                    lat=float_or_none(row['lat2']),
                    depth=float_or_none(row['depth_km2']),
                    mag_type=row['mag_type2'],
                    mag=float_or_none(row['mag2']),
                    trace_id=row['trace_id']
                )
                events[evid2] = ev2
            # Store the correlation between the two events in both events
            ev1.correlations[ev2.evid] = ev2.correlations[ev1.evid] = cc_max
    return events


def _build_families_from_shared_events(events, cc_min):
    """
    Build families by clustering all event pairs sharing an event.

    Valid event pairs are those with a correlation above cc_min.

    :param events: dictionary of events
    :type events: dict
    :return: list of families
    :rtype: list
    """
    # Build families from events with correlation above cc_min
    families = []
    for ev in events.values():
        new_family = Family()
        new_family.append(ev)
        for evid, cc in ev.correlations.items():
            if cc < cc_min:
                continue
            new_family.append(events[evid])
        if len(new_family) == 1:
            continue
        # Check if the new family shares events with an existing family
        # and merge them, if necessary
        found_existing_family = False
        for existing_family in families:
            if set(existing_family).intersection(new_family):
                found_existing_family = True
                existing_family.extend(new_family)
                break
        if not found_existing_family:
            families.append(new_family)
    return families


def _build_families_from_upgma(events, cc_min):
    """
    Build families of similar events using the UPGMA algorithm.

    Reference: https://en.wikipedia.org/wiki/UPGMA

    :param events: dictionary of events
    :type events: dict
    :return: list of families
    :rtype: list
    """
    # We use sorted tuples of evids as keys to avoid duplicates with inverted
    # order of evids, e.g. (evid1, evid2) and (evid2, evid1)
    correlations = {
        tuple(sorted((evid1, evid2))): cc
        for evid1, ev in events.items()
        for evid2, cc in ev.correlations.items()
    }
    min_correlation = min(correlations.values())
    # Build distance dictionary. Distance is 1 - correlation.
    # We use min_correlation for pairs for which no correlation is available
    evids = sorted(set(events.keys()))
    distances = {
        k: 1-correlations.get(k, min_correlation)
        for k in combinations(evids, 2)
    }
    # Build pairwise distance matrix, then the linkage matrix,
    # then the clusters
    pairwise_distances = [distances[k] for k in sorted(distances.keys())]
    linkage_matrix = average(pairwise_distances)
    clusters = fcluster(linkage_matrix, 1-cc_min, criterion='distance')
    # Build families
    families = [Family(number=n) for n in range(max(clusters))]
    for evid, cluster in zip(evids, clusters):
        families[cluster-1].append(events[evid])
    # Remove families with only one event
    families = [f for f in families if len(f) > 1]
    return families


def _write_families(config, families):
    """
    Write families to file.

    :param config: configuration object
    :type config: config.Config
    :param families: list of families
    :type families: list
    """
    sort_by = config.sort_families_by
    lon0, lat0 = config.distance_from_lon, config.distance_from_lat
    sort_keys = {
        'time': lambda f: f.starttime,
        'longitude': lambda f: f.lon,
        'latitude': lambda f: f.lat,
        'depth': lambda f: f.depth,
        'distance_from': lambda f: f.distance_from(lon0, lat0)
    }
    families = sorted(families, key=sort_keys[sort_by])
    with open(config.build_families_outfile, 'w', encoding='utf-8') as fp_out:
        fieldnames = [
            'evid', 'trace_id', 'orig_time', 'lon', 'lat', 'depth_km',
            'mag_type', 'mag', 'family_number', 'valid'
        ]
        writer = csv.writer(fp_out)
        writer.writerow(fieldnames)
        valid = True  # families are valid by default
        for number, family in enumerate(families):
            for ev in family:
                writer.writerow([
                    ev.evid, ev.trace_id, ev.orig_time, ev.lon, ev.lat,
                    ev.depth, ev.mag_type, ev.mag, number, valid
                ])


def build_families(config):
    """
    Build families of repeating earthquakes from a catalog of pairs.

    :param config: configuration object
    :type config: config.Config
    """
    try:
        _check_options(config)
    except ValueError as e:
        logger.error(e)
        rq_exit(1)
    try:
        logger.info('Reading events from pairs file...')
        events = _read_events_from_pairs_file(config)
    except FileNotFoundError:
        logger.error(
            'Unable to find event pairs file: '
            f'{config.scan_catalog_pairs_file}'
        )
        rq_exit(1)
    if config.clustering_algorithm == 'shared':
        logger.info('Building families from shared events...')
        families = _build_families_from_shared_events(events, config.cc_min)
    elif config.clustering_algorithm == 'UPGMA':
        logger.info('Building families using UPGMA...')
        families = _build_families_from_upgma(events, config.cc_min)
    _write_families(config, families)
    logger.info(f'Done! Output written to: {config.build_families_outfile}')
