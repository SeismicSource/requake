
#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
"""
Argument parser for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
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
    subparser.add_parser(
        'sample_config',
        help='write sample config file to current directory and exit'
    )
    subparser.add_parser(
        'scan_catalog',
        help='scan an existing catalog for earthquake pairs'
    )
    subparser.add_parser(
        'scan_template',
        help='scan a continuous waveform stream using a template'
    )
    plotpair = subparser.add_parser(
        'plot_pair',
        help='plot traces for a given event pair'
    )
    plotpair.add_argument('evid1')
    plotpair.add_argument('evid2')
    subparser.add_parser(
        'build_families',
        help='build families of repeating earthquakes from a catalog of pairs'
    )
    plotfamilies = subparser.add_parser(
        'plot_families',
        help='plot traces for one ore more event families'
    )
    plotfamilies.add_argument(
        'family_numbers',
        help='family_numbers to plot. It can be a single number, '
             'a comma-separated list or a hyphen-separated number range. '
             'Use "all" to specify all the families.')
    plotfamilies.add_argument(
        '-s', '--starttime', type=float, default=None,
        help='Start time, in seconds relative to trace start, for the plot.'
    )
    plotfamilies.add_argument(
        '-e', '--endtime', type=float, default=None,
        help='End time, in seconds relative to trace start, for the plot.'
    )
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
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    if args.action is None:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            '{}: error: at least one positional argument '
            'is required\n'.format(progname)
        )
        sys.exit(2)
    return args
