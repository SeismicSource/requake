# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``read`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import (
    add_group, parent_catalog_id, parent_force, parent_label, set_action
)
from .help_format import NewlineHelpFormatter

_CATALOG_FILE_HELP = (
    'Specifies the event catalog file to be used. If not provided, '
    'the event catalog will be downloaded from the FDSN web service '
    'configured in the control file.\n\n'
    'Acceptable catalog file formats are:\n'
    '- FDSN text\n'
    '- QuakeML\n'
    '- CSV\n'
    '- Space-separated text files.\n\n'
    'For CSV or space-separated formats, the file must include '
    "at least one column for the event's origin time "
    'and may contain additional columns for event ID, longitude, '
    'latitude, depth, and magnitude. Column names '
    'must be specified in the first row.\n\n'
    'Requake attempts to automatically identify the type of each '
    'column based on its name. If it fails to do so, '
    'the code will exit with an error.'
)


def _add_catalog_leaf(leaves, name, help_text):
    """Add the leaf that reads an event catalog."""
    parser = leaves.add_parser(
        name,
        parents=[parent_force(), parent_catalog_id(), parent_label()],
        help=help_text, formatter_class=NewlineHelpFormatter
    )
    parser.add_argument('catalog_file', nargs='?', help=_CATALOG_FILE_HELP)
    parser.add_argument(
        '-a', '--append', action='store_true',
        help='append events to existing catalog'
    )
    set_action(parser, 'read_catalog')
    return parser


def add_to(subparsers):
    """Add the "read" group to the command line."""
    group, leaves = add_group(
        subparsers, 'read', 'read a data set into the output database'
    )
    _add_catalog_leaf(
        leaves, 'catalog',
        'read an event catalog from web services or from a file'
    )
    return group
