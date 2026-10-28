# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``config`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .common import add_group, set_action


def _add_sample(leaves, name, help_text):
    """Add the leaf that writes a sample config file."""
    parser = leaves.add_parser(name, help=help_text)
    set_action(parser, 'sample_config')
    return parser


def _add_update(leaves, name, help_text):
    """Add the leaf that updates a config file."""
    parser = leaves.add_parser(name, help=help_text)
    parser.add_argument(
        'config_file', default=None, nargs='?',
        help='config file to be updated (default: the file given with '
             '-c/--configfile)'
    )
    set_action(parser, 'update_config')
    return parser


def add_to(subparsers):
    """Add the "config" group to the command line."""
    group, leaves = add_group(
        subparsers, 'config', 'write or update the configuration file'
    )
    _add_sample(
        leaves, 'sample',
        'write a sample config file to the current directory and exit'
    )
    _add_update(
        leaves, 'update',
        'update an existing config file to the latest version'
    )
    return group
