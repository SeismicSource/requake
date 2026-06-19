# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generic printer functions for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
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
from .config import config
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def generic_printer(rows, headers_fmt, print_headers=True):
    """
    Print rows using the configured output format.

    :param rows: Rows to print.
    :type rows: list of rows
    :param headers_fmt: Headers and format strings.
    :type headers_fmt: list of tuples of str
    """
    headers = [h[0] for h in headers_fmt]
    # Replace None with a safe default so tabulate never receives
    # None as a format specifier (crashes on float columns).
    floatfmt = [
        h[1] if h[1] is not None else '.6g' for h in headers_fmt
    ]
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


def _display_table(headers_fmt, rows=None, data_source=None,
                   row_label='Rows', copy_label=None,
                   copy_fn=None, detail_title='Row Details',
                   print_headers=True):
    """
    Display a table using the interactive curses pager.

    When stdout is a TTY (and ``--no-pager`` is not set), the
    interactive pager is used.  Otherwise the table is printed
    to stdout via :func:`generic_printer`.

    :param headers_fmt: Headers and format strings
        (list of (name, fmt) tuples).
    :param rows: In-memory rows (list of lists).  Ignored when
        *data_source* is given.
    :param data_source: Optional :class:`~requake.pager.DataSource`
        for database-backed pagination.
    :param row_label: Label for rows in the pager status bar.
    :param copy_label: Label for the copy-to-clipboard message.
    :param copy_fn: Optional callable ``copy_fn(row) -> str`` for
        custom copy behaviour.
    :param detail_title: Title for the detail popup.
    :param print_headers: Whether to include the header row
        (used for iterative printing fallback).
    """
    # Determine whether to use the pager
    use_pager = sys.stdout.isatty()
    if use_pager:
        no_pager = getattr(config.args, 'no_pager', False)
        if no_pager:
            use_pager = False

    if use_pager:
        from ..pager import (
            display_table_pager,
            PagerException,
            ListDataSource,
        )
        with contextlib.suppress(PagerException):
            if data_source is not None:
                ds = data_source
            else:
                fields = [h[0].replace('\n', ' ') for h in headers_fmt]
                ds = ListDataSource(fields, rows or [])
            display_table_pager(
                ds,
                row_label=row_label,
                copy_label=copy_label,
                copy_fn=copy_fn,
                detail_title=detail_title,
            )
            return
    # Fallback: plain-text output via generic_printer
    if data_source is not None:
        # For DB-backed sources, stream rows via generic_printer
        fields = data_source.fields
        total = data_source.total_count
        batch_size = 1000
        for offset in range(0, total, batch_size):
            batch = data_source.get_rows(offset, batch_size, None, True)
            # Rebuild headers_fmt for generic_printer
            batch_headers_fmt = [(f, None) for f in fields]
            generic_printer(
                batch, batch_headers_fmt,
                print_headers=(offset == 0 and print_headers)
            )
    else:
        generic_printer(rows, headers_fmt, print_headers)
