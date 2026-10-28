# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Catalog-based repeater scan for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import sys
import time
import logging
import contextlib
from concurrent.futures.process import BrokenProcessPool
from ..config import (
    config,
    rq_exit,
)
from ..config.run_params import (
    parameters_digest,
    parameters_json,
    scan_parameters,
)
from ..database.catalogs import CatalogNotFoundError, resolve_catalog_id
from ..database.db import get_db_path
from ..database.scans import (
    SCAN_STATUS_COMPLETE,
    SCAN_STATUS_FAILED,
    ScanNotFoundError,
    create_scan,
    find_scan_by_hash,
    finish_scan,
    read_scan,
    reset_scan,
)
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..database.pairs import write_pair_records
from ..database.trace_metadata import store_trace_metadata_from_inventory
from ..waveforms import (
    load_inventory,
    NoMetadataError, MetadataMismatchError,
)
from .scan_catalog_pairs import (
    build_valid_pair_indices,
    load_existing_pair_ids,
    log_pair_grouping_stats,
    mask_existing_pair_indices,
)
from .scan_catalog_helpers import (
    log_memory_usage,
    resolve_scan_catalog_nprocs,
)
from .slurm_diagnostics import slurm_get_context, slurm_log_runtime_context
from .scan_catalog_workers import (
    process_valid_pair_indices,
)

logger = logging.getLogger('scan_catalog')


def _ask_scan_action(scan_row):
    """Ask the user what to do with an existing identical scan."""
    args = config.args
    scan_id = int(scan_row['scan_id'])
    if args.force:
        return 'replace'
    if args.force_continue:
        return 'continue'
    message = (
        f'[rq:scan] A scan with the same parameters already exists '
        f'as scan {scan_id} on catalog {int(scan_row["catalog_id"])}.'
    )
    choice_help = (
        '[rq:scan] You can replace it, continue it, or add a new scan.'
    )
    if not sys.stdin.isatty():
        logger.error(message)
        logger.error(
            '[rq:scan] Cannot prompt in non-interactive mode. '
            'Use --force to replace it, --force-continue to resume it, '
            'or --scan-id with a new scan id to add a new scan.'
        )
        rq_exit(1)
    logger.warning(message)
    logger.warning(choice_help)
    prompt = (
        'Choose action: [r]eplace, [c]ontinue, [n]ew, [a]bort '
        '(default: abort): '
    )
    choices = {
        'r': 'replace',
        'replace': 'replace',
        'c': 'continue',
        'continue': 'continue',
        'n': 'new',
        'new': 'new',
        'a': 'abort',
        'abort': 'abort',
    }
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            return 'abort'
        action = choices.get(answer)
        if action is not None:
            return action
        print('Invalid choice. Please type r, c, n, or a.')


def _process_pairs(catalog, scan_id, continue_scan=False, slurm_context=None):
    """Process event pairs.

    :return: number of analyzed pairs and number of skipped pairs
    :rtype: tuple
    """
    if not continue_scan:
        write_pair_records([], scan_id, append=False)
    # Ensure inventory is loaded in the parent process before parent-side
    # writes, so trace_metadata rows keep full interval metadata in
    # parallel mode as in serial mode.
    try:
        load_inventory()
    except (NoMetadataError, MetadataMismatchError) as msg:
        logger.error(msg)
        rq_exit(1)
    # Write trace metadata immediately after tables are created so that
    # the DB is populated even when no pairs are found (e.g. all
    # waveform fetches fail).  Uses the inventory already in config.
    trace_ids = (
        [config.args.traceid]
        if getattr(config.args, 'traceid', None) is not None
        else list(config.catalog_trace_id)
    )
    store_trace_metadata_from_inventory(trace_ids, scan_id)
    nevents = len(catalog)
    initial_npairs = nevents * (nevents - 1) // 2
    logger.info('[rq:scan] Building valid event pairs...')
    t_grouping_start = time.monotonic()
    valid_pair_idx = build_valid_pair_indices(catalog)
    grouping_dt = time.monotonic() - t_grouping_start
    logger.info(
        f'[rq:scan] Valid-pair spatial grouping '
        f'completed in {grouping_dt:.1f}s'
    )
    skipped_npairs = 0
    candidate_npairs = len(valid_pair_idx)
    if continue_scan:
        logger.info(
            '[rq:scan] Continue-scan mode: loading existing pairs '
            'for pre-processing mask'
        )
        t_resume_filter_start = time.monotonic()
        existing_pair_ids = load_existing_pair_ids(catalog, scan_id)
        valid_pair_idx, skipped_npairs = mask_existing_pair_indices(
            valid_pair_idx,
            existing_pair_ids,
            nevents,
        )
        # Free the pair-ID set immediately after masking.
        # It can be large and would otherwise stay in scope
        # for the entire pair-processing phase.
        del existing_pair_ids
        resume_filter_dt = time.monotonic() - t_resume_filter_start
        logger.info(
            f'[rq:scan] Loading existing pair IDs and applying mask '
            f'completed in {resume_filter_dt:.1f}s'
        )
    npairs = len(valid_pair_idx)
    total_valid_pairs = skipped_npairs + npairs
    nprocs = resolve_scan_catalog_nprocs(npairs, slurm_context or {})
    ratio = npairs / initial_npairs if initial_npairs > 0 else 0.0
    logger.info(f'[rq:scan] Initial pairs: {initial_npairs:n}')
    logger.info(f'[rq:scan] Candidate pairs: {candidate_npairs:n}')
    logger.info(f'[rq:scan] Final pairs: {npairs:n}')
    logger.info(f'[rq:scan] Pair ratio: {ratio:.6f} ({ratio:.2%})')
    log_pair_grouping_stats(valid_pair_idx)
    log_memory_usage(prefix='[parent before processing]')
    logger.info(
        f'[rq:scan] Processing {npairs:n} event pairs '
        f'({skipped_npairs:n}/{total_valid_pairs:n} already processed)'
    )
    analyzed_npairs = process_valid_pair_indices(
        catalog,
        valid_pair_idx,
        npairs,
        initial_processed=skipped_npairs,
        total_pairs=total_valid_pairs,
        nprocs=nprocs,
        slurm_context=slurm_context,
        scan_id=scan_id,
    )
    if continue_scan:
        logger.info(
            f'[rq:scan] Skipped {skipped_npairs:n} event pairs '
            f'already present in the database'
        )
    log_memory_usage(prefix='[parent after processing]')
    return analyzed_npairs, skipped_npairs


def _select_scan_action(catalog_id, params_hash):
    """Return the scan id to use and whether to continue an existing scan."""
    args = config.args
    requested = getattr(args, 'scan_id', None)
    if requested is not None:
        try:
            read_scan(requested)
        except ScanNotFoundError as msg:
            logger.error(f'[rq:scan] {msg}')
            rq_exit(1)
        action = 'replace' if args.force else 'continue'
        return int(requested), action
    existing = find_scan_by_hash(params_hash, catalog_id=catalog_id)
    if existing is None:
        return None, 'new'
    return int(existing['scan_id']), _ask_scan_action(existing)


def scan_catalog():
    """Perform cross-correlation on catalog events."""
    slurm_context = slurm_get_context()
    slurm_log_runtime_context(slurm_context)
    try:
        catalog_id = resolve_catalog_id(
            getattr(config.args, 'catalog_id', None)
        )
    except CatalogNotFoundError as msg:
        logger.error(f'[rq:scan] {msg}')
        rq_exit(1)
    try:
        catalog = read_stored_catalog(catalog_id=catalog_id)
    except (ValueError, FileNotFoundError) as msg:
        logger.error(f'[rq:scan] {msg}')
        rq_exit(1)
    try:
        t_fix_start = time.monotonic()
        fix_non_locatable_events(catalog)
        fix_dt = time.monotonic() - t_fix_start
        if fix_dt > 1.0:
            logger.info(
                f'[rq:scan] Fixed non-locatable events in {fix_dt:.1f}s'
            )
    except MetadataMismatchError as msg:
        logger.error(f'[rq:scan] {msg}')
        rq_exit(1)
    nevents = len(catalog)
    if nevents < 2:
        logger.error(
            '[rq:scan] Not enough events in catalog. '
            'You need at least 2 events to run the scan.')
        rq_exit(1)
    logger.info(
        f'[rq:scan] {nevents:n} events read from catalog {catalog_id} '
        f'in db file {get_db_path()}'
    )
    params = scan_parameters()
    params_hash = parameters_digest(params)
    scan_id, action = _select_scan_action(catalog_id, params_hash)
    if action == 'abort':
        logger.info('[rq:scan] Scan aborted by user')
        rq_exit(0)
    continue_scan = action == 'continue'
    if action == 'replace':
        reset_scan(
            scan_id,
            params_hash,
            parameters_json(params),
            nevents=nevents,
            label=getattr(config.args, 'label', None),
        )
        logger.info(f'[rq:scan] Replacing scan {scan_id}')
    elif continue_scan:
        logger.info(f'[rq:scan] Continuing scan {scan_id}')
    else:
        scan_id = create_scan(
            catalog_id,
            params_hash,
            parameters_json(params),
            label=getattr(config.args, 'label', None),
            nevents=nevents,
        )
        logger.info(f'[rq:scan] Scan stored as scan {scan_id}')
    npairs = None
    skipped_npairs = None
    status = SCAN_STATUS_FAILED
    try:
        npairs, skipped_npairs = _process_pairs(
            catalog,
            scan_id,
            continue_scan=continue_scan,
            slurm_context=slurm_context,
        )
        status = SCAN_STATUS_COMPLETE
    except BrokenProcessPool as err:
        logger.error(
            '[rq:scan] Parallel scan stopped because a worker process '
            'terminated unexpectedly.'
        )
        logger.debug(f'Broken process pool details: {err}')
        rq_exit(1, abort=True)
    finally:
        with contextlib.suppress(Exception):
            stored = None if npairs is None else npairs + skipped_npairs
            finish_scan(
                scan_id,
                npairs_stored=stored,
                npairs_analyzed=npairs,
                status=status,
            )
    logger.info(f'[rq:scan] Processed {npairs:n} event pairs')
    logger.info(
        f'[rq:scan] Done! Scan {scan_id} written to {get_db_path()}'
    )
