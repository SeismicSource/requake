# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Snapshots of the configuration parameters used by a run.

Every catalog read, catalog scan and family build records the parameters
that produced it, so that runs can be listed, compared and resumed.  The
snapshot is stored as JSON (full detail, future proof) together with a
hash that identifies runs with identical parameters.
"""
import hashlib
import json
import os
from .config import config


def _value(key, default=None):
    """Return a configuration value, or *default* when it is not set."""
    value = config.get(key, default)
    return default if value is None else value


def _args_value(key, default=None):
    """Return a command-line value, or *default* when it is not set."""
    args = config.get('args')
    value = getattr(args, key, default)
    return default if value is None else value


def _json_default(value):
    """Serialize values that JSON does not handle natively."""
    return str(value)


def _catalog_source():
    """Describe where the catalog events come from."""
    catalog_file = _args_value('catalog_file')
    if catalog_file is not None:
        return {
            'type': 'file',
            'path': os.path.abspath(catalog_file),
        }
    return {
        'type': 'fdsn',
        'urls': list(_value('catalog_fdsn_event_urls', [])),
    }


def _trace_ids():
    """Return the trace IDs the scan will actually use."""
    traceid = _args_value('traceid')
    catalog_trace_ids = list(_value('catalog_trace_id', []))
    return [traceid] if traceid is not None else catalog_trace_ids


def catalog_parameters():
    """
    Return the parameters used to read and filter a catalog.

    :return: parameter snapshot
    :rtype: dict
    """
    return {
        'catalog_source': _catalog_source(),
        'start_times': list(_value('catalog_start_times', [])),
        'end_times': list(_value('catalog_end_times', [])),
        'lat_min': _value('catalog_lat_min'),
        'lat_max': _value('catalog_lat_max'),
        'lon_min': _value('catalog_lon_min'),
        'lon_max': _value('catalog_lon_max'),
        'depth_min': _value('catalog_depth_min'),
        'depth_max': _value('catalog_depth_max'),
        'mag_min': _value('catalog_mag_min'),
        'mag_max': _value('catalog_mag_max'),
    }


def scan_parameters():
    """
    Return the parameters that determine the outcome of a catalog scan.

    :return: parameter snapshot
    :rtype: dict
    """
    params = {
        'catalog_trace_id': _trace_ids(),
        'catalog_search_range': _value('catalog_search_range'),
        'station_source': {
            'fdsn_station_url': _value('fdsn_station_url'),
            'station_metadata_path': _value('station_metadata_path'),
        },
        'waveform_source': {
            'fdsn_dataselect_url': _value('fdsn_dataselect_url'),
            'sds_data_path': _value('sds_data_path'),
            'event_data_path': _value('event_data_path'),
        },
        'cc_pre_P': _value('cc_pre_P'),
        'cc_trace_length': _value('cc_trace_length'),
        'cc_freq_min': _value('cc_freq_min'),
        'cc_freq_max': _value('cc_freq_max'),
        'cc_max_shift': _value('cc_max_shift'),
        'cc_allow_negative': _value('cc_allow_negative'),
    }
    freq_band = _args_value('freq_band')
    if freq_band is not None:
        freq_min, freq_max = freq_band
        params['cc_freq_min'] = float(freq_min)
        params['cc_freq_max'] = float(freq_max)
    return params


def family_build_parameters():
    """
    Return the parameters that determine the outcome of a family build.

    :return: parameter snapshot
    :rtype: dict
    """
    return {
        'clustering_algorithm': _value('clustering_algorithm'),
        'cc_min': _value('cc_min'),
        'sort_families_by': _value('sort_families_by'),
        'distance_from_lon': _value('distance_from_lon'),
        'distance_from_lat': _value('distance_from_lat'),
    }


def parameters_json(params):
    """
    Serialize a parameter snapshot to canonical JSON.

    :param params: parameter snapshot
    :type params: dict
    :return: JSON string
    :rtype: str
    """
    return json.dumps(params, sort_keys=True, default=_json_default)


def parameters_digest(params):
    """
    Return a short hash identifying a parameter snapshot.

    :param params: parameter snapshot
    :type params: dict
    :return: hexadecimal digest
    :rtype: str
    """
    payload = parameters_json(params).encode('utf8')
    return hashlib.sha256(payload).hexdigest()


def format_parameters(params_json_string):
    """
    Return a stored parameter snapshot as sorted key/value pairs.

    :param params_json_string: JSON string stored in the database
    :type params_json_string: str or None
    :return: list of ``(key, value)`` pairs
    :rtype: list
    """
    try:
        params = json.loads(params_json_string or '{}')
    except ValueError:
        return [('params_json', params_json_string)]
    rows = []
    for key in sorted(params):
        value = params[key]
        if isinstance(value, dict):
            value = json.dumps(value, sort_keys=True, default=_json_default)
        elif isinstance(value, (list, tuple)):
            value = ', '.join(str(item) for item in value)
        rows.append((key, value))
    return rows
