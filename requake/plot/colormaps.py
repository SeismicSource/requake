# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Colormaps for Requake.


:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import matplotlib as mpl

_SPATIAL_CMAP = 'plasma'

cmaps = {
    'family_number': mpl.cm.get_cmap('tab10'),
    'time': mpl.cm.get_cmap('GnBu'),
    'duration': mpl.cm.get_cmap('viridis'),
    'latitude': mpl.cm.get_cmap(_SPATIAL_CMAP),
    'longitude': mpl.cm.get_cmap(_SPATIAL_CMAP),
    'depth': mpl.cm.get_cmap(_SPATIAL_CMAP),
    'distance_from': mpl.cm.get_cmap(_SPATIAL_CMAP),
    'number_of_events': mpl.cm.get_cmap('Greens'),
    'cumul_moment': mpl.cm.get_cmap('plasma'),
    'cumul_slip': mpl.cm.get_cmap('cividis'),
    'slip_rate': mpl.cm.get_cmap('inferno'),
}
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
