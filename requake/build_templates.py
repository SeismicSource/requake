#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Build waveform templates for one or more event families.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import os
from .families import (
    build_family_number_list, read_families, get_family,
    get_family_aligned_waveforms_and_template)
from .rq_setup import rq_exit


def _build_template(config, family):
    try:
        st = get_family_aligned_waveforms_and_template(config, family)
    except Exception as m:
        logger.error(str(m))
        return
    tr_template = [tr for tr in st if 'average' in tr.stats.evid][0]
    os.makedirs(config.template_dir, exist_ok=True)
    template_file = 'template{:02d}.{}.sac'.format(
        family.number, tr_template.id
    )
    template_file = os.path.join(config.template_dir, template_file)
    tr_template.stats.sac = dict(
        kevnm=tr_template.stats.evid,
        stla=tr_template.stats.coords['latitude'],
        stlo=tr_template.stats.coords['longitude'],
        stel=tr_template.stats.coords['elevation'],
        evla=tr_template.stats.ev_lat,
        evlo=tr_template.stats.ev_lon,
        evdp=tr_template.stats.ev_depth,
        a=tr_template.stats.P_arrival_time - tr_template.stats.starttime,
        ka='Ptheo',
        t0=tr_template.stats.S_arrival_time - tr_template.stats.starttime,
        kt0='Stheo',
    )
    tr_template.write(template_file, format='SAC')
    logger.info('Template for family {} saved as {}'.format(
        family.number, template_file
    ))


def build_templates(config):
    try:
        family_numbers = build_family_number_list(config)
        families = read_families(config)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)
    for family_number in family_numbers:
        try:
            family = get_family(config, families, family_number)
            _build_template(config, family)
        except Exception as m:
            logger.error(str(m))
            continue
