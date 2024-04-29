# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generic printer functions for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import os
import csv
import contextlib
import logging
from tabulate import tabulate
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def generic_printer(config, rows, headers_fmt, print_headers=True):
    """
    A generic printer function for Requake.

    :param config: Configuration object.
    :type config: config.Config
    :param rows: Rows to print.
    :type rows: list of rows
    :param headers_fmt: Headers and format strings.
    :type headers_fmt: list of tuples of str
    """
    headers = [h[0] for h in headers_fmt]
    floatfmt = [h[1] for h in headers_fmt]
    tablefmt = config.args.format
    if tablefmt == 'csv':
        writer = csv.writer(sys.stdout)
        if print_headers:
            # replace newlines with spaces in headers
            headers = [h.replace('\n', ' ') for h in headers]
            writer.writerow(headers)
    elif tablefmt == 'markdown':
        headers = [h.replace('\n', '<br>') for h in headers]
    if tablefmt == 'csv':
        try:
            writer.writerows(rows)
        except BrokenPipeError:
            # Redirect remaining output to devnull to avoid another
            # BrokenPipeError at shutdown
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
    else:
        format_dict = {
            'simple': 'simple',
            'markdown': 'github'
        }
        tablefmt = format_dict[config.args.format]
        with contextlib.suppress(BrokenPipeError):
            kwargs = {
                'headers': headers,
                'floatfmt': floatfmt,
                'tablefmt': tablefmt
            }
            line = tabulate(rows, **kwargs)
            if not print_headers:
                line = line.rsplit('\n', maxsplit=1)[-1]
            print(line)
