# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print the event catalog to screen.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import csv
import logging
from tabulate import tabulate
from .catalog import read_stored_catalog
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_catalog(config):
    """
    Print the event catalog to screen.

    :param config: Configuration object.
    :type config: config.Config
    """
    try:
        catalog = read_stored_catalog(config)
    except (ValueError, FileNotFoundError) as m:
        logger.error(m)
        rq_exit(1)

    headers = [
        'evid',
        'origin time',
        'longitude',
        'latitude',
        'depth (km)',
        'mag type',
        'mag',
    ]
    table = []
    tablefmt = config.args.format
    if tablefmt == 'csv':
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
    for ev in catalog:
        row = [
            ev.evid,
            ev.orig_time,
            ev.lon,
            ev.lat,
            ev.depth,
            ev.mag_type,
            ev.mag
        ]
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
            '.1f'
        ]
        print(
            tabulate(
                table, headers=headers, floatfmt=floatfmt, tablefmt=tablefmt)
        )
