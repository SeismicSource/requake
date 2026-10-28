# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``delete`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_dry_run, parent_force, set_action
)


def _add_catalog_leaf(leaves, name, help_text):
    """Add the leaf that deletes a catalog."""
    parser = leaves.add_parser(
        name, parents=[parent_force(), parent_dry_run()], help=help_text
    )
    parser.add_argument(
        'catalog_id', type=int, metavar='CATALOG_ID',
        help='catalog id to delete'
    )
    set_action(parser, 'delete_catalog')
    return parser


def _add_scan_leaf(leaves, name, help_text):
    """Add the leaf that deletes a catalog scan."""
    parser = leaves.add_parser(
        name, parents=[parent_force(), parent_dry_run()], help=help_text
    )
    parser.add_argument(
        'scan_id', type=int, metavar='SCAN_ID',
        help='scan id to delete'
    )
    set_action(parser, 'delete_scan')
    return parser


def _add_build_leaf(leaves, name, help_text):
    """Add the leaf that deletes a family build."""
    parser = leaves.add_parser(
        name, parents=[parent_force(), parent_dry_run()], help=help_text
    )
    parser.add_argument(
        'build_id', type=int, metavar='BUILD_ID',
        help='family build id to delete'
    )
    set_action(parser, 'delete_build')
    return parser


def add_to(subparsers):
    """Add the "delete" group to the command line."""
    group, leaves = add_group(
        subparsers, 'delete',
        'delete a catalog, a catalog scan or a family build'
    )
    _add_catalog_leaf(
        leaves, 'catalog', 'delete a catalog and everything built from it'
    )
    _add_scan_leaf(
        leaves, 'scan', 'delete a catalog scan and everything built from it'
    )
    _add_build_leaf(
        leaves, 'build',
        'delete a family build and its families and template detections'
    )
    return group
