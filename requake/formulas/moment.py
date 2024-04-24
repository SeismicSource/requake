# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions to compute seismic moment.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def mag_to_moment(magnitude, unit='N.m'):
    """
    Convert magnitude to seismic moment.

    :param magnitude: earthquake magnitude
    :type magnitude: float
    :param unit: unit of the seismic moment, either 'N.m' or 'dyne.cm'
    :type unit: str
    :returns: seismic moment
    :rtype: float
    """
    if magnitude is None:
        return 0
    if unit == 'N.m':
        moment = 10**(3/2*(magnitude+6.07))
    elif unit == 'dyne.cm':
        moment = 10**(3/2*(magnitude+10.7))
    else:
        raise ValueError(f'Wrong unit for seismic moment: {unit}')
    return moment
