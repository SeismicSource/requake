# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The ``wfcache`` command group.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import argparse
from .common import add_group, parent_catalog_id, parent_dry_run, set_action
from .values import nonnegative_int


def _row_filters():
    """Return a parent parser with the waveform-cache row filters."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        '--event-id', action='append', default=[],
        help='event ID filter (repeatable)'
    )
    parser.add_argument(
        '--event-id-file', type=str, default=None,
        help='path to text file with event IDs'
    )
    parser.add_argument(
        '--trace-id', action='append', default=[],
        help='trace-ID filter (repeatable)'
    )
    parser.add_argument(
        '--start-time', type=str, default=None,
        help='minimum start time (UTCDateTime-compatible string)'
    )
    parser.add_argument(
        '--end-time', type=str, default=None,
        help='maximum end time (UTCDateTime-compatible string)'
    )
    parser.add_argument(
        '--limit', type=nonnegative_int, default=None,
        help='limit number of returned rows'
    )
    return parser


def _add_prefetch_leaf(leaves, name, help_text):
    """Add the leaf that prefetches waveform windows."""
    parser = leaves.add_parser(
        name, parents=[parent_catalog_id()], help=help_text
    )
    parser.add_argument(
        '--event-id', action='append', default=[],
        help='event ID filter (repeatable)'
    )
    parser.add_argument(
        '--event-id-file', type=str, default=None,
        help='path to text file with event IDs'
    )
    parser.add_argument(
        '--trace-id', action='append', default=[],
        help='trace-ID filter (repeatable)'
    )
    parser.add_argument(
        '--max-events', type=nonnegative_int, default=None,
        help='maximum number of catalog events to prefetch'
    )
    parser.add_argument(
        '--batch-size', type=nonnegative_int, default=500,
        help='progress logging batch size (default: %(default)s)'
    )
    parser.add_argument(
        '--group-window', type=str, default='1h', metavar='DURATION',
        help='max grouped download span (e.g., 30m, 1h; default: '
             '%(default)s)'
    )
    set_action(parser, 'wfcache_prefetch')
    return parser


def _add_print_leaf(leaves, name, help_text):
    """Add the leaf that prints the cached rows."""
    parser = leaves.add_parser(
        name, parents=[_row_filters()], help=help_text
    )
    parser.add_argument(
        '--json', action='store_true', help='print rows as JSON'
    )
    set_action(parser, 'wfcache_print')
    return parser


def _add_inspect_leaf(leaves, name, help_text):
    """Add the leaf that summarises the waveform cache."""
    parser = leaves.add_parser(name, help=help_text)
    parser.add_argument(
        '--integrity', action='store_true', help='run PRAGMA integrity_check'
    )
    parser.add_argument(
        '--json', action='store_true', help='print summary as JSON'
    )
    set_action(parser, 'wfcache_inspect')
    return parser


def _add_extract_leaf(leaves, name, help_text):
    """Add the leaf that extracts the cached waveforms to files."""
    parser = leaves.add_parser(
        name, parents=[_row_filters()], help=help_text
    )
    parser.add_argument(
        '--format', type=str, choices=['mseed', 'sac'], default='mseed',
        help='output format (default: %(default)s)'
    )
    parser.add_argument(
        '--output-dir', type=str, default='waveform_cache',
        help='output directory (default: %(default)s)'
    )
    set_action(parser, 'wfcache_extract')
    return parser


def _add_reset_leaf(leaves, name, help_text):
    """Add the leaf that resets the failure-cache rows."""
    parser = leaves.add_parser(
        name, parents=[parent_dry_run()], help=help_text
    )
    parser.add_argument(
        '--event-id', action='append', default=[],
        help='event ID to reset (repeatable)'
    )
    parser.add_argument(
        '--event-id-file', type=str, default=None,
        help='path to text file with event IDs to reset'
    )
    parser.add_argument(
        '--all', action='store_true', help='reset all failure rows'
    )
    parser.add_argument(
        '--older-than', type=str, default=None, metavar='DURATION',
        help='reset rows older than DURATION (e.g., 6h, 7d)'
    )
    set_action(parser, 'wfcache_reset_failures')
    return parser


def add_to(subparsers):
    """Add the "wfcache" group to the command line."""
    group, leaves = add_group(
        subparsers, 'wfcache', 'manage the persistent waveform cache'
    )
    _add_prefetch_leaf(
        leaves, 'prefetch', 'prefetch waveform windows into '
        'the persistent cache'
    )
    _add_print_leaf(leaves, 'print', 'print cached waveform rows')
    _add_inspect_leaf(
        leaves, 'inspect', 'print persistent waveform-cache summary'
    )
    _add_extract_leaf(
        leaves, 'extract', 'extract cached waveforms to external files'
    )
    _add_reset_leaf(
        leaves, 'reset-failures', 'reset persistent waveform '
        'failure-cache rows'
    )
    return group
