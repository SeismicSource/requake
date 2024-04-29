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
import sys
import os
import csv
import contextlib
import logging
from tabulate import tabulate
from .pairs import read_pairs_file
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_pairs(config):
    """
    Print pairs to screen.

    :param config: Configuration object.
    :type config: config.Config
    """
    cc_min = config.args.cc_min if config.args.cc_min is not None else -1e99
    cc_max = config.args.cc_max if config.args.cc_max is not None else 1e99
    try:
        pairs = [
            pair for pair in read_pairs_file(config)
            if cc_min <= pair.cc_max <= cc_max
        ]
    except FileNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)

    headers = [
        'evid1',
        'evid2',
        'trace id',
        'origin time1',
        'lon1',
        'lat1',
        'depth1\n(km)',
        'mag1\ntype',
        'mag1',
        'origin time2',
        'lon2',
        'lat2',
        'depth2\n(km)',
        'mag2\ntype',
        'mag2',
        'lag\n(samp)',
        'lag\n(sec)',
        'cc\nmax'
    ]
    table = []
    tablefmt = config.args.format
    if tablefmt == 'csv':
        writer = csv.writer(sys.stdout)
        # replace newlines with spaces in headers
        headers = [h.replace('\n', ' ') for h in headers]
        writer.writerow(headers)
    elif tablefmt == 'markdown':
        headers = [h.replace('\n', '<br>') for h in headers]
    for pair in pairs:
        row = [
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
        table.append(row)
    if tablefmt == 'csv':
        try:
            writer.writerows(table)
        except BrokenPipeError:
            # Redirect remaining output to devnull to avoid another
            # BrokenPipeError at shutdown
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
    else:
        format_dict = {
            'simple': 'simple',
            'markdown': 'github'
        }
        tablefmt = format_dict[config.args.format]
        floatfmt = [
            None,
            None,
            None,
            None,
            '.4f',
            '.4f',
            '.3f',
            None,
            '.1f',
            None,
            '.4f',
            '.4f',
            '.3f',
            None,
            '.1f',
            '.1f',
            '.2f',
            '.2f'
        ]
        with contextlib.suppress(BrokenPipeError):
            print(
                tabulate(
                    table, headers=headers,
                    floatfmt=floatfmt, tablefmt=tablefmt
                )
            )
