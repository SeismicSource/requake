# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot families on a map.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit
from ..families import FamilyNotFoundError, read_selected_families
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def map_families():
    """Plot families on a map."""
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    backend = config.args.backend
    # backend modules are imported here, since folium is an optional
    # dependency
    # pylint: disable=import-outside-toplevel
    if backend == 'cartopy':
        from .map_families_cartopy import plot_families_map_with_cartopy
        plot_families_map_with_cartopy(families)
        return
    if backend == 'folium':
        from .map_families_folium import plot_families_map_with_folium
        plot_families_map_with_folium(families)
        return
    logger.error(f'Invalid map backend: "{backend}"')
    rq_exit(1)
