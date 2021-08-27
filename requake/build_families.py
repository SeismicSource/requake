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
from .rq_setup import rq_exit


class Event():
    """An hashable event class."""

    evid = None
    orig_time = None
    lon = None
    lat = None
    depth = None
    mag_type = None
    mag = None

    def __eq__(self, other):
        if self.evid == other.evid:
            return True
        else:
            return False

    def __gt__(self, other):
        return self.orig_time > other.orig_time

    def __ge__(self, other):
        return self.orig_time >= other.orig_time

    def __lt__(self, other):
        return self.orig_time < other.orig_time

    def __le__(self, other):
        return self.orig_time <= other.orig_time

    def __hash__(self):
        return self.evid.__hash__()

    def __str__(self):
        s = '{} {} {} {}'.format(
            self.evid, self.orig_time, self.mag_type, self.mag)
        return s


def _read_pairs(config):
    pairs = list()
    fp = open(config.scan_catalog_outfile, 'r')
    reader = csv.DictReader(fp)
    for row in reader:
        cc_max = float(row['cc_max'])
        if abs(cc_max) < config.cc_min:
            continue
        ev1 = Event()
        ev1.evid = row['evid1']
        ev1.orig_time = row['orig_time1']
        ev1.lon = row['lon1']
        ev1.lat = row['lat1']
        ev1.depth = row['depth_km1']
        ev1.mag_type = row['mag_type1']
        ev1.mag = row['mag1']
        ev2 = Event()
        ev2.evid = row['evid2']
        ev2.orig_time = row['orig_time2']
        ev2.lon = row['lon2']
        ev2.lat = row['lat2']
        ev2.depth = row['depth_km2']
        ev2.mag_type = row['mag_type2']
        ev2.mag = row['mag2']
        # each pair has to be a list, to be exetendable later as a family
        pairs.append([ev1, ev2])
    fp.close()
    return pairs


def build_families(config):
    logger.info('Building event families...')
    try:
        pairs = _read_pairs(config)
    except FileNotFoundError:
        logger.error(
            'Unable to find event pairs file: {}'.format(
                config.scan_catalog_outfile
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
                # [:] is important because we want to replace the whole
                # family with the new one
                family[:] = sorted(set(family))
                break
        if not found_family:
            families.append(pair)
    # Write families to output file
    fp_out = open(config.build_families_outfile, 'w')
    fieldnames = [
        'evid', 'orig_time', 'lon', 'lat', 'depth_km', 'mag_type', 'mag',
        'family_number'
    ]
    writer = csv.writer(fp_out)
    writer.writerows([fieldnames])
    for number, family in enumerate(families):
        for ev in family:
            writer.writerows([[
                ev.evid, ev.orig_time, ev.lon, ev.lat, ev.depth,
                ev.mag_type, ev.mag, number
            ]])
    fp_out.close()
    logger.info('Done! Output written to: {}'.format(
        config.build_families_outfile))
