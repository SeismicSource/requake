# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``build`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_family_numbers, parent_force,
    parent_label, parent_longer_than, parent_min_events, parent_scan_id,
    parent_shorter_than, parent_traceid, set_action
)


def _add_families_leaf(leaves, name, help_text):
    """Add the leaf that builds event families from the pairs."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_force(), parent_scan_id(), parent_build_id(),
            parent_label()
        ],
        help=help_text
    )
    set_action(parser, 'build_families')
    return parser


def _add_templates_leaf(leaves, name, help_text):
    """Add the leaf that builds waveform templates."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_longer_than(), parent_shorter_than(), parent_min_events(),
            parent_family_numbers(), parent_traceid(), parent_build_id()
        ],
        help=help_text
    )
    set_action(parser, 'build_templates')
    return parser


def add_to(subparsers):
    """Add the "build" group to the command line."""
    group, leaves = add_group(
        subparsers, 'build', 'build derived data from the output database'
    )
    _add_families_leaf(
        leaves, 'families',
        'build families of repeating earthquakes from a catalog of pairs'
    )
    _add_templates_leaf(
        leaves, 'templates',
        'build waveform templates for one or more event families'
    )
    return group
