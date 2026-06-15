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
from concurrent.futures.process import BrokenProcessPool
from ..config import (
    config,
    rq_exit,
)
from ..database.db import get_db_path
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..database.pairs import (
    count_pairs,
    write_pair_records,
)
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


def _ask_existing_pairs_action():
    """Ask the user whether to overwrite or continue an existing scan."""
    args = config.args
    if args.force:
        return 'overwrite'
    if args.force_continue:
        return 'continue'
    if not sys.stdin.isatty():
        logger.error(
            f'[rq:scan] Found existing event pairs '
            f'in db file {get_db_path()}.'
        )
        logger.error(
            '[rq:scan] Cannot prompt in non-interactive mode. '
            'Use --force to overwrite or --force-continue to resume.'
        )
        rq_exit(1)
    logger.warning(
        f'[rq:scan] Found existing event pairs '
        f'in db file {get_db_path()}.'
    )
    logger.warning(
        '[rq:scan] You can overwrite them and restart, or continue '
        'from where the previous scan stopped.'
    )
    prompt = (
        'Choose action: [o]verwrite, [c]ontinue, [a]bort '
        '(default: abort): '
    )
    choices = {
        'o': 'overwrite',
        'overwrite': 'overwrite',
        'c': 'continue',
        'continue': 'continue',
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
        print('Invalid choice. Please type o, c, or a.')


def _process_pairs(catalog, continue_scan=False, slurm_context=None):
    """Process event pairs."""
    if not continue_scan:
        write_pair_records([], append=False)
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
    store_trace_metadata_from_inventory(trace_ids)
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
        existing_pair_ids = load_existing_pair_ids(catalog)
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
    )
    if continue_scan:
        logger.info(
            f'[rq:scan] Skipped {skipped_npairs:n} event pairs '
            f'already present in the database'
        )
    log_memory_usage(prefix='[parent after processing]')
    return analyzed_npairs


def scan_catalog():
    """Perform cross-correlation on catalog events."""
    slurm_context = slurm_get_context()
    slurm_log_runtime_context(slurm_context)
    try:
        catalog = read_stored_catalog()
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
        f'[rq:scan] {nevents:n} events read from db file '
        f'{get_db_path()}'
    )
    continue_scan = False
    if count_pairs() > 0:
        action = _ask_existing_pairs_action()
        if action == 'abort':
            logger.info('[rq:scan] Scan aborted by user')
            rq_exit(0)
        continue_scan = action == 'continue'
    try:
        npairs = _process_pairs(
            catalog,
            continue_scan=continue_scan,
            slurm_context=slurm_context,
        )
    except BrokenProcessPool as err:
        logger.error(
            '[rq:scan] Parallel scan stopped because a worker process '
            'terminated unexpectedly.'
        )
        logger.debug(f'Broken process pool details: {err}')
        rq_exit(1, abort=True)
    logger.info(f'[rq:scan] Processed {npairs:n} event pairs')
    logger.info(f'[rq:scan] Done! Output written to {get_db_path()}')
