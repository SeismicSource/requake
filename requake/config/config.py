# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Config class for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from argparse import Namespace


# Runtime objects that are useful in-process but should not be sent to
# worker processes via ProcessPoolExecutor.
RUNTIME_ONLY_KEYS = frozenset({
    'station_client',
    'dataselect_client',
    'catalog_fdsn_event_clients',
})


class Config(dict):
    """A class to access config values with dot notation."""

    def __setitem__(self, key, value):
        """Make Config keys accessible as attributes."""
        super().__setattr__(key, value)
        super().__setitem__(key, value)

    def __getattr__(self, key):
        """Make Config keys accessible as attributes."""
        try:
            return self.__getitem__(key)
        except KeyError as err:
            raise AttributeError(err) from err

    __setattr__ = __setitem__


def to_picklable_config_dict(
    cfg,
    drop_inventory=False,
    extra_excluded_keys=None,
):
    """
    Build a pickle-safe config snapshot for multiprocessing.

    This helper strips known runtime-only objects (for example ObsPy clients
    containing SSL contexts) and converts ``args`` from ``argparse.Namespace``
    to a plain ``dict``.

    Typical usage with ``concurrent.futures.ProcessPoolExecutor``::

        from concurrent.futures import ProcessPoolExecutor
        from requake.config import (
            config,
            to_picklable_config_dict,
            from_picklable_config_dict,
        )

        cfg_dict = to_picklable_config_dict(config)

        def worker(cfg_dict, event_id):
            cfg = from_picklable_config_dict(cfg_dict)
            # Rebuild only what is needed in each process.
            # Re-create network clients here, not in the parent process.
            return cfg['cc_min'], event_id

        def _worker_call(args):
            cfg, evid = args
            return worker(cfg, evid)

        with ProcessPoolExecutor() as pool:
            worker_args = ((cfg_dict, evid) for evid in event_ids)
            list(pool.map(_worker_call, worker_args))

    :param cfg: Requake config-like mapping.
    :type cfg: Mapping
    :param drop_inventory: Exclude ``inventory`` from the snapshot.
    :type drop_inventory: bool
    :param extra_excluded_keys: Additional keys to remove from the snapshot.
    :type extra_excluded_keys: iterable or None
    :return: A pickle-safe shallow copy of the configuration.
    :rtype: dict
    """
    cfg_dict = dict(cfg)
    excluded_keys = set(RUNTIME_ONLY_KEYS)
    if drop_inventory:
        excluded_keys.add('inventory')
    if extra_excluded_keys is not None:
        excluded_keys.update(extra_excluded_keys)
    for key in excluded_keys:
        cfg_dict.pop(key, None)

    args = cfg_dict.get('args')
    if isinstance(args, Namespace):
        cfg_dict['args'] = vars(args).copy()

    return cfg_dict


def from_picklable_config_dict(cfg_dict):
    """
    Rebuild a ``Config`` instance from a pickle-safe snapshot.

    This helper is the counterpart of ``to_picklable_config_dict()`` and is
    intended for worker processes receiving a serialized config payload.

    If ``args`` is a dict, it is converted back to ``argparse.Namespace``.

    :param cfg_dict: Pickle-safe config snapshot.
    :type cfg_dict: Mapping
    :return: Reconstructed config object.
    :rtype: Config
    """
    cfg = Config()
    cfg.update(dict(cfg_dict))
    args = cfg.get('args')
    if isinstance(args, dict):
        cfg['args'] = Namespace(**args)
    return cfg

config = Config()  # noqa
