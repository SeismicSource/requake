# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print families to screen.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import csv
import logging
import numpy as np
from tabulate import tabulate
from .families import FamilyNotFoundError, read_selected_families
from ..config.rq_setup import rq_exit
from ..formulas.slip import mag_to_slip_in_cm
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_families(config):
    """
    Print families to screen.

    :param config: Configuration object.
    :type config: config.Config
    """
    try:
        families = read_selected_families(config)
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)

    headers = [
        'family',
        'nevents',
        'longitude',
        'latitude',
        'depth (km)',
        'start time',
        'end time',
        'duration (y)',
        'slip rate (cm/y)'
    ]
    table = []
    tablefmt = config.args.format
    if tablefmt == 'csv':
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
    for family in families:
        row = [
            family.number,
            len(family),
            family.lon,
            family.lat,
            family.depth,
            family.starttime,
            family.endtime,
            family.duration
        ]
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        cum_slip = np.cumsum(slip)
        d_slip = cum_slip[-1] - cum_slip[0]
        slip_rate = d_slip/family.duration
        row.append(slip_rate)
        table.append(row)
    if tablefmt == 'csv':
        writer.writerows(table)
    else:
        format_dict = {
            'simple': 'simple',
            'markdown': 'github'
        }
        tablefmt = format_dict[config.args.format]
        floatfmt = [
            None,
            None,
            '.4f',
            '.4f',
            '.3f',
            None,
            None,
            '.2f',
            '.1f'
        ]
        print(
            tabulate(
                table, headers=headers, floatfmt=floatfmt, tablefmt=tablefmt)
        )
