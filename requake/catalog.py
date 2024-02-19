# -*- coding: utf8 -*-
"""
Classes and functions for downloading, reading and writing catalogs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import contextlib
import urllib.request
from obspy.clients.fdsn.header import URL_MAPPINGS
from obspy import UTCDateTime


def _float_or_none(string):
    try:
        val = float(string)
    except (TypeError, ValueError):
        val = None
    return val


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
        return f'{self.evid} {self.orig_time} {self.mag_type} {self.mag}'

    def from_fdsn_text(self, line):
        """
        Initialize from a line in FDSN text file format.

        :param line: a line in FDSN text file format
        :type line: str
        """
        word = line.split('|')
        self.evid = word[0]
        self.orig_time = UTCDateTime(word[1])
        self.lat = _float_or_none(word[2])
        self.lon = _float_or_none(word[3])
        self.depth = _float_or_none(word[4])
        self.author = word[5]
        self.catalog = word[6]
        self.contributor = word[7]
        self.contributor_id = word[8]
        self.mag_type = word[9]
        self.mag = _float_or_none(word[10])
        self.mag_author = word[11]
        self.location_name = word[12]

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
        return '\n'.join(str(ev) for ev in self)

    def write(self, filename):
        """
        Write in FDSN text file format.

        :param filename: output filename
        :type filename: str
        """
        with open(filename, 'w', encoding='utf8') as fp:
            for ev in self:
                fp.write(ev.fdsn_text() + '\n')


def get_events(
        baseurl,
        starttime=None, endtime=None,
        minlatitude=None, maxlatitude=None,
        minlongitude=None, maxlongitude=None,
        latitude=None, longitude=None, minradius=None, maxradius=None,
        mindepth=None, maxdepth=None,
        minmagnitude=None, maxmagnitude=None):
    """
    Download from a fdsn-event webservice using text format.

    :param baseurl: base URL of the fdsn-event webservice
    :type baseurl: str
    :param starttime: start time
    :type starttime: obspy.UTCDateTime or str
    :param endtime: end time
    :type endtime: obspy.UTCDateTime or str
    :param minlatitude: minimum latitude
    :type minlatitude: float
    :param maxlatitude: maximum latitude
    :type maxlatitude: float
    :param minlongitude: minimum longitude
    :type minlongitude: float
    :param maxlongitude: maximum longitude
    :type maxlongitude: float
    :param latitude: latitude of radius center
    :type latitude: float
    :param longitude: longitude of radius center
    :type longitude: float
    :param minradius: minimum radius
    :type minradius: float
    :param maxradius: maximum radius
    :type maxradius: float
    :param mindepth: minimum depth
    :type mindepth: float
    :param maxdepth: maximum depth
    :type maxdepth: float
    :param minmagnitude: minimum magnitude
    :type minmagnitude: float
    :param maxmagnitude: maximum magnitude
    :type maxmagnitude: float

    :return: a RequakeCatalog object
    :rtype: RequakeCatalog
    """
    # pylint: disable=unused-argument
    arguments = locals()
    query = 'query?format=text&nodata=404&'
    for key, val in arguments.items():
        if key in ['baseurl']:
            continue
        if val is None:
            continue
        if isinstance(val, UTCDateTime):
            val = val.strftime('%Y-%m-%dT%H:%M:%S')
        query += f'{key}={val}&'
    # remove last "&" symbol
    query = query[:-1]
    # see if baseurl is an alias defined in ObsPy
    with contextlib.suppress(KeyError):
        baseurl = URL_MAPPINGS[baseurl]
    baseurl = f'{baseurl}/fdsnws/event/1/'
    url = baseurl + query
    cat = RequakeCatalog()
    with urllib.request.urlopen(url) as f:
        content = f.read().decode('utf-8')
    for line in content.split('\n'):
        if not line:
            continue
        if line[0] == '#':
            continue
        try:
            ev = RequakeEvent()
            ev.from_fdsn_text(line)
        except Exception:
            continue
        cat.append(ev)
    return cat


def read_events(filename):
    """
    Read events in FDSN text file format.

    :param filename: input filename
    :type filename: str

    :return: a RequakeCatalog object
    :rtype: RequakeCatalog
    """
    cat = RequakeCatalog()
    with open(filename, 'r', encoding='utf8') as fp:
        for line in fp:
            if not line:
                continue
            if line[0] == '#':
                continue
            ev = RequakeEvent()
            ev.from_fdsn_text(line)
            cat.append(ev)
    return cat


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
