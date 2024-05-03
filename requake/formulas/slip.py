# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions to compute slip for repeaters.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import numpy as np
import logging
from .moment import mag_to_moment
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _nadeau_and_johnson_1998(moment):
    """
    Compute slip from seismic moment using the Nadeau and Johnson (1998) model.

    :param moment: moment in dyne.cm
    :type moment: float
    :returns: slip in cm
    :rtype: float
    """
    return (10**(-2.36))*(moment**(0.17))


def _beeler_et_al_2001(moment, stress_drop, rigidity, strain_hardening):
    """
    Compute slip from seismic moment using the Beeler et al. (2001) model.

    :param moment: moment in N.m
    :type moment: float
    :param stress_drop: stress drop in MPa
    :type stress_drop: float
    :param rigidity: rigidity in GPa
    :type rigidity: float
    :param strain_hardening: strain hardening coefficient in MPa/cm
    :type strain_hardening: float
    :returns: slip in cm
    :rtype: float
    """
    rigidity *= 1e3  # Convert GPa to MPa
    return stress_drop * (
        1/(1.81*rigidity)*(moment/stress_drop)**(1/3) + 1/strain_hardening
    )


def _eshelby_1957(moment, stress_drop, rigidity):
    """
    Compute slip from seismic moment using the Eshelby (1957)
    circular crack model.

    :param moment: moment in N.m
    :type moment: float
    :param stress_drop: stress drop in MPa
    :type stress_drop: float
    :param rigidity: rigidity in GPa
    :type rigidity: float
    :returns: slip in cm
    :rtype: float
    """
    rigidity *= 1e3  # Convert GPa to MPa
    # radius in cm (since stress_drop is in MPa)
    radius = (7/16 * moment/stress_drop)**(1/3)
    # slip in cm (since rigidity is in MPa and radius is in cm)
    return moment/(np.pi*rigidity*radius**2)


def mag_to_slip_in_cm(config, magnitude):
    """
    Convert magnitude to slip in cm.

    :param config: requake configuration object
    :config type: config.Config
    :param magnitude: earthquake magnitude
    :type magnitude: float
    :returns: slip in cm
    :rtype: float

    :raises ValueError: if the magnitude-to-slip law is unknown
    """
    if magnitude is None:
        return 0
    if config.mag_to_slip_model == 'NJ1998':
        moment = mag_to_moment(magnitude, unit='dyne.cm')
        return _nadeau_and_johnson_1998(moment)
    elif config.mag_to_slip_model == 'B2001':
        moment = mag_to_moment(magnitude, unit='N.m')
        stress_drop = config.static_stress_drop
        rigidity = config.rigidity
        strain_hardening = config.strain_hardening
        return _beeler_et_al_2001(
            moment, stress_drop, rigidity, strain_hardening)
    elif config.mag_to_slip_model == 'E1957':
        moment = mag_to_moment(magnitude, unit='N.m')
        stress_drop = config.static_stress_drop
        rigidity = config.rigidity
        return _eshelby_1957(moment, stress_drop, rigidity)
    else:
        raise ValueError(
            f'Unknown magnitude-to-slip model: {config.mag_to_slip_model}')
