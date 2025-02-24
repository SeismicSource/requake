# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Argument parser for Requake.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import textwrap
import argparse
import argcomplete
from .._version import get_versions


class NewlineHelpFormatter(argparse.HelpFormatter):
    """
    Custom help formatter that preserves newlines in help messages.
    """
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


class SubcommandHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """
    Custom help formatter that removes the list of subcommands from the help
    message.

    See: https://stackoverflow.com/a/13429281/2021880
    """
    def _format_action(self, action):
        parts = super(
            argparse.RawDescriptionHelpFormatter, self
        )._format_action(action)
        if action.nargs == argparse.PARSER:
            parts = '\n'.join(parts.split('\n')[1:])
        return parts


def parse_arguments(progname='requake'):
    """
    Parse command line arguments.

    :param progname: Program name (default: "requake").
    :type progname: str
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description=f'{progname}: Repeating earthquakes search and analysis.',
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
            'at least one column for the event\'s origin time '
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
        help='format for the output table (default: %(default)s)'
    )
    # ---
    # --- print_catalog
    subparser.add_parser(
        'print_catalog',
        parents=[print_format],
        help='print the event catalog to screen'
    )
    # ---
    # --- scan_catalog
    subparser.add_parser(
        'scan_catalog',
        parents=[force],
        help='scan an existing catalog for earthquake pairs'
    )
    # ---
    # --- print_pairs
    print_pairs = subparser.add_parser(
        'print_pairs',
        parents=[print_format],
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
    # --- plot_pair
    plot_pair = subparser.add_parser(
        'plot_pair',
        parents=[traceid, freq_band],
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
    subparser.add_parser(
        'print_families',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, print_format
        ],
        help='print families to screen'
    )
    # ---
    # --- plot_families
    plotfamilies = subparser.add_parser(
        'plot_families',
        parents=[
            longerthan, shorterthan, minevents, family_numbers,
            traceid, freq_band
        ],
        help='plot traces for one ore more event families'
    )
    plotfamilies.add_argument(
        '-s', '--starttime', type=float, default=None,
        help='start time, in seconds relative to trace start, for the plot'
    )
    plotfamilies.add_argument(
        '-e', '--endtime', type=float, default=None,
        help='end time, in seconds relative to trace start, for the plot'
    )
    plotfamilies.add_argument(
        '-T', '--template', action='store_true',
        help='plot family members found with template scan'
    )
    # ---
    # --- plot_timespans
    plot_timespans = subparser.add_parser(
        'plot_timespans',
        parents=[
            longerthan, shorterthan, minevents, family_numbers, colorby,
            colormap, color_range
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
            colormap, color_range
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
            colormap, color_range
        ],
        help='plot families on a map'
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
             'certain map tiles might not be available at all zoom levels'
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
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    if args.action is None:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            f'{progname}: '
            'error: at least one positional argument is required\n'
        )
        sys.exit(2)
    # Additional code for "longerthan" and "shorterthan" options
    try:
        args.longerthan = _timespec_to_sec(args.longerthan)
    except AttributeError:
        pass
    except ValueError:
        sys.stderr.write(
            f"{progname} {args.action}: "
            "error: argument -l/--longerthan: "
            f"invalid value: '{args.longerthan}'\n"
        )
        sys.exit(2)
    try:
        args.shorterthan = _timespec_to_sec(args.shorterthan)
    except AttributeError:
        pass
    except ValueError:
        sys.stderr.write(
            f"{progname} {args.action}: "
            "error: argument -S/--shorterthan: "
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
        time_in_seconds *= 24*60
    elif suffix == 'd':
        time_in_seconds *= 24*60*60
    elif suffix == 'M':
        time_in_seconds *= 30*24*60*60
    elif suffix == 'y':
        time_in_seconds *= 365*24*60*60
    else:
        raise ValueError(f"Invalid time specification: {timespec}")
    return time_in_seconds
