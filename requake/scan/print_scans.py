# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print the catalog scans stored in the database to screen.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit
from ..config.generic_printer import (
    _display_table,
    format_count,
    format_timestamp,
    print_key_value_table,
)
from ..config.run_params import format_parameters
from ..database.db import get_db_path
from ..database.scans import (
    ScanNotFoundError,
    read_scan,
    read_scans,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _print_details(row):
    """Print the details of one scan."""
    rows = [
        ('scan id', int(row['scan_id'])),
        ('catalog id', int(row['catalog_id'])),
        ('label', row['label'] or ''),
        ('created', format_timestamp(row['created_at'])),
        ('finished', format_timestamp(row['finished_at'])),
        ('status', row['status']),
        ('events', format_count(row['nevents'])),
        ('pairs stored', format_count(row['npairs_stored'])),
        ('pairs analyzed', format_count(row['npairs_analyzed'])),
        ('params hash', row['params_hash']),
        ('requake version', row['requake_version'] or ''),
    ]
    rows.extend(format_parameters(row['params_json']))
    print_key_value_table(rows, detail_title='Scan Details')


def print_scans():
    """Print the catalog scans stored in the database to screen."""
    scan_id = getattr(config.args, 'scan_id', None)
    try:
        if scan_id is not None:
            _print_details(read_scan(scan_id))
            return
        rows = read_scans()
    except (ScanNotFoundError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if not rows:
        logger.error(f'No catalog scan found in db file {get_db_path()}')
        rq_exit(1)
    table = [
        [
            int(row['scan_id']),
            int(row['catalog_id']),
            row['label'] or '',
            format_timestamp(row['created_at']),
            row['status'],
            format_count(row['nevents']),
            format_count(row['npairs_stored']),
            format_count(row['npairs_analyzed']),
        ]
        for row in rows
    ]
    headers_fmt = [
        ('id', None),
        ('catalog', None),
        ('label', None),
        ('created', None),
        ('status', None),
        ('events', None),
        ('pairs', None),
        ('analyzed', None),
    ]
    _display_table(
        headers_fmt, table,
        row_label='Scans',
        copy_label='id',
        detail_title='Scan Details',
    )
