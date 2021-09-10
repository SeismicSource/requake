#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import csv
from obspy import UTCDateTime
from .catalog import RequakeEvent
from .families import Family
from .rq_setup import rq_exit


def _read_pairs(config):
    pairs = list()
    fp = open(config.scan_catalog_pairs_file, 'r')
    reader = csv.DictReader(fp)
    for row in reader:
        cc_max = float(row['cc_max'])
        if abs(cc_max) < config.cc_min:
            continue
        ev1 = RequakeEvent()
        ev1.evid = row['evid1']
        ev1.orig_time = UTCDateTime(row['orig_time1'])
        ev1.lon = float(row['lon1'])
        ev1.lat = float(row['lat1'])
        ev1.depth = float(row['depth_km1'])
        ev1.mag_type = row['mag_type1']
        ev1.mag = float(row['mag1'])
        ev1.trace_id = row['trace_id']
        ev2 = RequakeEvent()
        ev2.evid = row['evid2']
        ev2.orig_time = UTCDateTime(row['orig_time2'])
        ev2.lon = float(row['lon2'])
        ev2.lat = float(row['lat2'])
        ev2.depth = float(row['depth_km2'])
        ev2.mag_type = row['mag_type2']
        ev2.mag = float(row['mag2'])
        ev2.trace_id = row['trace_id']
        pair = Family()
        pair.extend([ev1, ev2])
        pairs.append(pair)
    fp.close()
    return pairs


def build_families(config):
    # Check options
    sort_by = config.sort_families_by
    lon0, lat0 = config.distance_from_lon, config.distance_from_lat
    if sort_by == 'distance_from' and (lon0 is None or lat0 is None):
        logger.error(
            '"sort_families_by" set to "distance_from", '
            'but "distance_from_lon" and/or "distance_from_lat" '
            'are not specified')
        rq_exit(1)
    logger.info('Building event families...')
    try:
        pairs = _read_pairs(config)
    except FileNotFoundError:
        logger.error(
            'Unable to find event pairs file: {}'.format(
                config.scan_catalog_pairs_file
            ))
        rq_exit(1)
    # Build families from pairs sharing an event
    families = list()
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
    # Sort families
    sort_keys = {
        'time': lambda f: f.starttime,
        'longitude': lambda f: f.lon,
        'latitude': lambda f: f.lat,
        'depth': lambda f: f.depth,
        'distance_from': lambda f: f.distance_from(lon0, lat0)
    }
    families = sorted(families, key=sort_keys[sort_by])
    # Write families to output file
    fp_out = open(config.build_families_outfile, 'w')
    fieldnames = [
        'evid', 'trace_id', 'orig_time', 'lon', 'lat', 'depth_km',
        'mag_type', 'mag', 'family_number', 'valid'
    ]
    writer = csv.writer(fp_out)
    writer.writerow(fieldnames)
    for number, family in enumerate(families):
        for ev in family:
            writer.writerow([
                ev.evid, ev.trace_id, ev.orig_time, ev.lon, ev.lat, ev.depth,
                ev.mag_type, ev.mag, number, True
            ])
    fp_out.close()
    logger.info('Done! Output written to: {}'.format(
        config.build_families_outfile))
