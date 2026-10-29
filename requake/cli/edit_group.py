# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``edit`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_catalog_id, parent_scan_id,
    set_action
)

_LABEL_HELP = 'new label; use an empty string to remove the label'


def _add_label_leaf(leaves, name, help_text, parent_id):
    """Add the leaf that changes the label of a stored entry."""
    parser = leaves.add_parser(
        name, parents=[parent_id], help=help_text
    )
    parser.add_argument('label', help=_LABEL_HELP)
    return parser


def _add_catalog_leaf(leaves, name, help_text):
    """Add the leaf that changes the label of a catalog."""
    parser = _add_label_leaf(
        leaves, name, help_text, parent_catalog_id()
    )
    set_action(parser, 'edit_catalog')
    return parser


def _add_scan_leaf(leaves, name, help_text):
    """Add the leaf that changes the label of a catalog scan."""
    parser = _add_label_leaf(leaves, name, help_text, parent_scan_id())
    set_action(parser, 'edit_scan')
    return parser


def _add_build_leaf(leaves, name, help_text):
    """Add the leaf that changes the label of a family build."""
    parser = _add_label_leaf(leaves, name, help_text, parent_build_id())
    set_action(parser, 'edit_build')
    return parser


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


def add_to(subparsers):
    """Add the "edit" group to the command line."""
    group, leaves = add_group(
        subparsers, 'edit', 'edit entries stored in the output database'
    )
    _add_catalog_leaf(
        leaves, 'catalog', 'change the label of a catalog'
    )
    _add_scan_leaf(
        leaves, 'scan', 'change the label of a catalog scan'
    )
    _add_build_leaf(
        leaves, 'build', 'change the label of a family build'
    )
    _add_family_leaf(
        leaves, 'family',
        'flag a family of repeating earthquakes as valid or not valid'
    )
    return group
