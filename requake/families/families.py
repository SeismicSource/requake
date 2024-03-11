# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Family classes and functions.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
import numpy as np
from obspy import UTCDateTime, Stream
from obspy.geodetics import gps2dist_azimuth
from ..formulas.conversion import float_or_none
from ..catalog.catalog import RequakeEvent
from ..waveforms.waveforms import (
    get_event_waveform, align_traces, build_template)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class FamilyNotFoundError(Exception):
    """Exception raised when a family is not found."""


class Family(list):
    """
    A list of events belonging to the same family.
    """
    def __init__(self, number=-1):
        self.lon = None
        self.lat = None
        self.depth = None  # km
        self.starttime = None
        self.endtime = None
        self.duration = None  # years
        self.number = number
        self.valid = True

    def __str__(self):
        return (
            f'{self.number:2d} {len(self):2d} '
            f'{self.lon:8.4f} {self.lat:8.4f} {self.depth:7.3f} '
            f'{self.starttime} {self.endtime} {self.duration:4.1f} '
            f'{self.valid}'
        )

    def append(self, ev):
        """
        Append an event to the family and update family attributes.

        If the event is already in the family, it is not appended.

        :param ev: Event to append.
        :type ev: RequakeEvent
        """
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

    def extend(self, ev_list):
        """
        Extend the family with a list of events.

        Events already in the family are not added.

        :param ev_list: List of events to append.
        :type ev_list: list of RequakeEvent
        """
        for ev in ev_list:
            self.append(ev)

    def distance_from(self, lon, lat):
        """
        Return the distance in km from the family to a given point.

        :param lon: Longitude of the point.
        :type lon: float
        :param lat: Latitude of the point.
        :type lat: float
        :return: Distance in km.
        :rtype: float
        """
        distance, _, _ = gps2dist_azimuth(self.lat, self.lon, lat, lon)
        return distance/1e3


def read_families(config):
    """
    Read a list of families from file.

    :param config: requake configuration object
    :type config: config.Config
    :return: List of families.
    :rtype: list of Family
    """
    with open(config.build_families_outfile, 'r', encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        old_family_number = -1
        families = []
        family = None
        for row in reader:
            ev = RequakeEvent()
            ev.evid = row['evid']
            ev.orig_time = UTCDateTime(row['orig_time'])
            ev.lon = float_or_none(row['lon'])
            ev.lat = float_or_none(row['lat'])
            ev.depth = float_or_none(row['depth_km'])
            ev.mag_type = row['mag_type']
            ev.mag = float_or_none(row['mag'])
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
    """
    Read and select families based on family number, validity, length
    and number of events.

    :param config: requake configuration object
    :type config: config.Config
    :return: List of families.
    :rtype: list of Family

    :raises FamilyNotFoundError: if no family is found
    """
    family_numbers = _build_family_number_list(config)
    families = read_families(config)
    families_selected = []
    for family in families:
        if family.number not in family_numbers:
            continue
        if not family.valid:
            logger.warning(f'Family "{family.number}" is flagged as not valid')
            continue
        if (family.endtime - family.starttime) < config.args.longerthan:
            logger.warning(f'Family "{family.number}" is too short')
            continue
        if len(family) < config.args.minevents:
            logger.warning(
                f'Family "{family.number}" has less than '
                f'{config.args.minevents} events'
            )
            continue
        families_selected.append(family)
    if not families_selected:
        raise FamilyNotFoundError('No family found')
    return families_selected


def get_family(config, families, family_number):
    """
    Get a given family from a list of families.

    :param config: requake configuration object
    :type config: config.Config
    :param families: List of families.
    :type families: list of Family
    :param family_number: Family number.
    :type family_number: int
    :return: The family.
    :rtype: Family
    """
    for family in families:
        if family.number != family_number:
            continue
        if not family.valid:
            msg = f'Family "{family_number}" is flagged as not valid'
            raise Exception(msg)
        if (family.endtime - family.starttime) < config.args.longerthan:
            msg = f'Family "{family.number}" is too short'
            raise Exception(msg)
        return family
    msg = f'No family found with number "{family_number}"'
    raise Exception(msg)


def get_family_waveforms(config, family):
    """
    Get waveforms for a given family.

    :param config: requake configuration object
    :type config: config.Config
    :param family: The family.
    :type family: Family
    :return: The waveforms.
    :rtype: obspy.Stream
    """
    st = Stream()
    for ev in family:
        try:
            st += get_event_waveform(config, ev)
        except Exception as m:
            logger.error(str(m))
    if not st:
        msg = f'No traces found for family {family.number}'
        raise Exception(msg)
    return st


def get_family_aligned_waveforms_and_template(config, family):
    """
    Get aligned waveforms and template for a given family.

    :param config: requake configuration object
    :type config: config.Config
    :param family: The family.
    :type family: Family
    :return: An obspy stream containing the aligned waveforms and the template.
    :rtype: obspy.Stream
    """
    st = get_family_waveforms(config, family)
    align_traces(config, st)
    build_template(config, st, family)
    return st


def _build_family_number_list(config):
    """Build a list of family numbers from config option."""
    family_numbers = config.args.family_numbers
    if family_numbers == 'all':
        with open(config.build_families_outfile, 'r', encoding='utf-8') as fp:
            reader = csv.DictReader(fp)
            fn = sorted({int(row['family_number']) for row in reader})
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
    except Exception as e:
        raise Exception(f'Invalid family numbers: {family_numbers}') from e
    return fn
