# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print pairs to screen.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit, generic_printer
from ..database.db import DatabaseCorruptError
from ..database.pairs import PairsTableNotFoundError, read_pairs
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_pairs():
    """Print pairs to screen."""
    headers_fmt = [
        ('evid1', None),
        ('evid2', None),
        ('trace id', None),
        ('origin time1', None),
        ('lon1', '.4f'),
        ('lat1', '.4f'),
        ('depth1\n(km)', '.3f'),
        ('mag1\ntype', None),
        ('mag1', '.1f'),
        ('origin time2', None),
        ('lon2', '.4f'),
        ('lat2', '.4f'),
        ('depth2\n(km)', '.3f'),
        ('mag2\ntype', None),
        ('mag2', '.1f'),
        ('lag\n(samp)', '.1f'),
        ('lag\n(sec)', '.2f'),
        ('cc\nmax', '.2f')
    ]
    cc_min = config.args.cc_min
    cc_max = config.args.cc_max
    try:
        print_headers = True
        for pair in read_pairs(config, cc_min=cc_min, cc_max=cc_max):
            rows = [
                [
                    pair.event1.evid,
                    pair.event2.evid,
                    pair.trace_id,
                    pair.event1.orig_time,
                    pair.event1.lon,
                    pair.event1.lat,
                    pair.event1.depth,
                    pair.event1.mag_type,
                    pair.event1.mag,
                    pair.event2.orig_time,
                    pair.event2.lon,
                    pair.event2.lat,
                    pair.event2.depth,
                    pair.event2.mag_type,
                    pair.event2.mag,
                    pair.lag_samples,
                    pair.lag_sec,
                    pair.cc_max
                ]
            ]
            generic_printer(rows, headers_fmt, print_headers)
            print_headers = False
    except (FileNotFoundError, PairsTableNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    except DatabaseCorruptError as msg:
        logger.error(msg)
        rq_exit(1)
