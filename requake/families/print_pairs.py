# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print pairs to screen.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from .pairs import read_pairs_file
from ..config.generic_printer import generic_printer
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_pairs(config):
    """
    Print pairs to screen.

    :param config: Configuration object.
    :type config: config.Config
    """
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
    cc_min = config.args.cc_min if config.args.cc_min is not None else -1e99
    cc_max = config.args.cc_max if config.args.cc_max is not None else 1e99
    try:
        print_headers = True
        for pair in read_pairs_file(config):
            if not cc_min <= pair.cc_max <= cc_max:
                continue
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
            generic_printer(config, rows, headers_fmt, print_headers)
            print_headers = False
    except FileNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
