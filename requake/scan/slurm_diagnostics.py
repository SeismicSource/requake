# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Low-overhead diagnostics for SLURM cluster runs.

All instrumentation is guarded by :func:`slurm_is_active` so that
local development runs are completely unaffected.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import os
from contextlib import suppress

logger = logging.getLogger('scan_catalog.slurm_diag')

# ---------------------------------------------------------------------------
# SLURM detection
# ---------------------------------------------------------------------------


def slurm_is_active():
    """Return ``True`` when the process is running inside a SLURM job."""
    return 'SLURM_JOB_ID' in os.environ


def _slurm_job_id():
    """Return the SLURM job ID or ``None``."""
    return os.environ.get('SLURM_JOB_ID')


# ---------------------------------------------------------------------------
# SLURM constants
# ---------------------------------------------------------------------------

SLURM_CONTEXT_KEYS = (
    'SLURM_JOB_ID',
    'SLURM_JOB_NAME',
    'SLURM_CLUSTER_NAME',
    'SLURM_CPUS_PER_TASK',
    'SLURM_CPUS_ON_NODE',
    'SLURM_JOB_CPUS_PER_NODE',
    'SLURM_NTASKS',
    'SLURM_PROCID',
    'SLURM_NODELIST',
    'SLURM_MEM_PER_CPU',
    'SLURM_MEM_PER_NODE',
)

SLURM_PROGRESS_KEYS = (
    'SLURM_JOB_ID',
    'SLURM_PROCID',
    'SLURM_NODELIST',
)

SLURM_CPU_SOURCES = (
    'SLURM_CPUS_PER_TASK',
    'SLURM_CPUS_ON_NODE',
    'SLURM_JOB_CPUS_PER_NODE',
)


# ---------------------------------------------------------------------------
# SLURM context and helpers
# ---------------------------------------------------------------------------


def slurm_get_context():
    """Return current Slurm environment variables that are set."""
    context = {}
    for key in SLURM_CONTEXT_KEYS:
        value = os.environ.get(key)
        if value:
            context[key] = value
    return context


def slurm_parse_cpu_count(value):
    """Parse a Slurm CPU count value into an integer."""
    if value is None:
        return None
    with suppress(ValueError):
        return int(value)
    head = value.split('(', 1)[0].split(',', 1)[0].strip()
    with suppress(ValueError):
        return int(head)
    return None


def slurm_progress_suffix(slurm_context):
    """Build compact Slurm suffix for periodic progress logs."""
    if not slurm_context:
        return ''
    details = ', '.join(
        f'{key}={slurm_context[key]}'
        for key in SLURM_PROGRESS_KEYS
        if key in slurm_context
    )
    return f', {details}' if details else ''


# ---------------------------------------------------------------------------
# Startup and context logging
# ---------------------------------------------------------------------------


def slurm_log_startup():
    """Emit a single startup line showing whether diagnostics are active."""
    enabled = slurm_is_active()
    job_id = _slurm_job_id() if enabled else None
    logger.info(
        f'[rq:slurm] DIAGNOSTICS enabled={str(enabled).lower()} '
        f'job_id={job_id}'
    )


def slurm_log_runtime_context(slurm_context):
    """Log Slurm runtime details when available."""
    slurm_log_startup()
    if not slurm_context:
        return
    details = ', '.join(
        f'{key}={value}'
        for key, value in sorted(slurm_context.items())
    )
    logger.info(f'[rq:slurm] RUNTIME_CONTEXT {details}')
