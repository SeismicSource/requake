# -*- coding: utf8 -*-
"""
Family classes and functions.

:copyright:
    2021-2022 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
import csv
import numpy as np
from obspy import UTCDateTime, Stream
from obspy.geodetics import gps2dist_azimuth
from .catalog import RequakeEvent
from .waveforms import (
    get_event_waveform, align_traces, build_template)

logger = logging.getLogger(__name__.split('.')[-1])


class Family(list):
    lon = None
    lat = None
    depth = None  # km
    starttime = None
    endtime = None
    duration = None  # years
    number = None
    valid = True

    def __str__(self):
        s = '{:2d} {:2d} {:8.4f} {:8.4f} {:7.3f} {} {} {:4.1f}'.format(
            self.number, len(self), self.lon, self.lat, self.depth,
            self.starttime, self.endtime, self.duration
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
        year = 365*24*60*60
        self.duration = (self.endtime - self.starttime)/year

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
    # append last family
    families.append(family)
    return families


def read_selected_families(config):
    """Read and select families based on family number, validity and length."""
    family_numbers = _build_family_number_list(config)
    families = read_families(config)
    families_selected = list()
    for family in families:
        if family.number not in family_numbers:
            continue
        if not family.valid:
            msg = 'Family "{}" is flagged as not valid'.format(family.number)
            logger.warning(msg)
            continue
        if (family.endtime - family.starttime) < config.args.longerthan:
            msg = 'Family "{}" is too short'.format(family.number)
            logger.warning(msg)
            continue
        families_selected.append(family)
    if not families_selected:
        msg = 'No family found with numbers "{}"'.format(family_numbers)
        raise Exception(msg)
    return families_selected


def get_family(config, families, family_number):
    """Get a given family from a list of families."""
    for family in families:
        if family.number != family_number:
            continue
        if not family.valid:
            msg = 'Family "{}" is flagged as not valid'.format(family_number)
            raise Exception(msg)
        if (family.endtime - family.starttime) < config.args.longerthan:
            msg = 'Family "{}" is too short'.format(family.number)
            raise Exception(msg)
        return family
    msg = 'No family found with number "{}"'.format(family_number)
    raise Exception(msg)


def get_family_waveforms(config, family):
    """Get waveforms for a given family."""
    st = Stream()
    for ev in family:
        try:
            st += get_event_waveform(config, ev)
        except Exception as m:
            logger.error(str(m))
            pass
    if not st:
        msg = 'No traces found for family {}'.format(family.number)
        raise Exception(msg)
    return st


def get_family_aligned_waveforms_and_template(config, family):
    """Get aligned waveforms and template for a given family."""
    st = get_family_waveforms(config, family)
    align_traces(config, st)
    build_template(config, st, family)
    return st


def _build_family_number_list(config):
    """Build a list of family numbers from config option."""
    family_numbers = config.args.family_numbers
    if family_numbers == 'all':
        with open(config.build_families_outfile, 'r') as fp:
            reader = csv.DictReader(fp)
            fn = sorted(set(int(row['family_number']) for row in reader))
        return fn
    try:
        if ',' in family_numbers:
            fn = list(map(int, family_numbers.split(',')))
        elif '-' in family_numbers:
            family0, family1 = map(int, family_numbers.split('-'))
            fn = list(range(family0, family1))
        elif family_numbers.isnumeric():
            fn = [int(family_numbers), ]
        else:
            raise Exception
    except Exception:
        msg = 'Invalid family numbers: {}'.format(family_numbers)
        raise Exception(msg)
    return fn
