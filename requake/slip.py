# -*- coding: utf8 -*-
"""
Functions to compute slip for repeaters.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging

logger = logging.getLogger(__name__.split('.')[-1])


def _mag_to_moment(magnitude, unit='N.m'):
    if unit == 'N.m':
        Mo = 10**(3/2*(magnitude+6.07))
    elif unit == 'dyne.cm':
        Mo = 10**(3/2*(magnitude+10.7))
    else:
        raise ValueError(f'Wrong unit for seismic moment: {unit}')
    return Mo


def mag_to_slip_in_cm(config, magnitude):
    Mo = _mag_to_moment(magnitude, unit='dyne.cm')
    # TODO: add other laws via config parameter
    # Nadeau and Johnson (1998)
    return (10**(-2.36))*(Mo**(0.17))
