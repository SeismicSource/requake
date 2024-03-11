# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build waveform templates for one or more event families.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
from .families import (
    FamilyNotFoundError,
    read_selected_families,
    get_family_aligned_waveforms_and_template)
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _build_template(config, family):
    try:
        st = get_family_aligned_waveforms_and_template(config, family)
    except Exception as m:
        logger.error(str(m))
        return
    tr_template = [tr for tr in st if 'average' in tr.stats.evid][0]
    os.makedirs(config.template_dir, exist_ok=True)
    template_file = f'template{family.number:02d}.{tr_template.id}.sac'
    template_file = os.path.join(config.template_dir, template_file)
    tr_template.stats.sac = {
        'kevnm': tr_template.stats.evid,
        'stla': tr_template.stats.coords['latitude'],
        'stlo': tr_template.stats.coords['longitude'],
        'stel': tr_template.stats.coords['elevation'],
        'evla': tr_template.stats.ev_lat,
        'evlo': tr_template.stats.ev_lon,
        'evdp': tr_template.stats.ev_depth,
        'a': tr_template.stats.P_arrival_time - tr_template.stats.starttime,
        'ka': 'Ptheo',
        't0': tr_template.stats.S_arrival_time - tr_template.stats.starttime,
        'kt0': 'Stheo',
    }
    tr_template.write(template_file, format='SAC')
    logger.info(
        f'Template for family {family.number} saved as {template_file}')


def build_templates(config):
    """
    Build waveform templates for one or more event families.

    :param config: requake configuration object
    :type config: config.Config
    """
    try:
        families = read_selected_families(config)
    except FamilyNotFoundError as m:
        logger.error(str(m))
        rq_exit(1)
    for family in families:
        try:
            _build_template(config, family)
        except Exception as m:
            logger.error(str(m))
            continue
