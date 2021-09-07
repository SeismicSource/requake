#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Classes and functions for downloading, reading and writing catalogs.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import urllib.request
from obspy.clients.fdsn.header import URL_MAPPINGS
from obspy import UTCDateTime


class RequakeEvent():
    """
    A hashable event class.

    Contains the same fields as in the FDSN text file format, plus a
    trace_id field.
    """

    evid = None
    orig_time = None
    lon = None
    lat = None
    depth = None
    mag_type = None
    mag = None
    author = None
    catalog = None
    contributor = None
    contributor_id = None
    mag_author = None
    location_name = None
    trace_id = None

    def __eq__(self, other):
        if (self.evid == other.evid) and (self.trace_id == other.trace_id):
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

    def from_fdsn_text(self, line):
        word = line.split('|')
        self.evid = word[0]
        self.orig_time = UTCDateTime(word[1])
        self.lat = float(word[2])
        self.lon = float(word[3])
        self.depth = float(word[4])
        self.author = word[5]
        self.catalog = word[6]
        self.contributor = word[7]
        self.contributor_id = word[8]
        self.mag_type = word[9]
        self.mag = float(word[10])
        self.mag_author = word[11]
        self.location_name = word[12]

    def fdsn_text(self):
        line = '|'.join((
            self.evid,
            str(self.orig_time),
            str(self.lat),
            str(self.lon),
            str(self.depth),
            self.author,
            self.catalog,
            self.contributor,
            self.contributor_id,
            self.mag_type,
            str(self.mag),
            self.mag_author,
            self.location_name
        ))
        return(line)


class RequakeCatalog(list):
    """A catalog class."""

    def write(self, filename):
        with open(filename, 'w') as fp:
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

    Returns a RequakeCatalog object.
    """
    arguments = locals()
    query = 'query?format=text&nodata=404&'
    for key, val in arguments.items():
        if key in ['baseurl']:
            continue
        if val is None:
            continue
        query += '{}={}&'.format(key, val)
    # remove last "&" symbol
    query = query[:-1]
    # see if baseurl is an alias defined in ObsPy
    try:
        baseurl = URL_MAPPINGS[baseurl]
    except KeyError:
        pass
    baseurl = baseurl + '/fdsnws/event/1/'
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

    Returns a RequakeCatalog object.
    """
    cat = RequakeCatalog()
    for line in open(filename, 'r'):
        if not line:
            continue
        if line[0] == '#':
            continue
        ev = RequakeEvent()
        ev.from_fdsn_text(line)
        cat.append(ev)
    return cat
