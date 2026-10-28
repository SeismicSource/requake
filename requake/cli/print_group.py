# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``print`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_catalog_id, parent_family_numbers,
    parent_longer_than, parent_min_events, parent_print_format,
    parent_print_pager, parent_scan_id, parent_shorter_than, set_action
)
from .values import hide_aliases


def _add_catalog_leaf(leaves, name, help_text):
    """Add the leaf that prints the event catalog."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_print_format(), parent_print_pager(), parent_catalog_id()
        ],
        help=help_text
    )
    set_action(parser, 'print_catalog')
    return parser


def _add_pairs_leaf(leaves, name, help_text):
    """Add the leaf that prints the event pairs."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_print_format(), parent_print_pager(), parent_scan_id()
        ],
        help=help_text
    )
    hide_aliases(
        parser.add_argument(
            '-c', '--cc-min', '--cc_min', type=float, default=None,
            help='minimum cross-correlation coefficient '
                 '(default: %(default)s)'
        ),
        '--cc_min'
    )
    hide_aliases(
        parser.add_argument(
            '-C', '--cc-max', '--cc_max', type=float, default=None,
            help='maximum cross-correlation coefficient '
                 '(default: %(default)s)'
        ),
        '--cc_max'
    )
    parser.add_argument(
        '--include-invalid', action='store_true',
        help='also show pairs flagged as invalid (e.g., pairs involving an '
             'event marked as duplicate), adding an "invalid" column'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='skip the large-dataset warning'
    )
    set_action(parser, 'print_pairs')
    return parser


def _add_families_leaf(leaves, name, help_text):
    """Add the leaf that prints the event families."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_longer_than(), parent_shorter_than(), parent_min_events(),
            parent_family_numbers(), parent_print_format('stats'),
            parent_print_pager(), parent_build_id()
        ],
        help=help_text
    )
    details = parser.add_mutually_exclusive_group()
    details.add_argument(
        '-d', '--detailed', action='store_true',
        help='print detailed information for each family, including a list '
             'of events'
    )
    details.add_argument(
        '-E', '--events', action='store_true',
        help='print one row per event of the selected families, instead '
             'of one row per family; can be combined with -f/--format to '
             'export the event list (e.g., "-f csv")'
    )
    set_action(parser, 'print_families')
    return parser


def add_to(subparsers):
    """Add the "print" group to the command line."""
    group, leaves = add_group(
        subparsers, 'print', 'print data to screen'
    )
    _add_catalog_leaf(leaves, 'catalog', 'print the event catalog to screen')
    _add_pairs_leaf(leaves, 'pairs', 'print the event pairs to screen')
    _add_families_leaf(
        leaves, 'families', 'print the event families to screen'
    )
    return group
