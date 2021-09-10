#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Family classes and functions.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import csv
import numpy as np
from obspy import UTCDateTime
from obspy.geodetics import gps2dist_azimuth
from .catalog import RequakeEvent


class Family(list):
    lon = None
    lat = None
    depth = None
    starttime = None
    endtime = None
    number = None
    valid = True

    def __str__(self):
        s = '{:.4f} {:.4f} {:.3f} {} {}'.format(
            self.lon, self.lat, self.depth,
            self.starttime, self.endtime
        )
        return s

    def append(self, ev):
        if ev in self:
            return
        super().append(ev)
        self.sort()
        self.lon = np.mean([e.lon for e in self])
        self.lat = np.mean([e.lat for e in self])
        self.depth = np.mean([e.depth for e in self])
        self.starttime = np.min([e.orig_time for e in self])
        self.endtime = np.max([e.orig_time for e in self])

    def extend(self, item):
        for ev in item:
            self.append(ev)

    def distance_from(self, lon, lat):
        distance, _, _ = gps2dist_azimuth(self.lat, self.lon, lat, lon)
        return distance/1e3


def read_families(config):
    """Read a list of families from file."""
    fp = open(config.build_families_outfile, 'r')
    reader = csv.DictReader(fp)
    old_family_number = -1
    families = list()
    family = None
    for row in reader:
        ev = RequakeEvent()
        ev.evid = row['evid']
        ev.orig_time = UTCDateTime(row['orig_time'])
        ev.lon = float(row['lon'])
        ev.lat = float(row['lat'])
        ev.depth = float(row['depth_km'])
        ev.mag_type = row['mag_type']
        ev.mag = float(row['mag'])
        ev.trace_id = row['trace_id']
        family_number = int(row['family_number'])
        if family_number != old_family_number:
            if family is not None:
                families.append(family)
            family = Family()
            family.number = family_number
            old_family_number = family_number
        family.append(ev)
        family.valid = row['valid'] in ['True', 'true']
    return families
