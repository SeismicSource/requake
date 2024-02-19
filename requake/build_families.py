# -*- coding: utf8 -*-
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
import csv
from itertools import combinations
from scipy.cluster.hierarchy import average, fcluster
from obspy import UTCDateTime
from .catalog import RequakeEvent
from .families import Family
from .rq_setup import rq_exit
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


def _read_pairs(config):
    """
    Read pairs from file.

    :param config: configuration object
    :type config: config.Config
    :return: list of pairs
    :rtype: list
    """
    pairs = []
    events = {}
    with open(config.scan_catalog_pairs_file, 'r', encoding='utf8') as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            cc_max = float(row['cc_max'])
            if abs(cc_max) < config.cc_min:
                continue
            evid1 = row['evid1']
            try:
                ev1 = events[evid1]
            except KeyError:
                ev1 = RequakeEvent(
                    evid=evid1, orig_time=UTCDateTime(row['orig_time1']),
                    lon=float(row['lon1']), lat=float(row['lat1']),
                    depth=float(row['depth_km1']), mag_type=row['mag_type1'],
                    mag=float(row['mag1']), trace_id=row['trace_id']
                )
                events[evid1] = ev1
            evid2 = row['evid2']
            try:
                ev2 = events[evid2]
            except KeyError:
                ev2 = RequakeEvent(
                    evid=evid2, orig_time=UTCDateTime(row['orig_time2']),
                    lon=float(row['lon2']), lat=float(row['lat2']),
                    depth=float(row['depth_km2']), mag_type=row['mag_type2'],
                    mag=float(row['mag2']), trace_id=row['trace_id']
                )
                events[evid2] = ev2
            ev1.correlations[ev2.evid] = ev2.correlations[ev1.evid] = cc_max
            pair = Family()
            pair.extend([ev1, ev2])
            pairs.append(pair)
    return pairs


def _build_families_from_shared_events(pairs):
    """
    Build families from pairs sharing an event.

    :param pairs: list of pairs
    :type pairs: list
    :return: list of families
    :rtype: list
    """
    families = []
    for pair in pairs:
        ev1, ev2 = pair
        found_family = False
        for family in families:
            if ev1 in family or ev2 in family:
                found_family = True
                family.extend(pair)
                break
        if not found_family:
            families.append(pair)
    return families


def _build_families_from_upgma(pairs, cc_min):
    """
    Build families from pairs using the UPGMA algorithm.

    Reference: https://en.wikipedia.org/wiki/UPGMA

    :param pairs: list of pairs
    :type pairs: list
    :return: list of families
    :rtype: list
    """
    events = {ev.evid: ev for pair in pairs for ev in pair}
    evids = sorted(set(events.keys()))
    # We use sorted tuples of evids as keys to avoid duplicates with inverted
    # order of evids, e.g. (evid1, evid2) and (evid2, evid1)
    correlations = {
        tuple(sorted((evid1, evid2))): cc
        for evid1, ev in events.items()
        for evid2, cc in ev.correlations.items()
    }
    # Build distance dictionary. Distance is 1 - correlation.
    # We use cc_min-0.1 for pairs with no correlation, so that they are not
    # clustered together
    distances = {
        k: 1-correlations.get(k, cc_min-0.1) for k in combinations(evids, 2)}
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
        logger.info('Reading pairs...')
        pairs = _read_pairs(config)
    except FileNotFoundError:
        logger.error(
            'Unable to find event pairs file: '
            f'{config.scan_catalog_pairs_file}'
        )
        rq_exit(1)
    if config.clustering_algorithm == 'shared':
        logger.info('Building families from shared events...')
        families = _build_families_from_shared_events(pairs)
    elif config.clustering_algorithm == 'UPGMA':
        logger.info('Building families using UPGMA...')
        families = _build_families_from_upgma(pairs, config.cc_min)
    _write_families(config, families)
    logger.info(f'Done! Output written to: {config.build_families_outfile}')
