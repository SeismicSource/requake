#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Print families to screen.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import numpy as np
from .families import read_selected_families
from .rq_setup import rq_exit
from .slip import mag_to_slip_in_cm


def print_families(config):
    try:
        families = read_selected_families(config)
    except Exception as msg:
        logger.error(msg)
        rq_exit(1)

    header = '#n nev     lon      lat   depth '
    header += '                 start_time                    end_time  yrs'
    header += ' cm/y'
    print(header)
    for family in families:
        family_str = str(family)
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        cum_slip = np.cumsum(slip)
        d_slip = cum_slip[-1] - cum_slip[0]
        slip_rate = d_slip/family.duration
        family_str += ' {:4.1f}'.format(slip_rate)
        print(family_str)
