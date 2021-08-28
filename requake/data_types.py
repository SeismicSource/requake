#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Data types for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""


class RequakeEvent():
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


