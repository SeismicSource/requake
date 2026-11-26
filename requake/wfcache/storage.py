# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
SQLite-backed waveform cache storage.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import io
import logging
import os
import socket
import time
import atexit
import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path

import numpy as np
from obspy import Stream, UTCDateTime, read

from ..config import config
from ..database.db import execute_with_retry

logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

SCHEMA_VERSION = 1
DEFAULT_FAILURE_MAX_RETRIES = 3
DEFAULT_FAILURE_BACKOFF_S = 600.0
# Lease duration of a claimed prefetch group, in seconds.
DEFAULT_CLAIM_TTL_S = 900.0

WAVEFORM_CACHE_SCHEMA = [
    '''
    CREATE TABLE IF NOT EXISTS cache_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS waveform_cache (
        evid TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        start_time_ns INTEGER NOT NULL,
        end_time_ns INTEGER NOT NULL,
        sampling_rate REAL NOT NULL,
        npts INTEGER NOT NULL,
        data_blob BLOB NOT NULL,
        created_at_ns INTEGER NOT NULL,
        accessed_at_ns INTEGER NOT NULL,
        PRIMARY KEY (evid, trace_id, start_time_ns, end_time_ns)
    )
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_waveform_cache_trace_time '
        'ON waveform_cache (trace_id, start_time_ns, end_time_ns)'
    ),
    '''
    CREATE TABLE IF NOT EXISTS waveform_failures (
        evid TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        start_time_ns INTEGER NOT NULL,
        end_time_ns INTEGER NOT NULL,
        retry_count INTEGER NOT NULL,
        max_retries INTEGER NOT NULL,
        last_error TEXT,
        first_failure_ns INTEGER NOT NULL,
        last_failure_ns INTEGER NOT NULL,
        next_retry_after_ns INTEGER,
        PRIMARY KEY (evid, trace_id, start_time_ns, end_time_ns)
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS prefetch_claims (
        trace_id TEXT NOT NULL,
        start_time_ns INTEGER NOT NULL,
        end_time_ns INTEGER NOT NULL,
        owner TEXT NOT NULL,
        host TEXT,
        pid INTEGER,
        claimed_at_ns INTEGER NOT NULL,
        expires_at_ns INTEGER NOT NULL,
        PRIMARY KEY (trace_id, start_time_ns, end_time_ns)
    )
    ''',
    (
        'CREATE INDEX IF NOT EXISTS idx_prefetch_claims_expires '
        'ON prefetch_claims (expires_at_ns)'
    ),
]

# One SQLite connection is cached per (path, pid) so that every process
# reuses the same handle.  The pid guard is essential: after os.fork()
# (used by ProcessPoolExecutor), the child inherits the parent's file
# descriptors but must NOT use them — we open a fresh connection instead.
_CACHE_CONN = None
_CACHE_CONN_PATH = None
_CACHE_CONN_PID = None
_CACHE_SCHEMA_VERIFIED = set()
_CACHE_BATCH_ACTIVE = False
# Cached return value of _failure_limits() for this process.
_FAILURE_LIMITS = None
# Identity of this process in the prefetch_claims table.
_OWNER_TOKEN = None


def _claim_owner_token():
    """Return the stable owner token for this process."""
    global _OWNER_TOKEN  # pylint: disable=global-statement
    if _OWNER_TOKEN is None:
        _OWNER_TOKEN = (
            f'{socket.gethostname()}:{os.getpid()}:'
            f'{uuid.uuid4().hex[:8]}'
        )
    return _OWNER_TOKEN


def _immediate_transaction(conn, work, name):
    """
    Run *work* inside a ``BEGIN IMMEDIATE`` transaction, retrying on locks.

    ``work`` must be safe to run more than once, since a transient
    ``database is locked`` error restarts the whole transaction.

    :param conn: SQLite connection
    :param work: callable performing the transaction statements
    :param name: operation name used in error messages
    :return: whatever *work* returns
    """

    def _run():
        conn.execute('BEGIN IMMEDIATE')
        try:
            result = work()
        except BaseException:
            with suppress(sqlite3.Error):
                conn.rollback()
            raise
        conn.commit()
        return result

    return execute_with_retry(_run, name)


def _write_transaction(conn, work, name):
    """
    Run *work* atomically, respecting an already open write batch.

    Inside a batch the caller already holds the write lock, so no new
    transaction is started and the commit is deferred to the batch.
    """
    if _CACHE_BATCH_ACTIVE:
        return work()
    return _immediate_transaction(conn, work, name)


def _utc_to_ns(value):
    """Convert UTCDateTime to epoch nanoseconds."""
    return int(round(float(value.timestamp) * 1e9))


def _ns_to_utc(value):
    """Convert epoch nanoseconds to UTCDateTime."""
    return UTCDateTime(float(value) / 1e9)


def get_waveform_cache_db_path():
    """Return path to the SQLite waveform cache database file."""
    if not bool(getattr(config, 'catalog_waveform_disk_cache_enabled', True)):
        return None
    args = getattr(config, 'args', None)
    outdir = getattr(args, 'outdir', None)
    if outdir is None:
        return None
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)
    return outdir_path / 'waveform_cache.sqlite'


def _connect_cache_db(cache_path):
    """Open a SQLite connection with conservative tuning."""
    conn = sqlite3.connect(str(cache_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    # Switching to WAL needs a short exclusive lock; a peer creating the
    # file at the same time may hold it, hence the retry.
    execute_with_retry(
        lambda: conn.execute('PRAGMA journal_mode=WAL'),
        'enable WAL journal mode',
    )
    conn.execute('PRAGMA synchronous=NORMAL')
    _ensure_schema(conn, str(cache_path))
    return conn


def _close_cached_connection():
    """Close the process-local cached SQLite connection."""
    global _CACHE_CONN  # pylint: disable=global-statement
    global _CACHE_CONN_PATH  # pylint: disable=global-statement
    global _CACHE_CONN_PID  # pylint: disable=global-statement

    if _CACHE_CONN is not None:
        _CACHE_CONN.close()
    _CACHE_CONN = None
    _CACHE_CONN_PATH = None
    _CACHE_CONN_PID = None


atexit.register(_close_cached_connection)


def _get_cache_connection(cache_path):
    """Return process-local cached SQLite connection for cache_path."""
    global _CACHE_CONN  # pylint: disable=global-statement
    global _CACHE_CONN_PATH  # pylint: disable=global-statement
    global _CACHE_CONN_PID  # pylint: disable=global-statement

    current_pid = os.getpid()
    if (
        _CACHE_CONN is not None
        and _CACHE_CONN_PATH == cache_path
        and _CACHE_CONN_PID == current_pid
    ):
        return _CACHE_CONN
    _close_cached_connection()
    _CACHE_CONN = _connect_cache_db(cache_path)
    _CACHE_CONN_PATH = cache_path
    _CACHE_CONN_PID = current_pid
    return _CACHE_CONN


def _ensure_schema(conn, cache_path_str):
    """Create tables and validate schema version."""
    if cache_path_str in _CACHE_SCHEMA_VERIFIED:
        return
    execute_with_retry(
        lambda: _apply_schema(conn, cache_path_str),
        'initialize waveform-cache schema',
    )
    _CACHE_SCHEMA_VERIFIED.add(cache_path_str)


def _apply_schema(conn, cache_path_str):
    """Create missing tables and set the schema version when unset."""
    for statement in WAVEFORM_CACHE_SCHEMA:
        conn.execute(statement)
    version = int(conn.execute('PRAGMA user_version').fetchone()[0])
    if version not in (0, SCHEMA_VERSION):
        raise RuntimeError(
            'Unsupported waveform-cache schema version: '
            f'{version} (expected {SCHEMA_VERSION}).'
        )
    if version == 0:
        conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        conn.execute(
            '''
            INSERT OR REPLACE INTO cache_meta (key, value)
            VALUES ('schema_version', ?)
            ''',
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


def _cache_key(evid, trace_id, starttime, endtime):
    """Build SQL key tuple for waveform cache tables."""
    return (
        str(evid),
        str(trace_id),
        _utc_to_ns(starttime),
        _utc_to_ns(endtime),
    )


def _trace_to_mseed_blob(tr):
    """Serialize trace to MiniSEED bytes using STEIM2 integer encoding."""
    tr_cache = tr.copy()
    mseed_stats = getattr(tr_cache.stats, 'mseed', None)
    if mseed_stats is not None:
        mseed_stats.pop('encoding', None)
    data = np.asarray(tr_cache.data)
    if not np.issubdtype(data.dtype, np.integer):
        data = np.rint(data)
    data = np.clip(data, np.iinfo(np.int32).min, np.iinfo(np.int32).max)
    tr_cache.data = data.astype(np.int32)
    stream = Stream([tr_cache])
    buffer = io.BytesIO()
    stream.write(buffer, format='MSEED', encoding='STEIM2')
    return buffer.getvalue()


def read_waveform_from_cache(evid, trace_id, starttime, endtime):
    """Read a waveform from SQLite cache, returning None on miss."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return None
    key = _cache_key(evid, trace_id, starttime, endtime)
    req_start_ns = key[2]
    req_end_ns = key[3]
    conn = _get_cache_connection(cache_path)
    row = conn.execute(
        '''
        SELECT data_blob, start_time_ns, end_time_ns
        FROM waveform_cache
        WHERE evid = ? AND trace_id = ?
            AND start_time_ns = ? AND end_time_ns = ?
        ''',
        key,
    ).fetchone()
    # Exact-match miss: try a covering-window lookup with ±10 s
    # tolerance.  This handles cases where the prefetch stored a
    # slightly different time window (e.g. because of config changes
    # or nanosecond rounding in _utc_to_ns).
    if row is None:
        row = conn.execute(
            '''
            SELECT data_blob, start_time_ns, end_time_ns
            FROM waveform_cache
            WHERE evid = ? AND trace_id = ?
                AND start_time_ns <= ? + 10000000000
                AND end_time_ns + 10000000000 >= ?
            ORDER BY (end_time_ns - start_time_ns) ASC
            LIMIT 1
            ''',
            (
                key[0],
                key[1],
                req_start_ns,
                req_end_ns,
            ),
        ).fetchone()
    if row is None:
        return None
    t_deser_start = time.monotonic()
    st = read(io.BytesIO(row['data_blob']), format='MSEED')
    deser_dt = time.monotonic() - t_deser_start
    if not st:
        return None
    tr = st[0]
    if (
        int(row['start_time_ns']) != req_start_ns
        or int(row['end_time_ns']) != req_end_ns
    ):
        t_trim_start = time.monotonic()
        tr = tr.copy()
        tr.trim(starttime=starttime, endtime=endtime)
        trim_dt = time.monotonic() - t_trim_start
        if tr.stats.npts <= 0:
            return None
    else:
        trim_dt = 0.0
    total_dt = deser_dt + trim_dt
    if total_dt > 1.0:
        logger.warning(
            '[rq:perf] Slow cache read: evid=%s trace_id=%s '
            'deser=%.2fs trim=%.2fs npts=%d',
            evid, trace_id, deser_dt, trim_dt, tr.stats.npts,
        )
    return tr


def is_waveform_cached(evid, trace_id, starttime, endtime):
    """
    Return True if the window is present in the positive cache.

    Cheaper than :func:`read_waveform_from_cache`, which deserializes
    the MiniSEED blob: this only checks for the row, using the same
    exact-match-then-covering-window lookup.
    """
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return False
    key = _cache_key(evid, trace_id, starttime, endtime)
    conn = _get_cache_connection(cache_path)
    row = conn.execute(
        '''
        SELECT 1 FROM waveform_cache
        WHERE evid = ? AND trace_id = ?
            AND start_time_ns = ? AND end_time_ns = ?
        ''',
        key,
    ).fetchone()
    if row is not None:
        return True
    row = conn.execute(
        '''
        SELECT 1 FROM waveform_cache
        WHERE evid = ? AND trace_id = ?
            AND start_time_ns <= ? + 10000000000
            AND end_time_ns + 10000000000 >= ?
        LIMIT 1
        ''',
        key,
    ).fetchone()
    return row is not None


def write_waveform_to_cache(evid, trace_id, starttime, endtime, tr):
    """Write one waveform window to SQLite cache."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return False
    blob = _trace_to_mseed_blob(tr)
    key = _cache_key(evid, trace_id, starttime, endtime)
    now_ns = _utc_to_ns(UTCDateTime())
    conn = _get_cache_connection(cache_path)
    cursor = conn.execute(
        '''
        INSERT OR IGNORE INTO waveform_cache (
            evid,
            trace_id,
            start_time_ns,
            end_time_ns,
            sampling_rate,
            npts,
            data_blob,
            created_at_ns,
            accessed_at_ns
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            *key,
            float(tr.stats.sampling_rate),
            int(tr.stats.npts),
            sqlite3.Binary(blob),
            now_ns,
            now_ns,
        ),
    )
    # During a batched-write transaction (used by wfcache prefetch),
    # defer commit to commit_cache_write_batch().  Outside of a batch
    # we commit immediately so that other processes / threads see the
    # new row right away.
    if not _CACHE_BATCH_ACTIVE:
        conn.commit()
    return cursor.rowcount > 0


def write_cache_meta(key, value):
    """Store a key-value pair in cache_meta."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return
    conn = _get_cache_connection(cache_path)
    _write_transaction(
        conn,
        lambda: conn.execute(
            '''
            INSERT OR REPLACE INTO cache_meta (key, value)
            VALUES (?, ?)
            ''',
            (str(key), str(value)),
        ),
        'write cache metadata',
    )


def read_cache_meta(key):
    """Read a value from cache_meta, returning None if absent."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return None
    conn = _get_cache_connection(cache_path)
    row = conn.execute(
        'SELECT value FROM cache_meta WHERE key = ?',
        (str(key),),
    ).fetchone()
    return row['value'] if row is not None else None


def begin_cache_write_batch():
    """Start a batched-write transaction for grouped inserts."""
    global _CACHE_BATCH_ACTIVE  # pylint: disable=global-statement
    if _CACHE_BATCH_ACTIVE:
        return
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return
    conn = _get_cache_connection(cache_path)
    # A peer may hold the write lock: retry instead of aborting the run.
    # A failed BEGIN leaves no transaction open, so retrying is safe.
    execute_with_retry(
        lambda: conn.execute('BEGIN IMMEDIATE'),
        'begin cache write batch',
    )
    _CACHE_BATCH_ACTIVE = True


def commit_cache_write_batch():
    """Commit and finalize a batched-write transaction."""
    global _CACHE_BATCH_ACTIVE  # pylint: disable=global-statement
    if not _CACHE_BATCH_ACTIVE:
        return
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        _CACHE_BATCH_ACTIVE = False
        return
    conn = _get_cache_connection(cache_path)
    conn.commit()
    _CACHE_BATCH_ACTIVE = False


def abort_cache_write_batch():
    """Roll back an open batched-write transaction, if any."""
    global _CACHE_BATCH_ACTIVE  # pylint: disable=global-statement
    if not _CACHE_BATCH_ACTIVE:
        return
    cache_path = get_waveform_cache_db_path()
    _CACHE_BATCH_ACTIVE = False
    if cache_path is None:
        return
    conn = _get_cache_connection(cache_path)
    with suppress(sqlite3.Error):
        conn.rollback()


def _claim_key(trace_id, starttime, endtime):
    """Build the SQL key tuple for the prefetch_claims table."""
    return (
        str(trace_id),
        _utc_to_ns(starttime),
        _utc_to_ns(endtime),
    )


def _claim_ttl_ns(ttl_s):
    """Return the claim lease duration in nanoseconds (at least 1 s)."""
    ttl = DEFAULT_CLAIM_TTL_S if ttl_s is None else float(ttl_s)
    return int(max(ttl, 1.0) * 1e9)


def claim_prefetch_group(trace_id, starttime, endtime, ttl_s=None):
    """
    Try to reserve one prefetch group for this process.

    Expired claims are removed first, so a crashed process never blocks
    a group forever.

    :param trace_id: trace ID of the group
    :param starttime: start of the grouped download window
    :param endtime: end of the grouped download window
    :param ttl_s: lease duration in seconds (defaults to
        ``DEFAULT_CLAIM_TTL_S``)
    :return: True if this process now owns the group, False if another
        live process holds it
    :rtype: bool
    """
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        # Disk cache disabled: nothing to coordinate.
        return True
    conn = _get_cache_connection(cache_path)
    key = _claim_key(trace_id, starttime, endtime)
    owner = _claim_owner_token()
    now_ns = _utc_to_ns(UTCDateTime())
    expires_ns = now_ns + _claim_ttl_ns(ttl_s)

    def work():
        conn.execute(
            'DELETE FROM prefetch_claims WHERE expires_at_ns < ?',
            (now_ns,),
        )
        cursor = conn.execute(
            '''
            INSERT OR IGNORE INTO prefetch_claims (
                trace_id, start_time_ns, end_time_ns,
                owner, host, pid, claimed_at_ns, expires_at_ns
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                *key,
                owner,
                socket.gethostname(),
                os.getpid(),
                now_ns,
                expires_ns,
            ),
        )
        if cursor.rowcount == 1:
            return True
        row = conn.execute(
            '''
            SELECT owner FROM prefetch_claims
            WHERE trace_id = ? AND start_time_ns = ? AND end_time_ns = ?
            ''',
            key,
        ).fetchone()
        if row is None or row['owner'] != owner:
            return False
        # We already own this group (e.g. a previous release was lost):
        # just renew the lease.
        conn.execute(
            '''
            UPDATE prefetch_claims SET expires_at_ns = ?
            WHERE trace_id = ? AND start_time_ns = ? AND end_time_ns = ?
            ''',
            (expires_ns, *key),
        )
        return True

    return _immediate_transaction(conn, work, 'claim prefetch group')


def renew_prefetch_claim(trace_id, starttime, endtime, ttl_s=None):
    """
    Extend the lease of a group owned by this process.

    :return: False when this process no longer owns the group
    :rtype: bool
    """
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        # Disk cache disabled: nothing to coordinate.
        return True
    conn = _get_cache_connection(cache_path)
    key = _claim_key(trace_id, starttime, endtime)
    expires_ns = _utc_to_ns(UTCDateTime()) + _claim_ttl_ns(ttl_s)

    def work():
        cursor = conn.execute(
            '''
            UPDATE prefetch_claims SET expires_at_ns = ?
            WHERE trace_id = ? AND start_time_ns = ? AND end_time_ns = ?
                AND owner = ?
            ''',
            (expires_ns, *key, _claim_owner_token()),
        )
        return cursor.rowcount == 1

    return _immediate_transaction(conn, work, 'renew prefetch claim')


def purge_expired_prefetch_claims():
    """Delete expired claims, returning the number of removed rows."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return 0
    conn = _get_cache_connection(cache_path)
    now_ns = _utc_to_ns(UTCDateTime())

    def work():
        return conn.execute(
            'DELETE FROM prefetch_claims WHERE expires_at_ns < ?',
            (now_ns,),
        ).rowcount

    return _immediate_transaction(conn, work, 'purge prefetch claims')


def release_prefetch_claim(trace_id, starttime, endtime):
    """Delete this process' claim on one group, if any."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return
    conn = _get_cache_connection(cache_path)
    key = _claim_key(trace_id, starttime, endtime)
    _write_transaction(
        conn,
        lambda: conn.execute(
            '''
            DELETE FROM prefetch_claims
            WHERE trace_id = ? AND start_time_ns = ? AND end_time_ns = ?
                AND owner = ?
            ''',
            (*key, _claim_owner_token()),
        ),
        'release prefetch claim',
    )


def release_all_prefetch_claims():
    """Delete every claim owned by this process, whatever its group."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return
    conn = _get_cache_connection(cache_path)
    _write_transaction(
        conn,
        lambda: conn.execute(
            'DELETE FROM prefetch_claims WHERE owner = ?',
            (_claim_owner_token(),),
        ),
        'release prefetch claims',
    )


def clear_prefetch_claims():
    """Delete all claims, returning the number of removed rows."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return 0
    conn = _get_cache_connection(cache_path)

    def work():
        return conn.execute('DELETE FROM prefetch_claims').rowcount

    return _immediate_transaction(conn, work, 'clear prefetch claims')


def list_prefetch_claims():
    """Return all claim rows, oldest group first."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return []
    conn = _get_cache_connection(cache_path)
    now_ns = _utc_to_ns(UTCDateTime())
    rows = conn.execute(
        '''
        SELECT trace_id, start_time_ns, end_time_ns, owner, host, pid,
            claimed_at_ns, expires_at_ns
        FROM prefetch_claims
        ORDER BY start_time_ns, trace_id
        '''
    ).fetchall()
    return [
        {
            'trace_id': row['trace_id'],
            'start_time': str(_ns_to_utc(row['start_time_ns'])),
            'end_time': str(_ns_to_utc(row['end_time_ns'])),
            'owner': row['owner'],
            'host': row['host'],
            'pid': row['pid'],
            'claimed_at': str(_ns_to_utc(row['claimed_at_ns'])),
            'expires_at': str(_ns_to_utc(row['expires_at_ns'])),
            'expired': int(row['expires_at_ns']) < now_ns,
        }
        for row in rows
    ]


def run_wal_checkpoint(mode='passive'):
    """Run WAL checkpoint to keep the WAL file bounded."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return
    conn = _get_cache_connection(cache_path)
    conn.execute(f'PRAGMA wal_checkpoint({mode})')


def _failure_limits():
    """Return configured failure cache retry limits.

    The result is cached at module level because config values are
    immutable after startup.  Use reset_waveform_failures() to clear
    the cached tuple after a config change.
    """
    global _FAILURE_LIMITS  # pylint: disable=global-statement
    if _FAILURE_LIMITS is not None:
        return _FAILURE_LIMITS
    max_retries = int(
        getattr(
            config,
            'catalog_waveform_cache_failure_max_retries',
            DEFAULT_FAILURE_MAX_RETRIES,
        )
    )
    base_backoff_s = float(
        getattr(
            config,
            'catalog_waveform_cache_failure_backoff_s',
            DEFAULT_FAILURE_BACKOFF_S,
        )
    )
    _FAILURE_LIMITS = max(max_retries, 0), max(base_backoff_s, 0.0)
    return _FAILURE_LIMITS


def has_exhausted_failure(evid, trace_id):
    """
    Return True if (evid, trace_id) exhausted its retries and is in backoff.

    Compares retry_count against the minimum of the stored max_retries
    and the current config max_retries, so that a tighter current
    policy (e.g. max_retries=0) correctly supersedes a more permissive
    value that was stored by an earlier run.

    Once all exhausted entries have passed their backoff deadline,
    returns False so that callers may retry.
    """
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return False
    conn = _get_cache_connection(cache_path)
    current_max_retries, _ = _failure_limits()
    now_ns = _utc_to_ns(UTCDateTime())
    row = conn.execute(
        '''
        SELECT 1 FROM waveform_failures
        WHERE evid = ? AND trace_id = ?
            AND retry_count >= MIN(max_retries, ?)
            AND (
                next_retry_after_ns IS NULL
                OR next_retry_after_ns > ?
            )
        LIMIT 1
        ''',
        (str(evid), str(trace_id), current_max_retries, now_ns),
    ).fetchone()
    return row is not None


def should_skip_waveform_download(evid, trace_id, starttime, endtime):
    """Return (skip, reason) from persistent failure cache."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return False, ''
    key = _cache_key(evid, trace_id, starttime, endtime)
    req_start_ns = key[2]
    req_end_ns = key[3]
    now_ns = _utc_to_ns(UTCDateTime())
    conn = _get_cache_connection(cache_path)
    row = conn.execute(
        '''
        SELECT retry_count, max_retries, next_retry_after_ns, last_error
        FROM waveform_failures
        WHERE evid = ? AND trace_id = ?
            AND start_time_ns = ? AND end_time_ns = ?
        ''',
        key,
    ).fetchone()
    # Covering-window fallback (same ±10 s tolerance as the positive
    # cache lookup — see read_waveform_from_cache).
    if row is None:
        row = conn.execute(
            '''
            SELECT retry_count, max_retries, next_retry_after_ns, last_error
            FROM waveform_failures
            WHERE evid = ? AND trace_id = ?
                AND start_time_ns <= ? + 10000000000
                AND end_time_ns + 10000000000 >= ?
            ORDER BY (end_time_ns - start_time_ns) ASC
            LIMIT 1
            ''',
            (
                key[0],
                key[1],
                req_start_ns,
                req_end_ns,
            ),
        ).fetchone()
    if row is None:
        return False, ''
    retry_count = int(row['retry_count'])
    max_retries = int(row['max_retries'])
    if retry_count >= max_retries:
        return True, f'retry limit reached ({retry_count}/{max_retries})'
    next_retry_after_ns = row['next_retry_after_ns']
    if next_retry_after_ns is not None and now_ns < int(next_retry_after_ns):
        last_error = row['last_error'] or ''
        retry_after = _ns_to_utc(next_retry_after_ns)
        return (
            True,
            f'next retry after {retry_after} '
            f'(last error: {last_error})',
        )
    return False, ''


def register_waveform_failure(evid, trace_id, starttime, endtime, error):
    """Persist one waveform download failure with backoff."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None:
        return
    key = _cache_key(evid, trace_id, starttime, endtime)
    max_retries, backoff_base_s = _failure_limits()
    conn = _get_cache_connection(cache_path)
    now_ns = _utc_to_ns(UTCDateTime())

    def work():
        # The read and the write happen in the same write transaction,
        # so a concurrent failure on the same key cannot lose an
        # increment.
        row = conn.execute(
            '''
            SELECT retry_count, first_failure_ns
            FROM waveform_failures
            WHERE evid = ? AND trace_id = ?
                AND start_time_ns = ? AND end_time_ns = ?
            ''',
            key,
        ).fetchone()
        # Increment retry count (or start at 1 for a brand-new failure).
        retry_count = 1 if row is None else int(row['retry_count']) + 1
        first_failure_ns = (
            now_ns if row is None else int(row['first_failure_ns'])
        )
        # Exponential backoff: delay = base * 2^(retry_count - 1).
        delay_s = backoff_base_s * (2 ** max(retry_count - 1, 0))
        next_retry_after_ns = now_ns + int(delay_s * 1e9)
        conn.execute(
            '''
            INSERT INTO waveform_failures (
                evid,
                trace_id,
                start_time_ns,
                end_time_ns,
                retry_count,
                max_retries,
                last_error,
                first_failure_ns,
                last_failure_ns,
                next_retry_after_ns
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evid, trace_id, start_time_ns, end_time_ns)
            DO UPDATE SET
                retry_count = excluded.retry_count,
                max_retries = excluded.max_retries,
                last_error = excluded.last_error,
                last_failure_ns = excluded.last_failure_ns,
                next_retry_after_ns = excluded.next_retry_after_ns
            ''',
            (
                *key,
                retry_count,
                max_retries,
                str(error),
                first_failure_ns,
                now_ns,
                next_retry_after_ns,
            ),
        )

    _write_transaction(conn, work, 'register waveform failure')


def clear_waveform_failure(evid, trace_id, starttime, endtime):
    """Remove waveform failure state for one cache key."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return
    key = _cache_key(evid, trace_id, starttime, endtime)
    conn = _get_cache_connection(cache_path)
    _write_transaction(
        conn,
        lambda: conn.execute(
            '''
            DELETE FROM waveform_failures
            WHERE evid = ? AND trace_id = ?
                AND start_time_ns = ? AND end_time_ns = ?
            ''',
            key,
        ),
        'clear waveform failure',
    )


def read_waveform_cache_summary(integrity=False):
    """Return summary dict for waveform cache diagnostics."""
    cache_path = get_waveform_cache_db_path()
    summary = {
        'path': str(cache_path) if cache_path is not None else None,
        'exists': False,
        'file_size_bytes': 0,
        'schema_version': None,
        'waveform_rows': 0,
        'time_span_start': None,
        'time_span_end': None,
        'top_trace_ids': [],
        'integrity_check': None,
        'failure_rows': 0,
        'failure_exhausted_rows': 0,
        'failure_retry_pending_rows': 0,
        'claim_rows': 0,
        'claim_active_rows': 0,
        'claim_expired_rows': 0,
        'claim_owners': [],
    }
    if cache_path is None or not cache_path.exists():
        return summary
    summary['exists'] = True
    summary['file_size_bytes'] = cache_path.stat().st_size
    conn = _get_cache_connection(cache_path)
    summary['schema_version'] = int(
        conn.execute('PRAGMA user_version').fetchone()[0]
    )
    row = conn.execute(
        '''
        SELECT
            COUNT(*) AS nrows,
            MIN(start_time_ns) AS min_start,
            MAX(end_time_ns) AS max_end
        FROM waveform_cache
        '''
    ).fetchone()
    summary['waveform_rows'] = int(row['nrows'])
    if row['min_start'] is not None:
        summary['time_span_start'] = str(_ns_to_utc(row['min_start']))
        summary['time_span_end'] = str(_ns_to_utc(row['max_end']))
    top_rows = conn.execute(
        '''
        SELECT trace_id, COUNT(*) AS nrows
        FROM waveform_cache
        GROUP BY trace_id
        ORDER BY nrows DESC
        LIMIT 10
        '''
    ).fetchall()
    summary['top_trace_ids'] = [
        {'trace_id': r['trace_id'], 'rows': int(r['nrows'])}
        for r in top_rows
    ]
    now_ns = _utc_to_ns(UTCDateTime())
    fail_row = conn.execute(
        '''
        SELECT
            COUNT(*) AS nrows,
            SUM(CASE WHEN retry_count >= max_retries THEN 1 ELSE 0 END)
                AS exhausted,
            SUM(
                CASE
                    WHEN next_retry_after_ns IS NOT NULL
                        AND next_retry_after_ns > ?
                    THEN 1
                    ELSE 0
                END
            ) AS pending
        FROM waveform_failures
        ''',
        (now_ns,),
    ).fetchone()
    summary['failure_rows'] = int(fail_row['nrows'])
    summary['failure_exhausted_rows'] = int(fail_row['exhausted'] or 0)
    summary['failure_retry_pending_rows'] = int(
        fail_row['pending'] or 0
    )
    claim_row = conn.execute(
        '''
        SELECT
            COUNT(*) AS nrows,
            SUM(CASE WHEN expires_at_ns > ? THEN 1 ELSE 0 END) AS active
        FROM prefetch_claims
        ''',
        (now_ns,),
    ).fetchone()
    summary['claim_rows'] = int(claim_row['nrows'])
    summary['claim_active_rows'] = int(claim_row['active'] or 0)
    summary['claim_expired_rows'] = (
        summary['claim_rows'] - summary['claim_active_rows']
    )
    owner_rows = conn.execute(
        '''
        SELECT
            owner,
            host,
            pid,
            COUNT(*) AS nrows,
            SUM(CASE WHEN expires_at_ns > ? THEN 1 ELSE 0 END) AS active
        FROM prefetch_claims
        GROUP BY owner, host, pid
        ORDER BY nrows DESC
        ''',
        (now_ns,),
    ).fetchall()
    summary['claim_owners'] = [
        {
            'owner': row['owner'],
            'host': row['host'],
            'pid': row['pid'],
            'claims': int(row['nrows']),
            'active': int(row['active'] or 0),
        }
        for row in owner_rows
    ]
    if integrity:
        with suppress(sqlite3.DatabaseError):
            integrity_row = conn.execute(
                'PRAGMA integrity_check'
            ).fetchone()
            if integrity_row is not None:
                summary['integrity_check'] = str(integrity_row[0])
    return summary


def list_waveform_cache_rows(
    event_ids=None,
    trace_ids=None,
    start_time=None,
    end_time=None,
    limit=None,
):
    """Return waveform cache rows formatted as file-like entries."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return []
    conn = _get_cache_connection(cache_path)
    clauses = []
    params = []

    def _add_in_clause(column, values):
        if values:
            placeholders = ', '.join('?' for _ in values)
            clauses.append(f'{column} IN ({placeholders})')
            params.extend(str(v) for v in values)

    _add_in_clause('evid', event_ids)
    _add_in_clause('trace_id', trace_ids)
    if start_time is not None:
        clauses.append('start_time_ns >= ?')
        params.append(_utc_to_ns(start_time))
    if end_time is not None:
        clauses.append('end_time_ns <= ?')
        params.append(_utc_to_ns(end_time))
    where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    limit_clause = '' if limit is None else ' LIMIT ?'
    query = (
        'SELECT evid, trace_id, start_time_ns, end_time_ns, '
        'sampling_rate, npts '
        f'FROM waveform_cache{where_clause} '
        f'ORDER BY start_time_ns, evid, trace_id{limit_clause}'
    )
    if limit is not None:
        params.append(int(limit))
    rows = conn.execute(query, tuple(params)).fetchall()
    output = []
    for row in rows:
        row_start_time = str(_ns_to_utc(row['start_time_ns']))
        row_end_time = str(_ns_to_utc(row['end_time_ns']))
        entry_name = (
            f"{row['evid']}__{row['trace_id']}"
            f'__{row_start_time}__{row_end_time}.mseed'
        )
        output.append(
            {
                'entry': entry_name,
                'evid': row['evid'],
                'trace_id': row['trace_id'],
                'start_time': row_start_time,
                'end_time': row_end_time,
                'sampling_rate': float(row['sampling_rate']),
                'npts': int(row['npts']),
            }
        )
    return output


def reset_waveform_failures(
    event_ids=None,
    older_than_s=None,
    dry_run=False,
    clear_all=False,
):
    """Reset failure-cache rows and return number of affected rows."""
    cache_path = get_waveform_cache_db_path()
    if cache_path is None or not cache_path.exists():
        return 0
    clauses = []
    params = []
    if event_ids:
        placeholders = ', '.join('?' for _ in event_ids)
        clauses.append(f'evid IN ({placeholders})')
        params.extend(str(event_id) for event_id in event_ids)
    if older_than_s is not None:
        cutoff_ns = _utc_to_ns(UTCDateTime()) - int(older_than_s * 1e9)
        clauses.append('last_failure_ns < ?')
        params.append(cutoff_ns)
    where_clause = ''
    if clauses and not clear_all:
        where_clause = f" WHERE {' AND '.join(clauses)}"
    query = f'SELECT COUNT(*) FROM waveform_failures{where_clause}'
    conn = _get_cache_connection(cache_path)
    if dry_run:
        return int(conn.execute(query, tuple(params)).fetchone()[0])
    delete_query = f'DELETE FROM waveform_failures{where_clause}'
    return _immediate_transaction(
        conn,
        lambda: conn.execute(delete_query, params).rowcount,
        'reset waveform failures',
    )
