# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Argument parser for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import re
import sys
import textwrap
import argparse
import argcomplete
from .._version import get_versions
from ..logo import REQUAKE_LOGO
from ..terminal import color_enabled, style


# ---------------------------------------------------------------------------
#  Colored help and usage output
# ---------------------------------------------------------------------------

# Stream that help or usage output is being written to; used to decide
# whether colors should be used.  ``None`` means ``sys.stdout``.
_help_stream = None

_USAGE_PREFIX = 'Usage: '

# Tokens to colorize inside a usage line: option strings, ``<metavars>``,
# uppercase metavars and the trailing ellipsis.  Square brackets belong to
# the usage grammar and are left uncolored.
_USAGE_TOKEN_PATTERN = (
    r'\[|\]'
    r'|(?<![\w-])-{1,2}[A-Za-z][\w-]*'
    r'|<[^<>]+>'
    r'|(?<![\w])[A-Z][A-Z0-9_]+'
    r'|\.\.\.'
)


def _set_help_stream(stream):
    """Set the stream help output is being written to."""
    global _help_stream  # pylint: disable=global-statement
    _help_stream = stream


def _help_colors_enabled():
    """Return True if help output should be colorized."""
    return color_enabled(_help_stream)


def _style_help(text, *styles):
    """Style a piece of help output."""
    return style(text, *styles, stream=_help_stream)


def _colorize_usage_token(match):
    """Colorize a single token of a usage line."""
    token = match.group()
    return token if token in ('[', ']') else _style_help(token, 'cyan')


def _collect_metavars(formatter, actions):
    """Return the metavar strings of a set of actions."""
    metavars = []
    for action in actions:
        if isinstance(action.metavar, str):
            metavars.append(action.metavar)
        elif not action.option_strings:
            default = formatter._get_default_metavar_for_positional(action)
            metavars.extend(formatter._metavar_formatter(action, default)(1))
    return metavars


def _colorize_usage_args(text, metavars):
    """Colorize options and metavars in a usage string."""
    literals = sorted(
        (m for m in metavars if m), key=len, reverse=True
    )
    pattern = '|'.join(
        [re.escape(item) for item in literals] + [_USAGE_TOKEN_PATTERN]
    )
    return re.compile(pattern).sub(_colorize_usage_token, text)


def _colorize_usage(text, prog, metavars):
    """Colorize a usage line (prefix, program name and arguments)."""
    if not text.startswith(_USAGE_PREFIX):
        return text
    body = text[len(_USAGE_PREFIX):]
    if prog and body.startswith(prog):
        program = _style_help(prog, 'gray')
        body = body[len(prog):]
    else:
        program = ''
    args = _colorize_usage_args(body, metavars)
    return f'{_style_help(_USAGE_PREFIX, "dark_orange")}{program}{args}'


def _colorize_action(text, invocation):
    """Colorize the option strings or the name of a formatted action."""
    if not invocation or not _help_colors_enabled():
        return text
    return text.replace(invocation, _style_help(invocation, 'cyan'), 1)


class ColoredHelpMixin:
    """Add colors to argparse help and usage output."""

    def start_section(self, heading):
        """Capitalize and colorize section headings."""
        if heading and heading is not argparse.SUPPRESS:
            heading = _style_help(heading.title(), 'dark_orange')
        super().start_section(heading)

    def _format_usage(self, usage, actions, groups, prefix):
        """Colorize the usage line."""
        if prefix is None:
            prefix = _USAGE_PREFIX
        text = super()._format_usage(usage, actions, groups, prefix)
        if not _help_colors_enabled():
            return text
        metavars = _collect_metavars(self, actions)
        return _colorize_usage(text, self._prog, metavars)

    def _format_action(self, action):
        """Colorize the option strings or the name of an action."""
        text = super()._format_action(action)
        return _colorize_action(text, self._format_action_invocation(action))


class ColoredHelpFormatter(ColoredHelpMixin, argparse.HelpFormatter):
    """Default help formatter, with colored output."""


class NewlineHelpFormatter(ColoredHelpMixin, argparse.HelpFormatter):
    """Custom help formatter that preserves newlines in help messages."""

    def _split_lines(self, text, width):
        lines = []
        for line in text.splitlines():  # Split the text by newlines first
            if len(line) > width:
                # Use textwrap to wrap lines that are too long
                wrap_lines = textwrap.wrap(line, width)
                lines.extend(wrap_lines)
            else:
                # For lines that are short enough, just add them as they are
                lines.append(line)
        return lines


class SubcommandHelpFormatter(
    ColoredHelpMixin, argparse.RawDescriptionHelpFormatter
):
    """
    Custom help formatter that removes the subcommand list from help.

    See: https://stackoverflow.com/a/13429281/2021880
    """

    def _format_action(self, action):
        parts = super(
            argparse.RawDescriptionHelpFormatter, self
        )._format_action(action)
        if action.nargs == argparse.PARSER:
            parts = '\n'.join(parts.split('\n')[1:])
        return _colorize_action(parts, self._format_action_invocation(action))


class ColoredHelpArgumentParser(argparse.ArgumentParser):
    """Argument parser whose help and usage output is colored on terminals."""

    def __init__(self, *args, **kwargs):
        """Set up the parser with the colored help formatter."""
        kwargs.setdefault('formatter_class', ColoredHelpFormatter)
        super().__init__(*args, **kwargs)

    def print_help(self, file=None):
        """Print the help message, colorized if ``file`` is a terminal."""
        _set_help_stream(sys.stdout if file is None else file)
        try:
            super().print_help(file)
        finally:
            _set_help_stream(None)

    def print_usage(self, file=None):
        """Print the usage message, colorized if ``file`` is a terminal."""
        _set_help_stream(sys.stdout if file is None else file)
        try:
            super().print_usage(file)
        finally:
            _set_help_stream(None)


def _nonnegative_int(value):
    """Argparse type for integers >= 0."""
    try:
        int_value = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f'invalid non-negative integer value: {value}'
        ) from err
    if int_value < 0:
        raise argparse.ArgumentTypeError(
            f'invalid non-negative integer value: {value}'
        )
    return int_value


class _PrintFormatAction(argparse.Action):
    """
    Store the output format and disable the interactive pager.

    The pager draws the table with its own layout and ignores the
    requested output format, hence an explicitly requested format
    implies plain-text output.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        """Set the output format and disable the pager."""
        setattr(namespace, self.dest, values)
        setattr(namespace, 'no_pager', True)


def parse_arguments(progname='requake'):
    """
    Parse command line arguments.

    :param progname: Program name (default: "requake").
    :type progname: str
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = ColoredHelpArgumentParser(
        description=(
            f'{REQUAKE_LOGO}\n'
            'Repeating earthquakes search and analysis.'
        ),
        epilog='Use "%(prog)s <command> -h" for help on a specific command\n'
               '(example: "%(prog)s read_catalog -h").\n'
               '\nFull documentation at https://requake.readthedocs.io',
        formatter_class=SubcommandHelpFormatter
    )
    subparser = parser.add_subparsers(dest='action', title='commands')
    subparser.metavar = '<command> [options]'
    parser.add_argument(
        '-c',
        '--configfile',
        type=str,
        default=f'{progname}.conf',
        help=f'config file (default: {progname}.conf)',
    )
    parser.add_argument(
        '-o',
        '--outdir',
        type=str,
        default=f'{progname}_out',
        help=f'save output to OUTDIR (default: {progname}_out)',
    )
    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version=f"%(prog)s {get_versions()['version']}",
    )
    # --- force
    #     A parent parser for the "force" option,
    #     used by several subparsers
    force = argparse.ArgumentParser(add_help=False)
    force.add_argument(
        '-f', '--force', action='store_true',
        help='force overwriting of existing files'
    )
    # --- sample_config
    subparser.add_parser(
        'sample_config',
        help='write sample config file to current directory and exit'
    )
    # ---
    # --- update_config
    update_config = subparser.add_parser(
        'update_config',
        help='update an existing config file to the latest version'
    )
    update_config.add_argument(
        'config_file', default='requake.conf', nargs='?',
        help='config file to be updated (default: %(default)s)'
    )
    # ---
    # --- read_catalog
    read_catalog = subparser.add_parser(
        'read_catalog',
        parents=[force],
        help='read an event catalog from web services or from a file',
        formatter_class=NewlineHelpFormatter
    )
    read_catalog.add_argument(
        'catalog_file', nargs='?', help=(
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
    )
    read_catalog.add_argument(
        '-a', '--append', action='store_true',
        help='append events to existing catalog'
    )
    # --- print_format
    #     a parent parser for the "format" option,
    #     used by the "print" subparsers
    print_format = argparse.ArgumentParser(add_help=False)
    print_format.add_argument(
        '-f', '--format', type=str, default='simple',
        choices=['simple', 'markdown', 'csv'],
        action=_PrintFormatAction,
        help='format for the output table (default: %(default)s); '
             'implies --no-pager'
    )
    # ---
    # --- print_pager
    #     a parent parser for the "no_pager" option,
    #     used by the "print" subparsers
    print_pager = argparse.ArgumentParser(add_help=False)
    print_pager.add_argument(
        '--no-pager', action='store_true',
        help='disable the interactive curses pager'
    )
    # ---
    # --- print_catalog
    subparser.add_parser(
        'print_catalog',
        parents=[print_format, print_pager],
        help='print the event catalog to screen'
    )
    # ---
    # --- scan_catalog
    scan_catalog = subparser.add_parser(
        'scan_catalog',
        help='scan an existing catalog for earthquake pairs'
    )
    scan_catalog_mode = scan_catalog.add_mutually_exclusive_group()
    scan_catalog_mode.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='delete existing event pairs and restart the scan'
    )
    scan_catalog_mode.add_argument(
        '-c',
        '--force-continue',
        action='store_true',
        help='continue an interrupted scan and keep existing event pairs'
    )
    scan_catalog.add_argument(
        '--nprocs',
        type=_nonnegative_int,
        default=None,
        help='number of worker processes for scan_catalog '
             '(0: auto, 1: disable parallelism)'
    )
    # ---
    # --- print_pairs
    print_pairs = subparser.add_parser(
        'print_pairs',
        parents=[print_format, print_pager],
        help='print pairs to screen'
    )
    print_pairs.add_argument(
        '-c', '--cc_min',
        type=float, default=None,
        help='minimum cross-correlation coefficient (default: %(default)s)'
    )
    print_pairs.add_argument(
        '-C', '--cc_max',
        type=float, default=None,
        help='maximum cross-correlation coefficient (default: %(default)s)'
    )
    print_pairs.add_argument(
        '--include-invalid', action='store_true',
        help='also show pairs flagged as invalid (e.g., pairs involving an '
             'event marked as duplicate), adding an "invalid" column'
    )
    print_pairs.add_argument(
        '--force', action='store_true',
        help='skip the large-dataset warning'
    )
    # ---
    # --- dedup_events
    dedup_events = subparser.add_parser(
        'dedup_events',
        help='detect and flag duplicate events in the catalog from close '
             'event pairs'
    )
    dedup_events.add_argument(
        '-c', '--cc_min',
        type=float, default=0.98,
        help='minimum cross-correlation coefficient for two events to be '
             'considered duplicates (default: %(default)s)'
    )
    dedup_events.add_argument(
        '-t', '--max-time-diff',
        type=float, default=60., metavar='SECONDS',
        help='maximum origin-time difference for two events to be '
             'considered duplicates (default: %(default)s s)'
    )
    dedup_events.add_argument(
        '-d', '--max-distance',
        type=float, default=2., metavar='KM',
        help='maximum horizontal distance for two events to be '
             'considered duplicates (default: %(default)s km)'
    )
    dedup_events.add_argument(
        '-n', '--dry-run', action='store_true',
        help='only print the report, without modifying the database'
    )
    dedup_events.add_argument(
        '--reset', action='store_true',
        help='reset the duplicate and invalid flags and exit, without '
             'performing duplicate detection'
    )
    # ---
    # --- traceid
    #     a parent parser for the "traceid" option,
    #     used by several subparsers
    traceid = argparse.ArgumentParser(add_help=False)
    traceid.add_argument(
        '-t', '--traceid', type=str, default=None,
        help='use this traceid instead of the one set in the config file'
    )
    # ---
    # --- freq_band
    #     a parent parser for the "freq_band" option,
    #     used by several subparsers
    freq_band = argparse.ArgumentParser(add_help=False)
    freq_band.add_argument(
        '-F', '--freq_band', nargs=2, type=float, default=None,
        metavar=('FREQ_MIN', 'FREQ_MAX'),
        help='use this frequency band instead of the one set in the '
             'config file. Specify FREQ_MIN and FREQ_MAX in Hz.'
    )
    # ---
    # --- parent parser for saving plots to file instead of showing
    #     them on screen
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument(
        '-o', '--output', type=str, default='NO_OUTPUT', nargs='?',
        metavar='FILE_OR_FORMAT',
        help='Save the plot instead of displaying it. Provide a filename '
             '(e.g., "plot.png") to specify the output name and format, or '
             'just a format (e.g., "png", "pdf", "svg") to automatically '
             'generate a default filename. If omitted, the plot is saved as '
             'a PNG file with a default name.'
    )
    # ---
    # --- plot_pair
    plot_pair = subparser.add_parser(
        'plot_pair',
        parents=[traceid, freq_band, output],
        help='plot traces for a given event pair'
    )
    plot_pair.add_argument('evid1')
    plot_pair.add_argument('evid2')
    # ---
    # --- build_families
    subparser.add_parser(
        'build_families',
        parents=[force],
        help='build families of repeating earthquakes from a catalog of pairs'
    )
    # ---
    # --- longerthan
    #     a parent parser for the "longerthan" option,
    #     used by several subparsers
    longerthan = argparse.ArgumentParser(add_help=False)
    longerthan.add_argument(
        '-l', '--longerthan', type=str, default='0d', metavar='DURATION',
        help='only use families lasting longer than this value. '
             'You can specify DURATION in seconds (e.g., 10s), '
             'minutes (e.g., 3.3m), hours (e.g., 3.5h), days (e.g., 100d), '
             'months (e.g., 2M), or in years (e.g., 2.5y)'
    )
    # --- shorterthan
    #     a parent parser for the "shorterthan" option,
    #     used by several subparsers
    shorterthan = argparse.ArgumentParser(add_help=False)
    shorterthan.add_argument(
        '-S', '--shorterthan', type=str, default=None, metavar='DURATION',
        help='only use families lasting shorter than this value. '
             'You can specify DURATION in seconds (e.g., 10s), '
             'minutes (e.g., 3.3m), hours (e.g., 3.5h), days (e.g., 100d), '
             'months (e.g., 2M), or in years (e.g., 2.5y)'
    )
    # ---
    # --- minevents
    #     a parent parser for the "minevents" option,
    #     used by several subparsers
    minevents = argparse.ArgumentParser(add_help=False)
    minevents.add_argument(
        '-m', '--minevents', type=int, default=0, metavar='NEVENTS',
        help='only use families with at least NEVENTS events'
    )
    # ---
    # --- family_numbers
    #     a parent parser for the "family_numbers" option,
    #     used by several subparsers
    family_numbers = argparse.ArgumentParser(add_help=False)
    family_numbers.add_argument(
        'family_numbers', default='all', nargs='?',
        help='family numbers to use. It can be a single number, '
             'a comma-separated list (ex.: 1,4,8), '
             'a hyphen-separated number range (ex.: 2-12), or "all" '
             '(default: %(default)s)'
    )
    # ---
    # --- colorby
    #     a parent parser for the "colorby" option,
    #     used by plotting subparsers
    colorby = argparse.ArgumentParser(add_help=False)
    colorby.add_argument(
        '-c', '--colorby', type=str, default='family_number',
        metavar='QUANTITY',
        choices=[
            'time', 'latitude', 'longitude', 'depth', 'distance_from',
            'family_number', 'cumul_slip', 'cumul_moment', 'number_of_events',
            'duration', 'slip_rate'
        ],
        help='quantity to color families by. Choose among {%(choices)s} '
             '(default: %(default)s)'
    )
    # --- colormap
    #     a parent parser for the "colormap" option,
    #     used by plotting subparsers
    colormap = argparse.ArgumentParser(add_help=False)
    colormap.add_argument(
        '-C', '--colormap', type=str, default=None,
        metavar='COLORMAP',
        help='color map to use for plotting. Use any colormap available in '
             'Matplotlib (e.g., "viridis", "plasma", "inferno"). '
             'If not provided, a default color map will be used, based on the '
             'quantity specified with the -c/--colorby option'
    )
    # --- color_range
    #     a parent parser for the "range" option,
    #     used by plotting subparsers
    # Note that "range" is a reserved word in Python, so we use "color_range"
    # for the variable name
    color_range = argparse.ArgumentParser(add_help=False)
    color_range.add_argument(
        '-r', '--range', type=str, default=None,
        metavar='RANGE',
        help='range of values for the colorbar. Use a comma-separated list of '
             'two values (e.g., "0,100"). Default behavior is to use the '
             'minimum and maximum values of the quantity specified with the '
             '-c/--colorby option. Note that for "duration" the range is '
             'expressed in years. Also note that this option is ignored if '
             'the -c/--colorby option is set to "family_number".'
    )
    # ---
    # --- print_families
    print_families = subparser.add_parser(
        'print_families',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, print_pager
        ],
        help='print families to screen'
    )
    print_families.add_argument(
        '-f', '--format', type=str, default='simple',
        choices=['simple', 'markdown', 'csv', 'stats'],
        action=_PrintFormatAction,
        help='format for the output (default: %(default)s); '
             'implies --no-pager'
    )
    print_families.add_argument(
        '-d', '--detailed', action='store_true',
        help='print detailed information for each family, including a list '
             'of events'
    )
    # ---
    # --- plot_families
    plot_families = subparser.add_parser(
        'plot_families',
        parents=[
            longerthan, shorterthan, minevents, family_numbers,
            traceid, freq_band, output
        ],
        help='plot traces for one ore more event families'
    )
    plot_families.add_argument(
        '-s', '--starttime', type=float, default=None,
        help='start time, in seconds relative to trace start, for the plot'
    )
    plot_families.add_argument(
        '-e', '--endtime', type=float, default=None,
        help='end time, in seconds relative to trace start, for the plot'
    )
    plot_families.add_argument(
        '-T', '--template', action='store_true',
        help='plot family members found with template scan'
    )
    # ---
    # --- plot_timespans
    plot_timespans = subparser.add_parser(
        'plot_timespans',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, colorby,
            colormap, color_range, output
        ],
        help='plot family timespans'
    )
    plot_timespans.add_argument(
        '-s', '--sortby', type=str, default='family_number',
        metavar='QUANTITY',
        choices=[
            'time', 'latitude', 'longitude', 'depth', 'distance_from',
            'family_number'
        ],
        help='quantity to sort families by on y-axis. Choose among '
             '{%(choices)s}. Default: %(default)s'
    )
    # ---
    # --- plot_cumulative
    plot_cumulative = subparser.add_parser(
        'plot_cumulative',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, colorby,
            colormap, color_range, output
        ],
        help='cumulative plot for one or more families'
    )
    plot_cumulative.add_argument(
        '-q', '--quantity', type=str, default='slip',
        metavar='QUANTITY',
        choices=['slip', 'moment', 'number'],
        help='cumulative quantity to plot on y-axis. Choose among '
             '{%(choices)s}. Default: %(default)s'
    )
    plot_cumulative.add_argument(
        '-L', '--logscale', action='store_true',
        help='use log scale for y-axis'
    )
    # ---
    # --- map_families
    map_families = subparser.add_parser(
        'map_families',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, colorby,
            colormap, color_range, output
        ],
        help='plot families on a map'
    )
    map_families.add_argument(
        '-b', '--backend', type=str, default='cartopy',
        choices=['cartopy', 'folium'],
        help='map backend (default: %(default)s). The "folium" backend '
             'produces an interactive HTML map and requires the optional '
             '"folium" package; use "-o html" or an output filename '
             'ending in ".html" to save the map to a file'
    )
    map_families.add_argument(
        '-s', '--sizeby', type=str, default='number_of_events',
        metavar='QUANTITY',
        choices=[
            'number_of_events', 'duration', 'depth', 'latitude', 'longitude',
            'distance_from', 'cumul_moment', 'cumul_slip', 'slip_rate'
        ],
        help='quantity to scale the family marker size by. Choose among '
             '{%(choices)s} (default: %(default)s). A logarithmic scale is '
             'used when the values span more than one order of magnitude'
    )
    map_families.add_argument(
        '-M', '--mapstyle', type=str, default='satellite',
        metavar='STYLE',
        choices=[
            'stamen_terrain', 'satellite', 'street', 'hillshade',
            'hillshade_dark', 'ocean'
        ],
        help='style of map to plot. Choose among {%(choices)s} '
             '(default: %(default)s)'
    )
    map_families.add_argument(
        '-k', '--apikey', type=str, default=None,
        help='API key for Stamen Terrain map tiles (default: %(default)s). '
             'You can get a free API key at https://stadiamaps.com/'
    )
    map_families.add_argument(
        '-z', '--zoom', type=int, default=None,
        help='zoom level for the map tiles (default: None). Note that '
             'certain map tiles might not be available at all zoom levels. '
             'For the folium backend, this sets the initial zoom level of '
             'the map, instead of fitting the map to the families'
    )
    # ---
    # --- flag_family
    flag_family = subparser.add_parser(
        'flag_family',
        help='flag a family of repeating earthquakes as valid or not valid'
    )
    flag_family.add_argument('family_number')
    flag_family.add_argument(
        'is_valid',
        help='"true" (or "t") to flag family as valid, '
             '"false" (or "f") to flag family as not valid'
    )
    # ---
    # --- build_templates
    subparser.add_parser(
        'build_templates',
        parents=[longerthan, shorterthan, minevents, family_numbers, traceid],
        help='build waveform templates for one or more event families'
    )
    # ---
    # --- scan_templates
    scan_templates = subparser.add_parser(
        'scan_templates',
        parents=[longerthan, shorterthan, minevents, family_numbers, traceid],
        help='scan a continuous waveform stream using one or more templates'
    )
    scan_templates.add_argument(
        '-T', '--template_file', type=str, default=None, metavar='FILE',
        help='use the provided file as template. '
             'File must be in SAC format, with a P pick in the '
             '"A" header field'
    )
    # ---
    # --- wfcache
    wfcache = subparser.add_parser(
        'wfcache',
        help='manage persistent waveform cache'
    )
    wfcache_sub = wfcache.add_subparsers(dest='wfcache_action')
    wfcache_sub.required = True

    wfcache_row_filters = argparse.ArgumentParser(add_help=False)
    wfcache_row_filters.add_argument(
        '--event-id',
        action='append',
        default=[],
        help='event ID filter (repeatable)'
    )
    wfcache_row_filters.add_argument(
        '--event-id-file',
        type=str,
        default=None,
        help='path to text file with event IDs'
    )
    wfcache_row_filters.add_argument(
        '--trace-id',
        action='append',
        default=[],
        help='trace-ID filter (repeatable)'
    )
    wfcache_row_filters.add_argument(
        '--start-time',
        type=str,
        default=None,
        help='minimum start time (UTCDateTime-compatible string)'
    )
    wfcache_row_filters.add_argument(
        '--end-time',
        type=str,
        default=None,
        help='maximum end time (UTCDateTime-compatible string)'
    )
    wfcache_row_filters.add_argument(
        '--limit',
        type=_nonnegative_int,
        default=None,
        help='limit number of returned rows'
    )

    wfcache_prefetch = wfcache_sub.add_parser(
        'prefetch',
        help='prefetch waveform windows into the persistent cache'
    )
    wfcache_prefetch.add_argument(
        '--event-id',
        action='append',
        default=[],
        help='event ID filter (repeatable)'
    )
    wfcache_prefetch.add_argument(
        '--event-id-file',
        type=str,
        default=None,
        help='path to text file with event IDs'
    )
    wfcache_prefetch.add_argument(
        '--trace-id',
        action='append',
        default=[],
        help='trace-ID filter (repeatable)'
    )
    wfcache_prefetch.add_argument(
        '--max-events',
        type=_nonnegative_int,
        default=None,
        help='maximum number of catalog events to prefetch'
    )
    wfcache_prefetch.add_argument(
        '--batch-size',
        type=_nonnegative_int,
        default=500,
        help='progress logging batch size (default: %(default)s)'
    )
    wfcache_prefetch.add_argument(
        '--group-window',
        type=str,
        default='1h',
        metavar='DURATION',
        help='max grouped download span (e.g., 30m, 1h; default: '
             '%(default)s)'
    )
    wfcache_prefetch.set_defaults(action='wfcache_prefetch')

    wfcache_print = wfcache_sub.add_parser(
        'print',
        parents=[wfcache_row_filters],
        help='print cached waveform rows'
    )
    wfcache_print.add_argument(
        '--json',
        action='store_true',
        help='print rows as JSON'
    )
    wfcache_print.set_defaults(action='wfcache_print')

    wfcache_inspect = wfcache_sub.add_parser(
        'inspect',
        help='print persistent waveform-cache summary'
    )
    wfcache_inspect.add_argument(
        '--integrity',
        action='store_true',
        help='run PRAGMA integrity_check'
    )
    wfcache_inspect.add_argument(
        '--json',
        action='store_true',
        help='print summary as JSON'
    )
    wfcache_inspect.set_defaults(action='wfcache_inspect')

    wfcache_extract = wfcache_sub.add_parser(
        'extract',
        parents=[wfcache_row_filters],
        help='extract cached waveforms to external files'
    )
    wfcache_extract.add_argument(
        '--format',
        type=str,
        choices=['mseed', 'sac'],
        default='mseed',
        help='output format (default: %(default)s)'
    )
    wfcache_extract.add_argument(
        '--output-dir',
        type=str,
        default='waveform_cache',
        help='output directory (default: %(default)s)'
    )
    wfcache_extract.set_defaults(action='wfcache_extract')

    wfcache_reset = wfcache_sub.add_parser(
        'reset-failures',
        help='reset persistent waveform failure-cache rows'
    )
    wfcache_reset.add_argument(
        '--event-id',
        action='append',
        default=[],
        help='event ID to reset (repeatable)'
    )
    wfcache_reset.add_argument(
        '--event-id-file',
        type=str,
        default=None,
        help='path to text file with event IDs to reset'
    )
    wfcache_reset.add_argument(
        '--all',
        action='store_true',
        help='reset all failure rows'
    )
    wfcache_reset.add_argument(
        '--older-than',
        type=str,
        default=None,
        metavar='DURATION',
        help='reset rows older than DURATION (e.g., 6h, 7d)'
    )
    wfcache_reset.add_argument(
        '--dry-run',
        action='store_true',
        help='show affected rows without deleting'
    )
    wfcache_reset.set_defaults(action='wfcache_reset_failures')
    # ---
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    if args.action is None:
        parser.print_help()
        sys.exit(0)
    # Additional code for "longerthan" and "shorterthan" options
    try:
        args.longerthan = _timespec_to_sec(args.longerthan)
    except AttributeError:
        pass
    except ValueError:
        sys.stderr.write(
            f'{progname} {args.action}: '
            'error: argument -l/--longerthan: '
            f"invalid value: '{args.longerthan}'\n"
        )
        sys.exit(2)
    try:
        args.shorterthan = _timespec_to_sec(args.shorterthan)
    except AttributeError:
        pass
    except ValueError:
        sys.stderr.write(
            f'{progname} {args.action}: '
            'error: argument -S/--shorterthan: '
            f"invalid value: '{args.shorterthan}'\n"
        )
        sys.exit(2)
    # args.traceid need to exist
    if not hasattr(args, 'traceid'):
        args.traceid = None
    return args


def _timespec_to_sec(timespec):
    """
    Convert a time specification to seconds.

    :param timespec: Time specification, e.g., "10s", "3.3m", "2h", "1d",
                     "2M", "3y".
    :type timespec: str
    :return: Time in seconds.
    :rtype: float
    """
    if timespec is None:
        return 1e999
    suffix = timespec[-1]
    time_in_seconds = float(timespec[:-1])
    if suffix == 's':
        time_in_seconds *= 1
    elif suffix == 'm':
        time_in_seconds *= 60
    elif suffix == 'h':
        time_in_seconds *= 24 * 60
    elif suffix == 'd':
        time_in_seconds *= 24 * 60 * 60
    elif suffix == 'M':
        time_in_seconds *= 30 * 24 * 60 * 60
    elif suffix == 'y':
        time_in_seconds *= 365 * 24 * 60 * 60
    else:
        raise ValueError(f'Invalid time specification: {timespec}')
    return time_in_seconds
