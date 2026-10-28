# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``list`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import argparse
from .common import (
    add_group, parent_print_format, set_action
)


def _add_hidden_no_pager(parser):
    """
    Print plain tables only, accepting the old ``--no-pager`` option.

    The pager is meant for the long tables of the ``print`` commands;
    the ``list`` commands always print plain text.  The option is kept,
    hidden from the help, so that the command lines already in use keep
    working.
    """
    parser.add_argument(
        '--no-pager', action='store_true', default=True,
        help=argparse.SUPPRESS
    )


def _add_catalogs_leaf(leaves, name, help_text):
    """Add the leaf that lists the stored catalogs."""
    parser = leaves.add_parser(
        name, parents=[parent_print_format(pager=False)], help=help_text
    )
    _add_hidden_no_pager(parser)
    parser.add_argument(
        'catalog_id', type=int, default=None, nargs='?',
        metavar='CATALOG_ID',
        help='show the details of this catalog id'
    )
    set_action(parser, 'print_catalogs')
    return parser


def _add_scans_leaf(leaves, name, help_text):
    """Add the leaf that lists the stored catalog scans."""
    parser = leaves.add_parser(
        name, parents=[parent_print_format(pager=False)], help=help_text
    )
    _add_hidden_no_pager(parser)
    parser.add_argument(
        'scan_id', type=int, default=None, nargs='?', metavar='SCAN_ID',
        help='show the details of this scan id'
    )
    set_action(parser, 'print_scans')
    return parser


def _add_builds_leaf(leaves, name, help_text):
    """Add the leaf that lists the stored family builds."""
    parser = leaves.add_parser(
        name, parents=[parent_print_format(pager=False)], help=help_text
    )
    _add_hidden_no_pager(parser)
    parser.add_argument(
        'build_id', type=int, default=None, nargs='?', metavar='BUILD_ID',
        help='show the details of this family build id'
    )
    set_action(parser, 'print_family_builds')
    return parser


def add_to(subparsers):
    """Add the "list" group to the command line."""
    group, leaves = add_group(
        subparsers, 'list', 'list the entries stored in the output database'
    )
    _add_catalogs_leaf(
        leaves, 'catalogs', 'list the catalogs stored in the database'
    )
    _add_scans_leaf(
        leaves, 'scans', 'list the catalog scans stored in the database'
    )
    _add_builds_leaf(
        leaves, 'builds', 'list the family builds stored in the database'
    )
    return group
