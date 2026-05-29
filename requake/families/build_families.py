# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from itertools import combinations
from scipy.cluster.hierarchy import average, fcluster
from ..config import config, rq_exit
from ..database.db import DatabaseCorruptError, get_db_path
from ..database.pairs import (
    PairsMetadataError,
    PairsSchemaError,
    PairsTableNotFoundError,
)
from ..database.families import write_families as write_families_to_db
from .pairs import read_events_from_pairs
from .families import Family
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _check_options():
    """
    Check the consistency of the configuration options.

    :raises ValueError: if the configuration options are inconsistent
    """
    sort_by = config.sort_families_by
    lon0, lat0 = config.distance_from_lon, config.distance_from_lat
    if sort_by == 'distance_from' and (lon0 is None or lat0 is None):
        raise ValueError(
            '"sort_families_by" set to "distance_from", '
            'but "distance_from_lon" and/or "distance_from_lat" '
            'are not specified')


def _build_families_from_shared_events(events):
    """
    Build families by clustering all event pairs sharing an event.

    :param events: dictionary of events
    :type events: dict
    :return: list of families
    :rtype: list
    """
    families = []
    for ev in events.values():
        new_family = Family()
        new_family.append(ev)
        for evid, cc in ev.correlations.items():
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
        k: 1 - correlations.get(k, min_correlation)
        for k in combinations(evids, 2)
    }
    # Build pairwise distance matrix, then the linkage matrix,
    # then the clusters
    pairwise_distances = [distances[k] for k in sorted(distances.keys())]
    linkage_matrix = average(pairwise_distances)
    clusters = fcluster(linkage_matrix, 1 - cc_min, criterion='distance')
    # Build families
    families = [Family(number=n) for n in range(max(clusters))]
    for evid, cluster in zip(evids, clusters):
        families[cluster - 1].append(events[evid])
    # Remove families with only one event
    families = [f for f in families if len(f) > 1]
    return families


def _write_families(families):
    """
    Write families to the SQLite database.

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
    valid = True  # families are valid by default
    for number, family in enumerate(families):
        family.number = number
        family.valid = valid
    write_families_to_db(families)


def build_families():
    """Build families of repeating earthquakes from a catalog of pairs."""
    try:
        _check_options()
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    try:
        logger.info(
            'Reading events from event pairs in '
            f'db file {get_db_path()}...'
        )
        cc_min = (
            config.cc_min
            if config.clustering_algorithm == 'shared'
            else None
        )
        events = read_events_from_pairs(cc_min=cc_min)
    except (FileNotFoundError, PairsTableNotFoundError):
        logger.error(
            'Unable to find event pairs in database: '
            f'{get_db_path()}'
        )
        rq_exit(1)
    except (PairsMetadataError, PairsSchemaError) as msg:
        logger.error(msg)
        rq_exit(1)
    except DatabaseCorruptError as msg:
        logger.error(msg)
        rq_exit(1)
    if config.clustering_algorithm == 'shared':
        logger.info('Building families from shared events...')
        families = _build_families_from_shared_events(events)
    elif config.clustering_algorithm == 'UPGMA':
        logger.info('Building families using UPGMA...')
        families = _build_families_from_upgma(events, config.cc_min)
    _write_families(families)
    logger.info(f'Done! Output written to: {get_db_path()}')
