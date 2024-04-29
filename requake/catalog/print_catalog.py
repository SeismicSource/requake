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
import logging
from .catalog import read_stored_catalog
from ..config.generic_printer import generic_printer
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

    headers_fmt = [
        ('evid', None),
        ('origin time', None),
        ('longitude', '.4f'),
        ('latitude', '.4f'),
        ('depth\n(km)', '.3f'),
        ('mag\ntype', None),
        ('mag', '.1f')
    ]
    rows = [
        [
            ev.evid,
            ev.orig_time,
            ev.lon,
            ev.lat,
            ev.depth,
            ev.mag_type,
            ev.mag
        ]
        for ev in catalog
    ]
    generic_printer(config, rows, headers_fmt)
