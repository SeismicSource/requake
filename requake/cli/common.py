# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Parent parsers shared by the Requake command line leaf commands.

Each function returns a fresh ``add_help=False`` parser, so that a leaf
command can list the options it needs::

    parents=[parent_force(), parent_scan_id()]

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import argparse
from .help_format import SubcommandHelpFormatter
from .values import PrintFormatAction, hide_aliases

_DURATION_HELP = (
    'You can specify DURATION in seconds (e.g., 10s), '
    'minutes (e.g., 3.3m), hours (e.g., 3.5h), days (e.g., 100d), '
    'months (e.g., 2M), or in years (e.g., 2.5y)'
)


def _parent():
    """Return an empty parent parser."""
    return argparse.ArgumentParser(add_help=False)


def _sentence(text):
    """Return *text* as a sentence, with a capital and a final period."""
    text = f'{text[0].upper()}{text[1:]}'
    return text if text.endswith('.') else f'{text}.'


def add_group(subparsers, name, help_text):
    """
    Add a first-level command group.

    :param subparsers: the top-level subparsers
    :type subparsers: argparse._SubParsersAction
    :param name: the group name, e.g. ``'plot'``
    :type name: str
    :param help_text: the one-line description of the group
    :type help_text: str
    :return: the group parser and its subparsers
    :rtype: tuple
    """
    group = subparsers.add_parser(
        name, help=help_text, description=_sentence(help_text),
        formatter_class=SubcommandHelpFormatter
    )
    # The object name is stored in its own destination: the action id of
    # the leaf command overwrites the group name stored by the top-level
    # parser, so that a group given alone keeps its name in ``action``.
    leaves = group.add_subparsers(
        dest='object', title='objects', metavar='<object> [options]'
    )
    return group, leaves


def set_action(parser, action):
    """
    Attach the action id to a leaf parser.

    :param parser: the leaf parser
    :type parser: argparse.ArgumentParser
    :param action: the action id used by the dispatcher, e.g.
        ``'read_catalog'``
    :type action: str
    """
    parser.set_defaults(action=action)


def parent_force():
    """Return a parent parser for the "force" option."""
    parser = _parent()
    parser.add_argument(
        '-f', '--force', action='store_true',
        help='force overwriting of existing files'
    )
    return parser


def parent_dry_run():
    """Return a parent parser for the "dry-run" option."""
    parser = _parent()
    parser.add_argument(
        '-n', '--dry-run', action='store_true',
        help='only report what would be done, without changing the database'
    )
    return parser


def parent_catalog_id():
    """Return a parent parser for the "catalog-id" option."""
    parser = _parent()
    parser.add_argument(
        '--catalog-id', type=int, default=None, metavar='CATALOG_ID',
        help='use this catalog id instead of the latest one'
    )
    return parser


def parent_scan_id():
    """Return a parent parser for the "scan-id" option."""
    parser = _parent()
    parser.add_argument(
        '--scan-id', type=int, default=None, metavar='SCAN_ID',
        help='use this catalog scan instead of the latest one'
    )
    return parser


def parent_build_id():
    """Return a parent parser for the "build-id" option."""
    parser = _parent()
    parser.add_argument(
        '--build-id', type=int, default=None, metavar='BUILD_ID',
        help='use this family build instead of the latest one'
    )
    return parser


def parent_label():
    """Return a parent parser for the "label" option."""
    parser = _parent()
    parser.add_argument(
        '-l', '--label', type=str, default=None, metavar='LABEL',
        help='a short label to help identifying this entry'
    )
    return parser


def parent_print_format(*extra_choices, pager=True):
    """
    Return a parent parser for the "format" option.

    :param extra_choices: additional formats accepted by this command
    :type extra_choices: str
    :param pager: whether the command uses the interactive pager, which
        an explicit format disables
    :type pager: bool
    """
    parser = _parent()
    choices = ['simple', 'markdown', 'csv', *extra_choices]
    help_text = 'format for the output (default: %(default)s)'
    if pager:
        help_text = f'{help_text}; implies --no-pager'
    parser.add_argument(
        '-f', '--format', type=str, default='simple',
        choices=choices, action=PrintFormatAction, help=help_text
    )
    return parser


def parent_print_pager():
    """Return a parent parser for the "no-pager" option."""
    parser = _parent()
    parser.add_argument(
        '--no-pager', action='store_true',
        help='disable the interactive curses pager'
    )
    return parser


def parent_traceid():
    """Return a parent parser for the "traceid" option."""
    parser = _parent()
    parser.add_argument(
        '-t', '--traceid', type=str, default=None,
        help='use this traceid instead of the one set in the config file'
    )
    return parser


def parent_freq_band():
    """Return a parent parser for the "freq-band" option."""
    parser = _parent()
    hide_aliases(
        parser.add_argument(
            '-F', '--freq-band', '--freq_band', nargs=2, type=float,
            default=None, metavar=('FREQ_MIN', 'FREQ_MAX'),
            help='use this frequency band instead of the one set in the '
                 'config file. Specify FREQ_MIN and FREQ_MAX in Hz.'
        ),
        '--freq_band'
    )
    return parser


def parent_output():
    """Return a parent parser for the "output" option."""
    parser = _parent()
    parser.add_argument(
        '-o', '--output', type=str, default='NO_OUTPUT', nargs='?',
        metavar='FILE_OR_FORMAT',
        help='Save the plot instead of displaying it. Provide a filename '
             '(e.g., "plot.png") to specify the output name and format, or '
             'just a format (e.g., "png", "pdf", "svg") to automatically '
             'generate a default filename. If omitted, the plot is saved as '
             'a PNG file with a default name.'
    )
    return parser


def parent_longer_than():
    """Return a parent parser for the "longer-than" option."""
    parser = _parent()
    hide_aliases(
        parser.add_argument(
            '-l', '--longer-than', '--longerthan', dest='longerthan',
            type=str, default='0d', metavar='DURATION',
            help='only use families lasting longer than this value. '
                 f'{_DURATION_HELP}'
        ),
        '--longerthan'
    )
    return parser


def parent_shorter_than():
    """Return a parent parser for the "shorter-than" option."""
    parser = _parent()
    hide_aliases(
        parser.add_argument(
            '-S', '--shorter-than', '--shorterthan', dest='shorterthan',
            type=str, default=None, metavar='DURATION',
            help='only use families lasting shorter than this value. '
                 f'{_DURATION_HELP}'
        ),
        '--shorterthan'
    )
    return parser


def parent_min_events():
    """Return a parent parser for the "min-events" option."""
    parser = _parent()
    hide_aliases(
        parser.add_argument(
            '-m', '--min-events', '--minevents', dest='minevents',
            type=int, default=0, metavar='NEVENTS',
            help='only use families with at least NEVENTS events'
        ),
        '--minevents'
    )
    return parser


def parent_family_numbers():
    """Return a parent parser for the "family_numbers" argument."""
    parser = _parent()
    parser.add_argument(
        'family_numbers', default='all', nargs='?',
        help='family numbers to use. It can be a single number, '
             'a comma-separated list (ex.: 1,4,8), '
             'a hyphen-separated number range (ex.: 2-12), or "all" '
             '(default: %(default)s)'
    )
    return parser


def parent_color_by():
    """Return a parent parser for the "color-by" option."""
    parser = _parent()
    hide_aliases(
        parser.add_argument(
            '-c', '--color-by', '--colorby', dest='colorby', type=str,
            default='family_number', metavar='QUANTITY',
            choices=[
                'time', 'latitude', 'longitude', 'depth', 'distance_from',
                'family_number', 'cumul_slip', 'cumul_moment',
                'number_of_events', 'duration', 'slip_rate'
            ],
            help='quantity to color families by. Choose among {%(choices)s} '
                 '(default: %(default)s)'
        ),
        '--colorby'
    )
    return parser


def parent_colormap():
    """Return a parent parser for the "colormap" option."""
    parser = _parent()
    parser.add_argument(
        '-C', '--colormap', type=str, default=None,
        metavar='COLORMAP',
        help='color map to use for plotting. Use any colormap available in '
             'Matplotlib (e.g., "viridis", "plasma", "inferno"). '
             'If not provided, a default color map will be used, based on the '
             'quantity specified with the -c/--color-by option'
    )
    return parser


def parent_color_range():
    """Return a parent parser for the "range" option."""
    # Note that "range" is a reserved word in Python, so we use
    # "color_range" for the variable name
    parser = _parent()
    parser.add_argument(
        '-r', '--range', type=str, default=None,
        metavar='RANGE',
        help='range of values for the colorbar. Use a comma-separated list of '
             'two values (e.g., "0,100"). Default behavior is to use the '
             'minimum and maximum values of the quantity specified with the '
             '-c/--color-by option. Note that for "duration" the range is '
             'expressed in years. Also note that this option is ignored if '
             'the -c/--color-by option is set to "family_number".'
    )
    return parser
