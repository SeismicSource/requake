# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
from obspy import UTCDateTime
from ..formulas.conversion import float_or_none
from ..catalog.catalog import RequakeEvent
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class RequakeEventPair:
    """
    A pair of events.
    """
    def __init__(self, event1, event2, trace_id, lag_samples, lag_sec, cc_max):
        """
        Initialize a pair of events.

        :param event1: first event
        :type event1: RequakeEvent
        :param event2: second event
        :type event2: RequakeEvent
        :param lag_samples: lag in samples
        :type lag_samples: int
        :param lag_sec: lag in seconds
        :type lag_sec: float
        :param cc_max: maximum cross-correlation coefficient
        :type cc_max: float
        """
        if not isinstance(event1, RequakeEvent):
            raise TypeError('event1 must be a RequakeEvent')
        if not isinstance(event2, RequakeEvent):
            raise TypeError('event2 must be a RequakeEvent')
        if not isinstance(trace_id, str):
            raise TypeError('trace_id must be a string')
        if not isinstance(lag_samples, (int, float)):
            raise TypeError('lag_samples must be a number')
        if not isinstance(lag_sec, (int, float)):
            raise TypeError('lag_sec must be a number')
        if not isinstance(cc_max, (int, float)):
            raise TypeError('cc_max must be a number')
        self.event1 = event1
        self.event2 = event2
        self.trace_id = trace_id
        self.lag_samples = lag_samples
        self.lag_sec = lag_sec
        self.cc_max = cc_max

    def __repr__(self):
        return (
            f'RequakeEventPair(event1={self.event1}, event2={self.event2}, '
            f'trace_id={self.trace_id}, '
            f'lag_samples={self.lag_samples}, lag_sec={self.lag_sec}, '
            f'cc_max={self.cc_max})'
        )

    def __str__(self):
        return (
            f'RequakeEventPair: {self.event1.evid} - {self.event2.evid}, '
            f'trace_id={self.trace_id}, '
            f'cc_max={self.cc_max}, lag_samples={self.lag_samples}, '
            f'lag_sec={self.lag_sec}'
        )


def read_pairs_file(config):
    """
    Read pairs file. Generate a RequakeEventPair object for each row.

    :param config: configuration object
    :type config: config.Config
    :return: generator of RequakeEventPair objects
    :rtype: generator

    :raises FileNotFoundError: if the pairs file is not found
    """
    with open(config.scan_catalog_pairs_file, 'r', encoding='utf8') as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            evid1 = row['evid1']
            ev1 = RequakeEvent(
                evid=evid1,
                orig_time=UTCDateTime(row['orig_time1']),
                lon=float_or_none(row['lon1']),
                lat=float_or_none(row['lat1']),
                depth=float_or_none(row['depth_km1']),
                mag_type=row['mag_type1'],
                mag=float_or_none(row['mag1']),
                trace_id=row['trace_id']
            )
            evid2 = row['evid2']
            ev2 = RequakeEvent(
                evid=evid2,
                orig_time=UTCDateTime(row['orig_time2']),
                lon=float_or_none(row['lon2']),
                lat=float_or_none(row['lat2']),
                depth=float_or_none(row['depth_km2']),
                mag_type=row['mag_type2'],
                mag=float_or_none(row['mag2']),
                trace_id=row['trace_id']
            )
            trace_id = row['trace_id']
            lag_samples = float(row['lag_samples'])
            lag_sec = float(row['lag_sec'])
            cc_max = float(row['cc_max'])
            yield RequakeEventPair(
                ev1, ev2, trace_id, lag_samples, lag_sec, cc_max)


def read_events_from_pairs_file(config):
    """
    Read events from pairs file.

    :param config: configuration object
    :type config: config.Config
    :return: dictionary of events
    :rtype: dict

    :raises FileNotFoundError: if the pairs file is not found
    """
    events = {}
    for pair in read_pairs_file(config):
        evid1 = pair.event1.evid
        try:
            ev1 = events[evid1]
        except KeyError:
            ev1 = pair.event1
            events[evid1] = ev1
        evid2 = pair.event2.evid
        try:
            ev2 = events[evid2]
        except KeyError:
            ev2 = pair.event2
            events[evid2] = ev2
        # Store the correlation between the two events in both events
        ev1.correlations[ev2.evid] = ev2.correlations[ev1.evid] = pair.cc_max
    return events
