# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print the family builds stored in the database to screen.

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
from ..database.family_builds import (
    FamilyBuildNotFoundError,
    read_family_build,
    read_family_builds,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _print_details(row):
    """Print the details of one family build."""
    cc_min = row['cc_min']
    rows = [
        ('build id', int(row['build_id'])),
        ('scan id', int(row['scan_id'])),
        ('label', row['label'] or ''),
        ('created', format_timestamp(row['created_at'])),
        ('finished', format_timestamp(row['finished_at'])),
        ('status', row['status']),
        ('method', row['method']),
        ('cc min', 'n/a' if cc_min is None else f'{cc_min:g}'),
        ('families', format_count(row['nfamilies'])),
        ('events', format_count(row['nevents'])),
        ('params hash', row['params_hash']),
        ('requake version', row['requake_version'] or ''),
    ]
    rows.extend(format_parameters(row['params_json']))
    print_key_value_table(rows, detail_title='Family Build Details')


def print_family_builds():
    """Print the family builds stored in the database to screen."""
    build_id = getattr(config.args, 'build_id', None)
    try:
        if build_id is not None:
            _print_details(read_family_build(build_id))
            return
        rows = read_family_builds()
    except (FamilyBuildNotFoundError, FileNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if not rows:
        logger.error(f'No family build found in db file {get_db_path()}')
        rq_exit(1)
    table = [
        [
            int(row['build_id']),
            int(row['scan_id']),
            row['label'] or '',
            format_timestamp(row['created_at']),
            row['status'],
            row['method'],
            'n/a' if row['cc_min'] is None else f'{row["cc_min"]:g}',
            format_count(row['nfamilies']),
            format_count(row['nevents']),
        ]
        for row in rows
    ]
    headers_fmt = [
        ('id', None),
        ('scan', None),
        ('label', None),
        ('created', None),
        ('status', None),
        ('method', None),
        ('cc min', None),
        ('families', None),
        ('events', None),
    ]
    _display_table(
        headers_fmt, table,
        row_label='Family builds',
        copy_label='id',
        detail_title='Family Build Details',
    )
