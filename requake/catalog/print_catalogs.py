# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print the catalogs stored in the database to screen.

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
from ..database.catalogs import (
    CatalogNotFoundError,
    count_catalog_scans,
    count_stored_events,
    read_catalog_row,
    read_catalogs,
)
from ..database.db import get_db_path
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _print_details(row):
    """Print the details of one catalog."""
    catalog_id = int(row['catalog_id'])
    rows = [
        ('catalog id', catalog_id),
        ('label', row['label'] or ''),
        ('created', format_timestamp(row['created_at'])),
        ('source', row['source'] or ''),
        ('events', format_count(count_stored_events(catalog_id))),
        ('scans', format_count(count_catalog_scans(catalog_id))),
        ('params hash', row['params_hash']),
        ('requake version', row['requake_version'] or ''),
    ]
    rows.extend(format_parameters(row['params_json']))
    print_key_value_table(rows, detail_title='Catalog Details')


def print_catalogs():
    """Print the catalogs stored in the database to screen."""
    catalog_id = getattr(config.args, 'catalog_id', None)
    try:
        if catalog_id is not None:
            _print_details(read_catalog_row(catalog_id))
            return
        rows = read_catalogs()
    except (CatalogNotFoundError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if not rows:
        logger.error(f'No catalog found in db file {get_db_path()}')
        rq_exit(1)
    table = [
        [
            int(row['catalog_id']),
            row['label'] or '',
            format_timestamp(row['created_at']),
            format_count(row['nevents']),
            format_count(count_catalog_scans(int(row['catalog_id']))),
            row['source'] or '',
        ]
        for row in rows
    ]
    headers_fmt = [
        ('id', None),
        ('label', None),
        ('created', None),
        ('events', None),
        ('scans', None),
        ('source', None),
    ]
    _display_table(
        headers_fmt, table,
        row_label='Catalogs',
        copy_label='id',
        detail_title='Catalog Details',
    )
