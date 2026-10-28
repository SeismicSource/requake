# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``plot`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_catalog_id, parent_color_by,
    parent_color_range, parent_colormap, parent_family_numbers,
    parent_freq_band, parent_longer_than, parent_min_events, parent_output,
    parent_shorter_than, parent_traceid, set_action
)
from .values import hide_aliases

# Parents shared by the family plots
_PLOT_PARENTS = [
    parent_longer_than, parent_shorter_than, parent_min_events,
    parent_family_numbers, parent_build_id
]


def _family_parents(*extra_parents):
    """Return the parents shared by the family plots, plus some others."""
    return [parent() for parent in _PLOT_PARENTS + list(extra_parents)]


def _add_pair_leaf(leaves, name, help_text):
    """Add the leaf that plots one event pair."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_traceid(), parent_freq_band(), parent_output(),
            parent_catalog_id()
        ],
        help=help_text
    )
    parser.add_argument('evid1')
    parser.add_argument('evid2')
    set_action(parser, 'plot_pair')
    return parser


def _add_families_leaf(leaves, name, help_text):
    """Add the leaf that plots the traces of the families."""
    parser = leaves.add_parser(
        name,
        parents=_family_parents(
            parent_traceid, parent_freq_band, parent_output
        ),
        help=help_text
    )
    hide_aliases(
        parser.add_argument(
            '-s', '--start-time', '--starttime', dest='starttime',
            type=float, default=None,
            help='start time, in seconds relative to trace start, '
                 'for the plot'
        ),
        '--starttime'
    )
    hide_aliases(
        parser.add_argument(
            '-e', '--end-time', '--endtime', dest='endtime', type=float,
            default=None,
            help='end time, in seconds relative to trace start, '
                 'for the plot'
        ),
        '--endtime'
    )
    parser.add_argument(
        '-T', '--template', action='store_true',
        help='plot family members found with template scan'
    )
    parser.add_argument(
        '--mode', type=str, default='wiggle',
        choices=['wiggle', 'heatmap'],
        help='plot mode. "wiggle" draws one trace per event, as a line; '
             '"heatmap" draws the traces as an image, one row per event, '
             'with the normalized amplitude encoded in color. '
             'Default: %(default)s'
    )
    parser.add_argument(
        '--max-labels', type=int, default=None, metavar='NLABELS',
        help='maximum number of traces carrying a label; when a family has '
             'more traces than this, only a subset of them is labeled, at '
             'a regular interval. In "wiggle" mode, the labeled traces are '
             'also highlighted, the other traces are drawn lighter, and '
             'the trace amplitude is scaled with the number of events. '
             'Use 0 to label every trace (default: 15)'
    )
    set_action(parser, 'plot_families')
    return parser


def _add_timespans_leaf(leaves, name, help_text):
    """Add the leaf that plots the family timespans."""
    parser = leaves.add_parser(
        name,
        parents=_family_parents(
            parent_color_by, parent_colormap, parent_color_range,
            parent_output
        ),
        help=help_text
    )
    hide_aliases(
        parser.add_argument(
            '-s', '--sort-by', '--sortby', dest='sortby', type=str,
            default='family_number', metavar='QUANTITY',
            choices=[
                'time', 'latitude', 'longitude', 'depth', 'distance_from',
                'family_number'
            ],
            help='quantity to sort families by on y-axis. Choose among '
                 '{%(choices)s}. Default: %(default)s'
        ),
        '--sortby'
    )
    set_action(parser, 'plot_timespans')
    return parser


def _add_cumulative_leaf(leaves, name, help_text):
    """Add the leaf that plots the cumulative quantities of the families."""
    parser = leaves.add_parser(
        name,
        parents=_family_parents(
            parent_color_by, parent_colormap, parent_color_range,
            parent_output
        ),
        help=help_text
    )
    parser.add_argument(
        '-q', '--quantity', type=str, default='slip',
        metavar='QUANTITY',
        choices=['slip', 'moment', 'number'],
        help='cumulative quantity to plot on y-axis. Choose among '
             '{%(choices)s}. Default: %(default)s'
    )
    hide_aliases(
        parser.add_argument(
            '-L', '--log-scale', '--logscale', dest='logscale',
            action='store_true',
            help='use log scale for y-axis'
        ),
        '--logscale'
    )
    set_action(parser, 'plot_cumulative')
    return parser


def _add_map_leaf(leaves, name, help_text):
    """Add the leaf that plots the families on a map."""
    parser = leaves.add_parser(
        name,
        parents=_family_parents(
            parent_color_by, parent_colormap, parent_color_range,
            parent_output
        ),
        help=help_text
    )
    parser.add_argument(
        '-b', '--backend', type=str, default='cartopy',
        choices=['cartopy', 'folium'],
        help='map backend (default: %(default)s). The "folium" backend '
             'produces an interactive HTML map and requires the optional '
             '"folium" package; use "-o html" or an output filename '
             'ending in ".html" to save the map to a file'
    )
    hide_aliases(
        parser.add_argument(
            '-s', '--size-by', '--sizeby', dest='sizeby', type=str,
            default='number_of_events', metavar='QUANTITY',
            choices=[
                'number_of_events', 'duration', 'depth', 'latitude',
                'longitude', 'distance_from', 'cumul_moment', 'cumul_slip',
                'slip_rate'
            ],
            help='quantity to scale the family marker size by. Choose among '
                 '{%(choices)s} (default: %(default)s). A logarithmic scale '
                 'is used when the values span more than one order of '
                 'magnitude'
        ),
        '--sizeby'
    )
    hide_aliases(
        parser.add_argument(
            '-M', '--map-style', '--mapstyle', dest='mapstyle', type=str,
            default='satellite', metavar='STYLE',
            choices=[
                'stamen_terrain', 'satellite', 'street', 'hillshade',
                'hillshade_dark', 'ocean'
            ],
            help='style of map to plot. Choose among {%(choices)s} '
                 '(default: %(default)s)'
        ),
        '--mapstyle'
    )
    hide_aliases(
        parser.add_argument(
            '-k', '--api-key', '--apikey', dest='apikey', type=str,
            default=None,
            help='API key for Stamen Terrain map tiles '
                 '(default: %(default)s). '
                 'You can get a free API key at https://stadiamaps.com/'
        ),
        '--apikey'
    )
    parser.add_argument(
        '-z', '--zoom', type=int, default=None,
        help='zoom level for the map tiles (default: None). Note that '
             'certain map tiles might not be available at all zoom levels. '
             'For the folium backend, this sets the initial zoom level of '
             'the map, instead of fitting the map to the families'
    )
    set_action(parser, 'map_families')
    return parser


def add_to(subparsers):
    """Add the "plot" group to the command line."""
    group, leaves = add_group(
        subparsers, 'plot', 'plot data to screen or file'
    )
    _add_pair_leaf(leaves, 'pair', 'plot traces for a given event pair')
    _add_families_leaf(
        leaves, 'families', 'plot traces for one or more event families'
    )
    _add_timespans_leaf(leaves, 'timespans', 'plot family timespans')
    _add_cumulative_leaf(
        leaves, 'cumulative', 'cumulative plot for one or more families'
    )
    _add_map_leaf(leaves, 'map', 'plot families on a map')
    return group
