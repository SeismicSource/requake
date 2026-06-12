# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Colormaps for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import matplotlib as mpl
from ..config import config, rq_exit

_SPATIAL_CMAP = 'plasma'

cmaps = {
    'family_number': mpl.colormaps['tab10'],
    'time': mpl.colormaps['GnBu'],
    'duration': mpl.colormaps['viridis'],
    'latitude': mpl.colormaps[_SPATIAL_CMAP],
    'longitude': mpl.colormaps[_SPATIAL_CMAP],
    'depth': mpl.colormaps[_SPATIAL_CMAP],
    'distance_from': mpl.colormaps[_SPATIAL_CMAP],
    'number_of_events': mpl.colormaps['Greens'],
    'cumul_moment': mpl.colormaps['plasma'],
    'cumul_slip': mpl.colormaps['cividis'],
    'slip_rate': mpl.colormaps['inferno'],
}
if getattr(config.args, 'colormap', None) is not None:
    try:
        user_cmap = mpl.colormaps[config.args.colormap]
    except KeyError:
        rq_exit(f'Colormap "{config.args.colormap}" not found.')
    for cmap in cmaps:
        cmaps[cmap] = user_cmap.copy()
cmap_labels = {
    'family_number': 'Family Number (last digit)',
    'time': 'Family Start Time',
    'duration': 'Family Duration',
    'latitude': 'Latitude (°N)',
    'longitude': 'Longitude (°E)',
    'depth': 'Depth (km)',
    'distance_from': 'Distance from',
    'number_of_events': 'Number of Events',
    'cumul_moment': 'Cumulative Moment (N·m)',
    'cumul_slip': 'Cumulative Slip (cm)',
    'slip_rate': 'Slip Rate (cm/y)',
}
# add labels as cmap attributes
for cmap, label in cmap_labels.items():
    cmaps[cmap].label = label
