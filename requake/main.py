#!/usr/bin/env python
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Main script for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
# Note: modules are lazily imported to speed up the startup time.
# pylint: disable=relative-beyond-top-level,import-outside-toplevel


def run():
    """Run Requake."""
    from .config.parse_arguments import parse_arguments
    args = parse_arguments()
    from .config.rq_setup import configure, rq_exit
    config = configure(args)
    if config.args.action == 'read_catalog':
        from .catalog import read_catalog
        read_catalog(config)
    if config.args.action == 'scan_catalog':
        from .scan import scan_catalog
        scan_catalog(config)
    if config.args.action == 'scan_templates':
        from .scan import scan_templates
        scan_templates(config)
    if config.args.action == 'plot_pair':
        from .plot import plot_pair
        plot_pair(config)
    if config.args.action == 'build_families':
        from .families import build_families
        build_families(config)
    if config.args.action == 'print_families':
        from .families import print_families
        print_families(config)
    if config.args.action == 'plot_families':
        from .plot import plot_families
        plot_families(config)
    if config.args.action == 'plot_timespans':
        from .plot import plot_timespans
        plot_timespans(config)
    if config.args.action == 'plot_slip':
        from .plot import plot_slip
        plot_slip(config)
    if config.args.action == 'map_families':
        from .plot import map_families
        map_families(config)
    if config.args.action == 'flag_family':
        from .families import flag_family
        flag_family(config)
    if config.args.action == 'build_templates':
        from .families import build_templates
        build_templates(config)
    rq_exit(0)


def main():
    """Main entry point for Requake."""
    try:
        run()
    # pylint: disable=broad-except
    except Exception as e:
        import sys
        import traceback
        from .config.rq_setup import rq_exit
        from . import __version__
        sys.stderr.write("""
# BEGIN TRACEBACK #############################################################
""")
        sys.stderr.write('\n')
        traceback.print_exc()
        sys.stderr.write("""
# END TRACEBACK ###############################################################
""")
        sys.stderr.write("""

Congratulations, you've found a bug in Requake! 🐞

Please report it on https://github.com/SeismicSource/requake/issues
or by email to satriano@ipgp.fr.

Include the following information in your report:

""")
        sys.stderr.write(f'  Requake version: {__version__}\n')
        sys.stderr.write(f'  Python version: {sys.version}\n')
        sys.stderr.write(f'  Platform: {sys.platform}\n')
        sys.stderr.write(f'  Command line: {" ".join(sys.argv)}\n')
        sys.stderr.write(f'  Error message: {str(e)}\n')
        sys.stderr.write('\n')
        sys.stderr.write(
            'Also, please copy and paste the traceback above in your '
            'report.\n\n')
        sys.stderr.write('Thank you for your help!\n\n')
        rq_exit(1)
