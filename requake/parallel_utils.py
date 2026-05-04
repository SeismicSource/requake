#!/usr/bin/env python
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utilities for parallel processing and optional disk caching in Requake.

:copyright:
    2021-2026 Claudio Satriano, Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
# Note: modules are lazily imported to speed up the startup time.
# pylint: disable=import-outside-toplevel
import hashlib
import multiprocessing as mp
import os
import pickle


def _get_n_jobs(n_jobs):
    """
    Resolve the number of worker processes.

    Negative values follow joblib convention:
    -1 means all CPUs, -2 means all CPUs minus one, etc.

    :param n_jobs: requested number of workers
    :type n_jobs: int or None
    :returns: resolved number of workers
    :rtype: int
    """
    if n_jobs is None:
        return mp.cpu_count()
    if n_jobs < 0:
        return max(1, mp.cpu_count() + 1 + n_jobs)
    return max(1, n_jobs)


def _hash_args(args, kwargs):
    """
    Compute a deterministic SHA-256 hash from function arguments.

    Used as cache key for disk caching.

    :param args: positional arguments
    :param kwargs: keyword arguments
    :returns: hex digest string
    :rtype: str
    """
    hasher = hashlib.sha256()
    hasher.update(pickle.dumps((args, kwargs), protocol=pickle.HIGHEST_PROTOCOL))
    return hasher.hexdigest()


def cache_get(cache_dir, func_name, key):
    """
    Retrieve a cached result from disk if it exists.

    :param cache_dir: path to the cache directory
    :type cache_dir: str
    :param func_name: name of the cached function (used as subdirectory)
    :type func_name: str
    :param key: cache key (SHA-256 hex digest)
    :type key: str
    :returns: cached result, or None if not found
    """
    cache_path = os.path.join(cache_dir, func_name, f'{key}.pkl')
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    return None


def cache_put(cache_dir, func_name, key, result):
    """
    Persist a result to the disk cache.

    :param cache_dir: path to the cache directory
    :type cache_dir: str
    :param func_name: name of the cached function (used as subdirectory)
    :type func_name: str
    :param key: cache key (SHA-256 hex digest)
    :type key: str
    :param result: result to store
    """
    cache_path = os.path.join(cache_dir, func_name, f'{key}.pkl')
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)


def parallel_map(func, items, n_jobs=None, chunksize=1, cache_dir=None):
    """
    Parallel map using ProcessPoolExecutor with optional disk caching.

    Preserves result order. When ``cache_dir`` is set, already-computed
    results are read from disk and skipped in the worker pool, allowing
    interrupted scans to resume without data loss.

    :param func: function to parallelize. Must be pickleable and defined
        at module level (no lambdas, no closures).
    :type func: callable
    :param items: list of arguments, one per call to ``func``
    :type items: list
    :param n_jobs: number of worker processes. ``None`` uses all available
        CPUs. Negative values follow joblib convention (e.g. -1 = all CPUs,
        -2 = all CPUs minus one). Defaults to ``None``.
    :type n_jobs: int or None
    :param chunksize: number of items per submitted task. Higher values
        reduce IPC overhead at the cost of coarser load balancing.
        Defaults to 1.
    :type chunksize: int
    :param cache_dir: path to the disk cache directory. If ``None``,
        caching is disabled. Defaults to ``None``.
    :type cache_dir: str or None
    :returns: list of results in the same order as ``items``
    :rtype: list
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed
    n_workers = _get_n_jobs(n_jobs)
    results = [None] * len(items)

    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {}
        for idx, item in enumerate(items):
            cache_key = _hash_args((item,), {}) if cache_dir else None
            if cache_dir and cache_key:
                cached = cache_get(cache_dir, func.__name__, cache_key)
                if cached is not None:
                    results[idx] = cached
                    continue
            future = executor.submit(func, item)
            futures[future] = (idx, cache_key)

        for future in as_completed(futures):
            idx, cache_key = futures[future]
            try:
                result = future.result()
                results[idx] = result
                if cache_dir and cache_key:
                    cache_put(cache_dir, func.__name__, cache_key, result)
            except Exception as exc:  # pylint: disable=broad-except
                # Mirror Requake's error reporting style
                print(
                    f'ERROR: worker failed for item index {idx}: {exc}'
                )

    return results
