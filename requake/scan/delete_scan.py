# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Delete a catalog scan and everything built from it.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import sys
from ..config import config, rq_exit
from ..config.utils import confirm_action
from ..database.scans import (
    ScanNotFoundError,
    delete_scan_row,
    summarize_scan_delete,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _report(summary, verb):
    """Report what the deletion involves."""
    logger.warning(
        f'Scan {summary["scan_id"]} of catalog {summary["catalog_id"]}: '
        f'{summary["pairs"]} pairs, {summary["builds"]} family builds, '
        f'{summary["families"]} family rows, '
        f'{summary["detections"]} template detections'
    )
    logger.warning(f'All of the above {verb}')


def _confirm():
    """Ask the user to confirm a destructive operation."""
    if not sys.stdin.isatty():
        logger.error(
            'Cannot ask for confirmation in non-interactive mode; '
            'use -f/--force to delete without confirmation'
        )
        rq_exit(1)
    if not confirm_action('Delete this scan and everything built on it?'):
        logger.info('Deletion aborted by user')
        rq_exit(0)


def delete_scan():
    """Delete a catalog scan and everything built from it."""
    scan_id = config.args.scan_id
    try:
        summary = summarize_scan_delete(scan_id)
    except ScanNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    dry_run = getattr(config.args, 'dry_run', False)
    _report(summary, 'would be deleted' if dry_run else 'will be deleted')
    if dry_run:
        logger.info('Dry run: the database was not modified')
        return
    if not getattr(config.args, 'force', False):
        _confirm()
    delete_scan_row(scan_id)
    logger.info(f'Scan {scan_id} deleted')
