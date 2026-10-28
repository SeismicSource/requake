# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``scan`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_build_id, parent_family_numbers, parent_label,
    parent_longer_than, parent_min_events, parent_scan_id,
    parent_shorter_than, parent_traceid, set_action
)
from .values import hide_aliases, nonnegative_int


def _add_catalog_leaf(leaves, name, help_text):
    """Add the leaf that scans a catalog for event pairs."""
    parser = leaves.add_parser(
        name, parents=[parent_scan_id(), parent_label()], help=help_text
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '-f', '--force', action='store_true',
        help='delete existing event pairs and restart the scan'
    )
    hide_aliases(
        mode.add_argument(
            '-r', '--resume', '-c', '--force-continue',
            dest='force_continue', action='store_true',
            help='continue an interrupted scan and keep existing event pairs'
        ),
        '-c', '--force-continue'
    )
    parser.add_argument(
        '--nprocs', type=nonnegative_int, default=None,
        help='number of worker processes for the catalog scan '
             '(0: auto, 1: disable parallelism)'
    )
    set_action(parser, 'scan_catalog')
    return parser


def _add_templates_leaf(leaves, name, help_text):
    """Add the leaf that scans a waveform stream with templates."""
    parser = leaves.add_parser(
        name,
        parents=[
            parent_longer_than(), parent_shorter_than(), parent_min_events(),
            parent_family_numbers(), parent_traceid(), parent_build_id()
        ],
        help=help_text
    )
    hide_aliases(
        parser.add_argument(
            '-T', '--template-file', '--template_file', type=str,
            default=None, metavar='FILE',
            help='use the provided file as template. '
                 'File must be in SAC format, with a P pick in the '
                 '"A" header field'
        ),
        '--template_file'
    )
    set_action(parser, 'scan_templates')
    return parser


def add_to(subparsers):
    """Add the "scan" group to the command line."""
    group, leaves = add_group(
        subparsers, 'scan',
        'search data already in the output database or new waveforms'
    )
    _add_catalog_leaf(
        leaves, 'catalog', 'scan an existing catalog for earthquake pairs'
    )
    _add_templates_leaf(
        leaves, 'templates',
        'scan a continuous waveform stream using one or more templates'
    )
    return group
