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
import sys
import contextlib
from itertools import combinations
from scipy.cluster.hierarchy import average, fcluster
from ..config import config, rq_exit
from ..config.run_params import (
    family_build_parameters,
    parameters_digest,
    parameters_json,
)
from ..config.utils import run_with_spinner
from ..database.db import DatabaseCorruptError, get_db_path
from ..database.family_builds import (
    BUILD_STATUS_COMPLETE,
    BUILD_STATUS_FAILED,
    FamilyBuildNotFoundError,
    create_family_build,
    find_family_build_by_hash,
    finish_family_build,
    read_family_build,
    reset_family_build,
)
from ..database.families import write_families as write_families_to_db
from ..database.pairs import (
    PairsMetadataError,
    PairsSchemaError,
    PairsTableNotFoundError,
)
from ..database.scans import (
    ScanNotFoundError,
    resolve_scan_id,
    scan_catalog_id,
)
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


def _write_families(families, build_id, catalog_id):
    """
    Write families to the SQLite database.

    :param families: list of families
    :type families: list
    :param build_id: family build the families belong to
    :type build_id: int
    :param catalog_id: catalog the events belong to
    :type catalog_id: int
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
    write_families_to_db(build_id, catalog_id, families)


def _ask_build_action(build_row):
    """Ask the user what to do with an existing identical build."""
    args = config.args
    build_id = int(build_row['build_id'])
    if getattr(args, 'force', False):
        return 'replace'
    if not sys.stdin.isatty():
        logger.error(
            'A family build with the same parameters already exists as '
            f'build {build_id} of scan {int(build_row["scan_id"])}.'
        )
        logger.error(
            'Cannot prompt in non-interactive mode. Use --force to '
            'replace it or --build-id to target a specific build.'
        )
        rq_exit(1)
    logger.warning(
        'A family build with the same parameters already exists as '
        f'build {build_id} of scan {int(build_row["scan_id"])}.'
    )
    logger.warning(
        'You can replace it or add a new build from the same pairs.'
    )
    prompt = (
        'Choose action: [r]eplace, [n]ew, [a]bort (default: abort): '
    )
    choices = {
        'r': 'replace',
        'replace': 'replace',
        'n': 'new',
        'new': 'new',
        'a': 'abort',
        'abort': 'abort',
    }
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            return 'abort'
        action = choices.get(answer)
        if action is not None:
            return action
        print('Invalid choice. Please type r, n, or a.')


def _select_build_action(scan_id, method, params_hash):
    """Return the build id to use and the action to perform."""
    requested = getattr(config.args, 'build_id', None)
    if requested is not None:
        try:
            read_family_build(requested)
        except FamilyBuildNotFoundError as msg:
            logger.error(msg)
            rq_exit(1)
        return int(requested), 'replace'
    existing = find_family_build_by_hash(scan_id, method, params_hash)
    if existing is None:
        return None, 'new'
    return int(existing['build_id']), _ask_build_action(existing)


def build_families():
    """Build families of repeating earthquakes from a catalog of pairs."""
    try:
        _check_options()
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    try:
        scan_id = resolve_scan_id(getattr(config.args, 'scan_id', None))
        catalog_id = scan_catalog_id(scan_id)
    except ScanNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    method = config.clustering_algorithm
    params = family_build_parameters()
    params_hash = parameters_digest(params)
    build_id, action = _select_build_action(scan_id, method, params_hash)
    if action == 'abort':
        logger.info('Family build aborted by user')
        rq_exit(0)
    if action == 'replace':
        reset_family_build(
            build_id,
            method,
            config.cc_min,
            params_hash,
            parameters_json(params),
            label=getattr(config.args, 'label', None),
            scan_id=scan_id,
        )
        logger.info(f'Replacing family build {build_id}')
    else:
        build_id = create_family_build(
            scan_id,
            method,
            config.cc_min,
            params_hash,
            parameters_json(params),
            label=getattr(config.args, 'label', None),
        )
        logger.info(f'Family build stored as build {build_id}')
    try:
        cc_min = (
            config.cc_min
            if config.clustering_algorithm == 'shared'
            else None
        )
        read_message = (
            f'Reading events from the pairs of scan {scan_id} in '
            f'db file {get_db_path()}...'
        )
        logger.debug(read_message)
        events = run_with_spinner(
            read_message,
            lambda: read_events_from_pairs(cc_min=cc_min, scan_id=scan_id),
        )
    except (FileNotFoundError, PairsTableNotFoundError):
        logger.error(
            'Unable to find event pairs in database: '
            f'{get_db_path()}'
        )
        finish_family_build(build_id, status=BUILD_STATUS_FAILED)
        rq_exit(1)
    except (PairsMetadataError, PairsSchemaError) as msg:
        logger.error(msg)
        finish_family_build(build_id, status=BUILD_STATUS_FAILED)
        rq_exit(1)
    except DatabaseCorruptError as msg:
        logger.error(msg)
        finish_family_build(build_id, status=BUILD_STATUS_FAILED)
        rq_exit(1)
    if config.clustering_algorithm == 'shared':
        build_message = 'Building families from shared events...'
        logger.debug(build_message)
        families = run_with_spinner(
            build_message,
            lambda: _build_families_from_shared_events(events),
        )
    elif config.clustering_algorithm == 'UPGMA':
        build_message = 'Building families using UPGMA...'
        logger.debug(build_message)
        families = run_with_spinner(
            build_message,
            lambda: _build_families_from_upgma(events, config.cc_min),
        )
    nfamilies = None
    nevents = None
    status = BUILD_STATUS_FAILED
    try:
        _write_families(families, build_id, catalog_id)
        nfamilies = len(families)
        nevents = sum(len(family) for family in families)
        status = BUILD_STATUS_COMPLETE
    finally:
        with contextlib.suppress(Exception):
            finish_family_build(
                build_id,
                nfamilies=nfamilies,
                nevents=nevents,
                status=status,
            )
    logger.info(
        f'Done! Family build {build_id} written to: {get_db_path()}'
    )
