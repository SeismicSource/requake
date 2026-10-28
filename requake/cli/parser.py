# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Assemble and parse the Requake command line.

The command line is a two-level tree: a verb (or a namespace) followed by
the object the verb acts on, e.g. ``requake print pairs`` or
``requake delete scan 3``.  Each first-level group is built by its own
module, so that a new command is added in one place.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import argcomplete
from .._version import get_versions
from ..logo import REQUAKE_LOGO
from . import (
    build_group, config_group, delete_group, flag_group, list_group,
    plot_group, print_group, read_group, scan_group, wfcache_group,
)
from .help_format import ColoredHelpArgumentParser, SubcommandHelpFormatter
from .values import timespec_to_sec

_GROUPS = (
    config_group, read_group, scan_group, build_group, print_group,
    list_group, plot_group, flag_group, delete_group, wfcache_group,
)


def build_parser(progname='requake'):
    """
    Build the Requake command line parser.

    :param progname: Program name (default: "requake").
    :type progname: str
    :return: the parser and the parsers of the first-level groups, by name
    :rtype: tuple
    """
    parser = ColoredHelpArgumentParser(
        description=(
            f'{REQUAKE_LOGO}\n'
            'Repeating earthquakes search and analysis.'
        ),
        epilog='Use "%(prog)s <verb> <object> -h" for help on a specific\n'
               'command (example: "%(prog)s plot map -h").\n'
               '\nFull documentation at https://requake.readthedocs.io',
        formatter_class=SubcommandHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='action', title='commands')
    subparsers.metavar = '<command> [options]'
    parser.add_argument(
        '-c', '--configfile', type=str, default=f'{progname}.conf',
        help=f'config file (default: {progname}.conf)'
    )
    parser.add_argument(
        '-o', '--outdir', type=str, default=f'{progname}_out',
        help=f'save output to OUTDIR (default: {progname}_out)'
    )
    parser.add_argument(
        '-v', '--version', action='version',
        version=f"%(prog)s {get_versions()['version']}"
    )
    group_parsers = {}
    for module in _GROUPS:
        group_parser = module.add_to(subparsers)
        group_parsers[group_parser.prog.split()[-1]] = group_parser
    return parser, group_parsers


def _convert_durations(args, progname):
    """Convert the "--longer-than" and "--shorter-than" values to seconds."""
    for dest, option in (
        ('longerthan', '-l/--longer-than'),
        ('shorterthan', '-S/--shorter-than'),
    ):
        try:
            value = timespec_to_sec(getattr(args, dest))
        except AttributeError:
            continue
        except ValueError:
            sys.stderr.write(
                f'{progname}: error: argument {option}: '
                f"invalid value: '{getattr(args, dest)}'\n"
            )
            sys.exit(2)
        setattr(args, dest, value)


def _set_missing_defaults(args):
    """Make sure the options read by the commands always exist."""
    if not hasattr(args, 'traceid'):
        args.traceid = None
    for name in ('catalog_id', 'scan_id', 'build_id'):
        if not hasattr(args, name):
            setattr(args, name, None)


def _check_events_format(args, progname):
    """Reject "--events" together with a statistics output."""
    if (
        getattr(args, 'events', False)
        and getattr(args, 'format', '') == 'stats'
    ):
        sys.stderr.write(
            f'{progname} print families: '
            "error: argument -E/--events: not allowed with '-f stats'\n"
        )
        sys.exit(2)


def parse_arguments(progname='requake'):
    """
    Parse command line arguments.

    :param progname: Program name (default: "requake").
    :type progname: str
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser, group_parsers = build_parser(progname)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    if args.action is None:
        parser.print_help()
        sys.exit(0)
    group_parser = group_parsers.get(args.action)
    if group_parser is not None:
        group_parser.print_help()
        sys.exit(0)
    _convert_durations(args, progname)
    _set_missing_defaults(args)
    _check_events_format(args, progname)
    return args
