# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Argument parser for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
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


def parse_arguments(progname='requake'):
    """
    Parse command line arguments.

    :param progname: Program name (default: "requake").
    :type progname: str
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description=f'{progname}: Repeating earthquakes search and analysis.'
    )
    subparser = parser.add_subparsers(dest='action')
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
    # --- sample_config
    subparser.add_parser(
        'sample_config',
        help='write sample config file to current directory and exit'
    )
    # ---
    # --- read catalog
    readcatalog = subparser.add_parser(
        'read_catalog',
        help='read an event catalog from web services or from a file',
        formatter_class=NewlineHelpFormatter
    )
    readcatalog.add_argument(
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
    readcatalog.add_argument(
        '-a', '--append', action='store_true',
        help='append events to existing catalog'
    )
    # ---
    # --- scan_catalog
    subparser.add_parser(
        'scan_catalog',
        help='scan an existing catalog for earthquake pairs'
    )
    # ---
    # --- plot_pair
    plotpair = subparser.add_parser(
        'plot_pair',
        help='plot traces for a given event pair'
    )
    plotpair.add_argument('evid1')
    plotpair.add_argument('evid2')
    # ---
    # --- build_families
    subparser.add_parser(
        'build_families',
        help='build families of repeating earthquakes from a catalog of pairs'
    )
    # ---
    # --- longerthan
    #     a parent parser for the "longerthan" option,
    #     used by several subparsers
    longerthan = argparse.ArgumentParser(add_help=False)
    longerthan.add_argument(
        '-l', '--longerthan', type=str, default=0, metavar='DURATION',
        help='only use families lasting longer than this value. '
             'You can specify DURATION in days (e.g., 100d) '
             'or in years (e.g., 2.5y).'
    )
    # ---
    # --- minevents
    #     a parent parser for the "minevents" option,
    #     used by several subparsers
    minevents = argparse.ArgumentParser(add_help=False)
    minevents.add_argument(
        '-m', '--minevents', type=int, default=0, metavar='NEVENTS',
        help='only use families with at least NEVENTS events.'
    )
    # ---
    # --- familynumbers
    #     a parent parser for the "family_numbers" option,
    #     used by several subparsers
    familynumbers = argparse.ArgumentParser(add_help=False)
    familynumbers.add_argument(
        'family_numbers', default='all', nargs='?',
        help='family numbers to use. It can be a single number, '
             'a comma-separated list (ex.: 1,4,8), '
             'a hyphen-separated number range (ex.: 2-12), or "all" '
             '(default: "all"). '
    )
    # ---
    # --- traceid
    #     a parent parser for the "traceid" option,
    #     used by several subparsers
    traceid = argparse.ArgumentParser(add_help=False)
    traceid.add_argument(
        '-t', '--traceid', type=str, default=None,
        help='use this traceid instead of the default one for the family.'
    )
    # ---
    # --- print_families
    printfamilies = subparser.add_parser(
        'print_families',
        parents=[longerthan, minevents, familynumbers],
        help='print families to screen'
    )
    printfamilies.add_argument(
        '-f', '--format', type=str, default='simple',
        help='format for the output table.'
             'Choose between "simple", "markdown" and "csv"'
    )
    # ---
    # --- plot_families
    plotfamilies = subparser.add_parser(
        'plot_families',
        parents=[longerthan, minevents, familynumbers, traceid],
        help='plot traces for one ore more event families'
    )
    plotfamilies.add_argument(
        '-s', '--starttime', type=float, default=None,
        help='start time, in seconds relative to trace start, for the plot.'
    )
    plotfamilies.add_argument(
        '-e', '--endtime', type=float, default=None,
        help='end time, in seconds relative to trace start, for the plot.'
    )
    # ---
    # --- plot_timespans
    timespans = subparser.add_parser(
        'plot_timespans',
        parents=[longerthan, minevents, familynumbers],
        help='plot family timespans'
    )
    timespans.add_argument(
        '-s', '--sortby', type=str, default=None,
        choices=[
            'time', 'latitude', 'longitude', 'depth', 'distance_from',
            'family_number'
        ],
        help='quantity to sort families by on y-axis. '
             'Possible values are: time, latitude, longitude, depth, '
             'distance_from, family_number. If not specified, the config '
             'value "sort_families_by" will be used.'
    )
    # ---
    # --- plot_slip
    subparser.add_parser(
        'plot_slip',
        parents=[longerthan, minevents, familynumbers],
        help='plot cumulative slip for one or more families'
    )
    # ---
    # --- map_families
    mapfamilies = subparser.add_parser(
        'map_families',
        parents=[longerthan, minevents, familynumbers],
        help='plot families on a map'
    )
    mapfamilies.add_argument(
        '-M', '--mapstyle', type=str, default='satellite',
        choices=[
            'stamen_terrain', 'satellite', 'street', 'hillshade',
            'hillshade_dark', 'ocean'
        ],
        help='style of map to plot. Possible values are: '
             'stamen_terrain, satellite, street, hillshade, hillshade_dark, '
             'ocean'
    )
    mapfamilies.add_argument(
        '-k', '--apikey', type=str, default=None,
        help='API key for Stamen Terrain map tiles (default: None). '
             'You can get a free API key at https://stadiamaps.com/'
    )
    mapfamilies.add_argument(
        '-z', '--zoom', type=int, default=None,
        help='zoom level for the map tiles (default: None). Note that '
             'certain map tiles might not be available at all zoom levels.'
    )
    # ---
    # --- flag_family
    flagfamily = subparser.add_parser(
        'flag_family',
        help='flag a family of repeating earthquakes as valid or not valid. '
             'Note that all families are valid by default when first created'
    )
    flagfamily.add_argument('family_number')
    flagfamily.add_argument(
        'is_valid',
        help='"true" (or "t") to flag family as valid, '
             '"false" (or "f") to flag family as not valid.'
    )
    # ---
    # --- build_templates
    subparser.add_parser(
        'build_templates',
        parents=[longerthan, minevents, familynumbers, traceid],
        help='build waveform templates for one or more event families'
    )
    # ---
    # --- scan_templates
    scantemplates = subparser.add_parser(
        'scan_templates',
        parents=[longerthan, minevents, familynumbers, traceid],
        help='scan a continuous waveform stream using one or more templates'
    )
    scantemplates.add_argument(
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
    # Additional code for "longerthan" option
    try:
        # transform "longerthan" to seconds
        lt = args.longerthan
        if lt != 0:
            suffix = lt[-1]
            lt_float = float(lt[:-1])
            if suffix == 'd':
                lt_float *= 24*60*60
            elif suffix == 'y':
                lt_float *= 365*24*60*60
            else:
                raise ValueError
            args.longerthan = lt_float
    except AttributeError:
        pass
    except ValueError:
        sys.stderr.write(
            f"{progname} {args.action}: "
            f"error: argument -l/--longerthan: invalid value: '{lt}'\n"
        )
        sys.exit(2)
    # args.traceid need to exist
    if not hasattr(args, 'traceid'):
        args.traceid = None
    return args
