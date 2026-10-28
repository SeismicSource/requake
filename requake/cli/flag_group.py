# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``flag`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_dry_run, parent_scan_id, set_action
)
from .values import hide_aliases


def _add_family_leaf(leaves, name, help_text):
    """Add the leaf that flags a family as valid or not valid."""
    parser = leaves.add_parser(
        name, parents=[parent_build_id()], help=help_text
    )
    parser.add_argument('family_number')
    parser.add_argument(
        'is_valid',
        help='"true" (or "t") to flag family as valid, '
             '"false" (or "f") to flag family as not valid'
    )
    set_action(parser, 'flag_family')
    return parser


def _add_duplicates_leaf(leaves, name, help_text):
    """Add the leaf that flags duplicate events."""
    parser = leaves.add_parser(
        name, parents=[parent_scan_id(), parent_dry_run()], help=help_text
    )
    hide_aliases(
        parser.add_argument(
            '-c', '--cc-min', '--cc_min', type=float, default=0.98,
            help='minimum cross-correlation coefficient for two events to be '
                 'considered duplicates (default: %(default)s)'
        ),
        '--cc_min'
    )
    parser.add_argument(
        '-t', '--max-time-diff',
        type=float, default=60., metavar='SECONDS',
        help='maximum origin-time difference for two events to be '
             'considered duplicates (default: %(default)s s)'
    )
    parser.add_argument(
        '-d', '--max-distance',
        type=float, default=2., metavar='KM',
        help='maximum horizontal distance for two events to be '
             'considered duplicates (default: %(default)s km)'
    )
    parser.add_argument(
        '--reset', action='store_true',
        help='reset the duplicate and invalid flags and exit, without '
             'performing duplicate detection'
    )
    set_action(parser, 'dedup_events')
    return parser


def add_to(subparsers):
    """Add the "flag" group to the command line."""
    group, leaves = add_group(
        subparsers, 'flag', 'flag entries of the output database'
    )
    _add_family_leaf(
        leaves, 'family',
        'flag a family of repeating earthquakes as valid or not valid'
    )
    _add_duplicates_leaf(
        leaves, 'duplicates',
        'detect and flag duplicate events in the catalog from close '
        'event pairs'
    )
    return group
