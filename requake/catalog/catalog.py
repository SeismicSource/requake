# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Classes and functions for downloading, reading and writing catalogs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import numpy as np
from obspy import UTCDateTime
from ..formulas.conversion import float_or_none
from ..waveforms.station_metadata import get_traceid_coords


class RequakeEvent():
    """
    A hashable event class.

    Contains the same fields as in the FDSN text file format, plus a
    trace_id field and a correlations dictionary.
    """

    def __init__(self, evid=None, orig_time=None, lon=None, lat=None,
                 depth=None, mag_type=None, mag=None, author=None,
                 catalog=None, contributor=None, contributor_id=None,
                 mag_author=None, location_name=None, trace_id=None):
        self.evid = evid
        self.orig_time = orig_time
        self.lon = lon
        self.lat = lat
        self.depth = depth
        self.mag_type = mag_type
        self.mag = mag
        self.author = author
        self.catalog = catalog
        self.contributor = contributor
        self.contributor_id = contributor_id
        self.mag_author = mag_author
        self.location_name = location_name
        self.trace_id = trace_id
        self.correlations = {}

    def __eq__(self, other):
        return self.evid == other.evid and self.trace_id == other.trace_id

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
        return (
            f'{self.evid} {self.orig_time} '
            f'{self.lon} {self.lat} {self.depth} {self.mag_type} {self.mag}'
        )

    def from_fdsn_text(self, line):
        """
        Initialize from a line in FDSN text file format.

        :param line: a line in FDSN text file format
        :type line: str

        :raises ValueError: if line is not in FDSN text file format
        """
        try:
            word = line.strip().split('|')
            self.evid = word[0]
            self.orig_time = UTCDateTime(word[1])
            self.lat = float_or_none(word[2])
            self.lon = float_or_none(word[3])
            self.depth = float_or_none(word[4])
            self.author = word[5]
            self.catalog = word[6]
            self.contributor = word[7]
            self.contributor_id = word[8]
            self.mag_type = word[9]
            self.mag = float_or_none(word[10])
            self.mag_author = word[11]
            self.location_name = word[12]
        except IndexError as e:
            raise ValueError(f'Invalid line: {line}') from e

    def fdsn_text(self):
        """
        Return a string in FDSN text file format.

        :return: a string in FDSN text file format
        :rtype: str
        """
        fields = (
            self.evid,
            self.orig_time.strftime('%Y-%m-%dT%H:%M:%S'),
            self.lat,
            self.lon,
            self.depth,
            self.author,
            self.catalog,
            self.contributor,
            self.contributor_id,
            self.mag_type,
            self.mag,
            self.mag_author,
            self.location_name,
        )
        return '|'.join(map(str, fields))


class RequakeCatalog(list):
    """A catalog class."""

    def __str__(self):
        """
        Return a string representation of the catalog.

        :return: a string representation of the catalog
        :rtype: str
        """
        return '\n'.join(str(ev) for ev in self)

    def deduplicate(self):
        """
        Deduplicate events in the catalog.

        The operation is in place.
        """
        self[:] = list(set(self))

    def sort(self):
        """
        Sort events by origin time.

        The operation is in place.
        """
        self[:] = sorted(self, key=lambda ev: ev.orig_time)

    def read(self, filename):
        """
        Read catalog from FDSN text file format.

        Skips events already in the catalog.

        :param filename: input filename
        :type filename: str

        :raises FileNotFoundError: if filename does not exist
        :raises ValueError: if line is not in FDSN text file format
        """
        with open(filename, 'r', encoding='utf8') as fp:
            for line in fp:
                if not line:
                    continue
                if line[0] == '#':
                    continue
                ev = RequakeEvent()
                ev.from_fdsn_text(line)
                self.append(ev)
        self.deduplicate()

    def write(self, filename):
        """
        Write catalog in FDSN text file format.

        :param filename: output filename
        :type filename: str
        """
        with open(filename, 'w', encoding='utf8') as fp:
            for ev in self:
                fp.write(ev.fdsn_text() + '\n')


def read_stored_catalog(config):
    """
    Read the catalog stored in the output directory.

    :param config: Configuration object.
    :type config: config.Config

    :return: Catalog object.
    :rtype: RequakeCatalog

    :raises ValueError: if error reading catalog file
    :raises FileNotFoundError: if catalog file not found
    """
    try:
        cat = RequakeCatalog()
        cat.read(config.scan_catalog_file)
        return cat
    except ValueError as m:
        raise ValueError(
            f'Error reading catalog file {config.scan_catalog_file}'
        ) from m
    except FileNotFoundError as m:
        raise FileNotFoundError(
            f'Catalog file {config.scan_catalog_file} not found'
        ) from m


def fix_non_locatable_events(catalog, config):
    """
    Fix non-locatable events in catalog.

    :param catalog: a RequakeCatalog object
    :type catalog: RequakeCatalog
    :param config: a Config object
    :type config: config.Config
    """
    if not any(ev.lat is None or ev.lon is None for ev in catalog):
        return
    traceid_coords = get_traceid_coords(config)
    mean_lat = np.mean([
        coords['latitude'] for coords in traceid_coords.values()])
    mean_lon = np.mean([
        coords['longitude'] for coords in traceid_coords.values()])
    for ev in catalog:
        if ev.lat is None or ev.lon is None:
            ev.lat = mean_lat
            ev.lon = mean_lon
            ev.depth = 10.0


def _base26(val):
    """
    Represent value using 6 characters from latin alphabet (26 chars).

    :param val: value to represent
    :type val: int

    :return: a string of 6 characters from latin alphabet
    :rtype: str
    """
    chars = [
      'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j',
      'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't',
      'u', 'v', 'w', 'x', 'y', 'z'
    ]
    base = len(chars)
    ret = ''
    while True:
        ret = chars[val % base] + ret
        val = val // base
        if val == 0:
            break
    return ret.rjust(6, 'a')


def generate_evid(orig_time):
    """
    Generate an event id from origin time.

    :param orig_time: origin time
    :type orig_time: obspy.UTCDateTime

    :return: an event id
    :rtype: str
    """
    prefix = 'reqk'
    year = orig_time.year
    orig_year = UTCDateTime(year=year, month=1, day=1)
    val = int(orig_time - orig_year)
    # normalize val between 0 (aaaaaa) and 26**6-1 (zzzzzz)
    maxval = 366*24*3600  # max number of seconds in leap year
    normval = int(val/maxval * (26**6-1))
    ret = _base26(normval)
    return f'{prefix}{year}{ret}'
