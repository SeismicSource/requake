# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
"""
Argument parser for Requake.

:copyright:
    2021-2022 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import sys
import argparse
import argcomplete
from ._version import get_versions


def parse_arguments(progname='requake'):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='{}: Repeating earthquakes '
                    'search and analysis.'.format(progname))
    subparser = parser.add_subparsers(dest='action')
    parser.add_argument(
        '-c', '--configfile', type=str, default='{}.conf'.format(progname),
        help='config file (default: {}.conf)'.format(progname)
    )
    parser.add_argument(
        '-o', '--outdir', type=str, default='{}_out'.format(progname),
        help='save output to OUTDIR (default: {}_out)'.format(progname)
    )
    parser.add_argument(
        '-v', '--version', action='version',
        version='%(prog)s {}'.format(get_versions()['version']))
    # --- sample_config
    subparser.add_parser(
        'sample_config',
        help='write sample config file to current directory and exit'
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
        parents=[longerthan, familynumbers],
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
        parents=[longerthan, familynumbers, traceid],
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
        parents=[longerthan, familynumbers],
        help='plot family timespans'
    )
    timespans.add_argument(
        '-s', '--sortby', type=str, default=None, metavar='QUANTITY',
        help='quantity to sort families by on y-axis. '
             'Possible values are: time, latitude, longitude, depth, '
             'distance_from. If not specified, the config value '
             '"sort_families_by" will be used.'
    )
    # ---
    # --- plot_slip
    subparser.add_parser(
        'plot_slip',
        parents=[longerthan, familynumbers],
        help='plot cumulative slip for one or more families'
    )
    # ---
    # --- map_families
    subparser.add_parser(
        'map_families',
        parents=[longerthan, familynumbers],
        help='plot families on a map'
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
        parents=[longerthan, familynumbers, traceid],
        help='build waveform templates for one or more event families'
    )
    # ---
    # --- build_templates
    scantemplates = subparser.add_parser(
        'scan_templates',
        parents=[longerthan, familynumbers, traceid],
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
            '{}: error: at least one positional argument '
            'is required\n'.format(progname)
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
            '{} {}: error: argument -l/--longerthan: '
            "invalid value: '{}'\n".format(progname, args.action, lt)
        )
        sys.exit(2)
    # args.traceid need to exist
    if not hasattr(args, 'traceid'):
        args.traceid = None
    return args
