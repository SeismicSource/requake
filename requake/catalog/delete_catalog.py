# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Delete a catalog and everything built from it.

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
from ..database.catalogs import (
    CatalogNotFoundError,
    delete_catalog_row,
    summarize_catalog_delete,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _report(summary, verb):
    """Report what the deletion involves."""
    logger.warning(
        f'Catalog {summary["catalog_id"]}: {summary["events"]} events, '
        f'{summary["scans"]} scans, {summary["pairs"]} pairs, '
        f'{summary["builds"]} family builds, {summary["families"]} '
        f'family rows, {summary["detections"]} template detections'
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
    if not confirm_action('Delete this catalog and everything built on it?'):
        logger.info('Deletion aborted by user')
        rq_exit(0)


def delete_catalog():
    """Delete a catalog and everything built from it."""
    catalog_id = config.args.catalog_id
    try:
        summary = summarize_catalog_delete(catalog_id)
    except CatalogNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    dry_run = getattr(config.args, 'dry_run', False)
    _report(summary, 'would be deleted' if dry_run else 'will be deleted')
    if dry_run:
        logger.info('Dry run: the database was not modified')
        return
    if not getattr(config.args, 'force', False):
        _confirm()
    delete_catalog_row(catalog_id)
    logger.info(f'Catalog {catalog_id} deleted')
