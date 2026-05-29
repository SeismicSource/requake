# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build families of repeating earthquakes from a catalog of pairs.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from numbers import Real
from ..catalog import RequakeEvent
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class RequakeEventPair:
    """A pair of events."""

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
        if not isinstance(lag_samples, Real):
            raise TypeError('lag_samples must be a number')
        if not isinstance(lag_sec, Real):
            raise TypeError('lag_sec must be a number')
        if not isinstance(cc_max, Real):
            raise TypeError('cc_max must be a number')
        self.event1 = event1
        self.event2 = event2
        self.trace_id = trace_id
        self.lag_samples = lag_samples
        self.lag_sec = lag_sec
        self.cc_max = cc_max

    def __repr__(self):
        """Return the debug representation of the pair."""
        return (
            f'RequakeEventPair(event1={self.event1}, event2={self.event2}, '
            f'trace_id={self.trace_id}, '
            f'lag_samples={self.lag_samples}, lag_sec={self.lag_sec}, '
            f'cc_max={self.cc_max})'
        )

    def __str__(self):
        """Return a compact string representation of the pair."""
        return (
            f'RequakeEventPair: {self.event1.evid} - {self.event2.evid}, '
            f'trace_id={self.trace_id}, '
            f'cc_max={self.cc_max}, lag_samples={self.lag_samples}, '
            f'lag_sec={self.lag_sec}'
        )


def read_events_from_pairs(cc_min=None, cc_max=None):
    """
    Read events from stored event pairs.

    :param cc_min: If given, only use pairs with cc_max >= cc_min.
    :type cc_min: float or None
    :param cc_max: If given, only use pairs with cc_max <= cc_max.
    :type cc_max: float or None
    :return: dictionary of events
    :rtype: dict

    :raises PairsTableNotFoundError: if the stored pairs table is missing
    """
    from ..database.pairs import read_pairs
    events = {}
    for pair in read_pairs(cc_min=cc_min, cc_max=cc_max):
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
