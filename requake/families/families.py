# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Family classes and functions.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import logging
import csv
import os
from glob import glob
import numpy as np
from obspy import UTCDateTime, Stream
from obspy.geodetics import gps2dist_azimuth
from ..config import config
from ..formulas import float_or_none, mag_to_slip_in_cm, mag_to_moment
from ..catalog import RequakeEvent
from ..waveforms import (
    load_inventory, get_event_waveform, align_traces, build_template,
    NoWaveformError
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class FamilyNotFoundError(Exception):
    """Exception raised when a family is not found."""


class InvalidFamilyError(Exception):
    """Exception raised when a family is not valid."""


class Family(list):
    """
    A list of events belonging to the same family.
    """
    def __init__(self, number=-1):
        """
        Initialize a family.

        :param number: Family number.
        :type number: int
        """
        self.lon = None
        self.lat = None
        self.depth = None  # km
        self.starttime = None
        self.endtime = None
        self.duration = None  # years
        self.cumul_slip = None  # cm
        self.slip_rate = None  # cm/year
        self.cumul_moment = None  # N.m
        self.magmin = None
        self.magmax = None
        self.number = number
        self.valid = True
        self.trace_id = None

    def __str__(self):
        return (
            f'{self.number:2d} {len(self):2d} '
            f'{self.lon:8.4f} {self.lat:8.4f} {self.depth:7.3f} '
            f'{self.starttime} {self.endtime} {self.duration:4.1f} '
            f'{self.magmin:3.1f} {self.magmax:3.1f} '
            f'{self.valid}'
        )

    def append(self, ev):
        """
        Append an event to the family and update family attributes.

        If the event is already in the family, it is not appended.

        :param ev: Event to append.
        :type ev: RequakeEvent
        """
        if not isinstance(ev, RequakeEvent):
            raise TypeError('Event must be a RequakeEvent')
        if ev in self:
            return
        if self.trace_id is None:
            self.trace_id = ev.trace_id
        elif ev.trace_id != self.trace_id:
            raise ValueError('Event trace_id does not match family trace_id')
        super().append(ev)
        self.sort()
        if ev.lon is not None:
            self.lon = np.mean([e.lon for e in self])
        if ev.lat is not None:
            self.lat = np.mean([e.lat for e in self])
        if ev.depth is not None:
            self.depth = np.mean([e.depth for e in self])
        self.starttime = min(ev.orig_time, self.starttime)\
            if self.starttime else ev.orig_time
        self.endtime = max(ev.orig_time, self.endtime)\
            if self.endtime else ev.orig_time
        year = 365*24*60*60
        self.duration = (self.endtime - self.starttime)/year
        if ev.mag is not None:
            self._mag_quantities(ev)

    def _mag_quantities(self, ev):
        """
        Update magnitude-related quantities.

        :param ev: Event to process.
        :type ev: RequakeEvent
        """
        self.magmin = min(ev.mag, self.magmin) if self.magmin else ev.mag
        self.magmax = max(ev.mag, self.magmax) if self.magmax else ev.mag
        if self.cumul_slip is None:
            self.cumul_slip = 0
        ev_slip = mag_to_slip_in_cm(ev.mag)
        self.cumul_slip += ev_slip
        ev_first = sorted(self)[0]
        ev_first_slip = mag_to_slip_in_cm(ev_first.mag)
        d_slip = self.cumul_slip - ev_first_slip
        self.slip_rate = np.inf if self.duration == 0 else d_slip/self.duration
        if self.cumul_moment is None:
            self.cumul_moment = 0
        self.cumul_moment += mag_to_moment(ev.mag)

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


def _read_families_from_catalog_scan():
    """
    Read a list of families from the catalog scan output.

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
        if family is not None:
            families.append(family)
    return families


def _read_families_from_template_scan():
    """
    Read a list of families from the template scan output.

    :return: List of families.
    :rtype: list of Family
    """
    template_catalogs = glob(
        f'{config.args.outdir}/template_catalogs/catalog*.txt'
    )
    families = []
    for template_catalog in template_catalogs:
        fname = os.path.basename(template_catalog)
        catalog_name = fname.split('.')[0]
        trace_id = fname.lstrip(f'{catalog_name}.').rstrip('.txt')
        family_number = int(catalog_name.lstrip('catalog'))
        family = Family(family_number)
        with open(template_catalog, 'r', encoding='utf-8') as fp:
            for row in fp:
                fields = row.split('|')
                ev = RequakeEvent()
                ev.evid = fields[0].strip()
                ev.orig_time = UTCDateTime(fields[1].strip())
                ev.lon = float(fields[2].strip())
                ev.lat = float(fields[3].strip())
                ev.depth = float(fields[4].strip())
                ev.trace_id = trace_id
                family.append(ev)
        families.append(family)
    return families


def read_families():
    """
    Read families from the catalog scan output or from the template scan
    output.

    :return: List of families.
    :rtype: list of Family
    """
    if getattr(config.args, 'template', False):
        return _read_families_from_template_scan()
    return _read_families_from_catalog_scan()


def read_selected_families():
    """
    Read and select families based on family number, validity, length
    and number of events.

    :return: List of families.
    :rtype: list of Family

    :raises FamilyNotFoundError: if no family is found
    """
    family_numbers = _build_family_number_list()
    families = read_families()
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
        if (family.endtime - family.starttime) >= config.args.shorterthan:
            logger.warning(f'Family "{family.number}" is too long')
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


def get_family(families, family_number):
    """
    Get a given family from a list of families.

    :param families: List of families.
    :type families: list of Family
    :param family_number: Family number.
    :type family_number: int
    :return: The family.
    :rtype: Family

    :raises FamilyNotFoundError: if no family is found
    :raises InvalidFamilyError: if the family is not valid
    """
    for family in families:
        if family.number != family_number:
            continue
        if not family.valid:
            raise InvalidFamilyError(
                f'Family "{family_number}" is flagged as not valid'
            )
        if (family.endtime - family.starttime) < config.args.longerthan:
            raise InvalidFamilyError(f'Family "{family_number}" is too short')
        return family
    raise FamilyNotFoundError(f'No family found with number "{family_number}"')


def get_family_waveforms(family):
    """
    Get waveforms for a given family.

    :param family: The family.
    :type family: Family
    :return: The waveforms.
    :rtype: obspy.Stream

    :raises NoWaveformError: if no waveform is found
    """
    # make sure inventory is loaded in the config object
    load_inventory()
    st = Stream()
    nevs = len(family)
    clear_line = '\x1b[2K\r'  # escape sequence to clear line
    for n, ev in enumerate(family):
        sys.stdout.write(
            f'{clear_line}Family {family.number}: '
            f'reading waveform for event {ev.evid}: {n+1}/{nevs}')
        try:
            st += get_event_waveform(ev)
        except NoWaveformError as msg:
            sys.stdout.write('\n')
            logger.error(msg)
    sys.stdout.write(
        f'{clear_line}Family {family.number}: reading waveforms: done.\n'
    )
    if not st:
        raise NoWaveformError(f'No traces found for family {family.number}')
    return st


def get_family_aligned_waveforms_and_template(family):
    """
    Get aligned waveforms and template for a given family.

    :param family: The family.
    :type family: Family
    :return: An obspy stream containing the aligned waveforms and the template.
    :rtype: obspy.Stream
    """
    st = get_family_waveforms(family)
    align_traces(st)
    build_template(st, family)
    return st


def _build_family_number_list():
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
            raise ValueError
    except ValueError as err:
        raise FamilyNotFoundError(
            f'Invalid family numbers: {family_numbers}'
        ) from err
    return fn
