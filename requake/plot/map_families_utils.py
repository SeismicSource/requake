# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility functions for the map backends.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import math
import numpy as np
from ..config import config

# marker size range: the radius of the marker of the family with the
# smallest value is MIN_MARKER_RADIUS, while the one with the largest value
# is MAX_MARKER_RADIUS (radii are in points for the cartopy backend and in
# pixels for the folium backend)
MIN_MARKER_RADIUS = 5
MAX_MARKER_RADIUS = 14
# maximum number of entries in the size legend
MAX_LEGEND_ENTRIES = 3
# mantissas of the round values used for the size legend
_LEGEND_MANTISSAS = (1, 2, 5)

_SIZE_LABELS = {
    'number_of_events': 'Number of Events',
    'duration': 'Duration',
    'depth': 'Depth (km)',
    'latitude': 'Latitude (°N)',
    'longitude': 'Longitude (°E)',
    'distance_from': 'Distance from',
    'cumul_moment': 'Cumulative Moment (N·m)',
    'cumul_slip': 'Cumulative Slip (cm)',
    'slip_rate': 'Slip Rate (cm/y)',
}


def size_label(sizeby):
    """
    Return a description of a size quantity.

    :param sizeby: Quantity used to scale the marker size
    :type sizeby: str
    :return: Description
    :rtype: str
    """
    label = _SIZE_LABELS.get(sizeby, sizeby)
    if sizeby == 'duration':
        return f'{label} (years)'
    if sizeby == 'distance_from':
        lon0 = config.distance_from_lon
        lat0 = config.distance_from_lat
        if None not in (lon0, lat0):
            return f'{label} ({lat0:.1f}°N,{lon0:.1f}°E) (km)'
    return label


def _size_values(families, sizeby):
    """
    Return the values used to scale the family markers.

    :param families: List of families
    :type families: list of requake.families.Family
    :param sizeby: Quantity used to scale the marker size
    :type sizeby: str
    :return: Values, one per family (nan for missing values)
    :rtype: numpy.ndarray

    :raises ValueError: if the sizeby quantity is invalid or if lon0 and/or
        lat0 are not specified when sizeby is 'distance_from'
    """
    if sizeby == 'number_of_events':
        values = [len(family) for family in families]
    elif sizeby == 'duration':
        values = [family.duration for family in families]
    elif sizeby == 'depth':
        values = [family.depth for family in families]
    elif sizeby == 'latitude':
        values = [family.lat for family in families]
    elif sizeby == 'longitude':
        values = [family.lon for family in families]
    elif sizeby == 'distance_from':
        lon0, lat0 = config.distance_from_lon, config.distance_from_lat
        if lon0 is None or lat0 is None:
            raise ValueError(
                '"sizeby" set to "distance_from", '
                'but "distance_from_lon" and/or "distance_from_lat" '
                'are not specified in the config file')
        values = [family.distance_from(lon0, lat0) for family in families]
    elif sizeby == 'cumul_moment':
        values = [family.cumul_moment for family in families]
    elif sizeby == 'cumul_slip':
        values = [family.cumul_slip for family in families]
    elif sizeby == 'slip_rate':
        values = [
            family.slip_rate if family.slip_rate != np.inf
            else np.nan for family in families
        ]
    else:
        raise ValueError(f'Invalid value for "sizeby": {sizeby}')
    # Convert values to float numpy array. This changes None values to np.nan
    return np.array(values, dtype=float)


def _size_scale(values):
    """
    Return the range and the type of the size scale.

    A logarithmic scale is used when all the values are positive and span
    more than one order of magnitude.

    :param values: Values used to scale the marker size
    :type values: numpy.ndarray
    :return: Minimum value, maximum value, use logarithmic scale
    :rtype: tuple or None
    """
    finite = values[np.isfinite(values)]
    if not finite.size:
        return None
    vmin = float(finite.min())
    vmax = float(finite.max())
    return vmin, vmax, vmin > 0 and vmax > 10 * vmin


def _normalized_size(value, vmin, vmax, use_log):
    """
    Normalize a value into the [0, 1] range.

    :param value: Value to normalize
    :type value: float
    :param vmin: Minimum value of the scale
    :type vmin: float
    :param vmax: Maximum value of the scale
    :type vmax: float
    :param use_log: Whether to use a logarithmic scale
    :type use_log: bool
    :return: Normalized value
    :rtype: float
    """
    if use_log:
        return (
            (np.log10(value) - np.log10(vmin))
            / (np.log10(vmax) - np.log10(vmin))
        )
    return (value - vmin) / (vmax - vmin)


def _value_from_size(size, vmin, vmax, use_log):
    """
    Return the value corresponding to a normalized size.

    :param size: Normalized size, in the [0, 1] range
    :type size: float
    :param vmin: Minimum value of the scale
    :type vmin: float
    :param vmax: Maximum value of the scale
    :type vmax: float
    :param use_log: Whether to use a logarithmic scale
    :type use_log: bool
    :return: Value
    :rtype: float
    """
    return (
        vmin * (vmax / vmin) ** size if use_log
        else vmin + size * (vmax - vmin)
    )


def _round_values(vmin, vmax, use_log):
    """
    Return round values inside the given range, for the size legend.

    Values are taken from the 1-2-5 sequence, so that the size legend
    shows round numbers (e.g., 5, 50, 500).

    :param vmin: Minimum value of the scale
    :type vmin: float
    :param vmax: Maximum value of the scale
    :type vmax: float
    :param use_log: Whether to use a logarithmic scale
    :type use_log: bool
    :return: Round values
    :rtype: list of float
    """
    exponent = math.floor(math.log10(vmin)) if vmin > 0 else 0
    values = []
    while 10 ** exponent <= vmax:
        values.extend(
            float(mantissa * 10 ** exponent)
            for mantissa in _LEGEND_MANTISSAS
            if vmin <= mantissa * 10 ** exponent <= vmax
        )
        exponent += 1
    if len(values) < 2:
        # no round values in the range: use the minimum, the middle and
        # the maximum value, rounded to three significant digits
        fallback = [vmin, _value_from_size(0.5, vmin, vmax, use_log), vmax]
        return [float(f'{value:.3g}') for value in fallback]
    if len(values) > MAX_LEGEND_ENTRIES:
        # keep the first and the last value, and evenly spaced values
        # in between
        indices = np.linspace(0, len(values) - 1, MAX_LEGEND_ENTRIES)
        indices = sorted({int(round(index)) for index in indices})
        values = [values[index] for index in indices]
    return values


def _legend_entries(values, vmin, vmax, use_log):
    """
    Return the size legend entries.

    :param values: Values of the size legend
    :type values: list of float
    :param vmin: Minimum value of the scale
    :type vmin: float
    :param vmax: Maximum value of the scale
    :type vmax: float
    :param use_log: Whether to use a logarithmic scale
    :type use_log: bool
    :return: Legend entries, as (value label, radius) pairs
    :rtype: list of tuple
    """
    entries = []
    for value in values:
        with np.errstate(divide='ignore', invalid='ignore'):
            size = _normalized_size(value, vmin, vmax, use_log)
        size = float(np.clip(size, 0.0, 1.0))
        entries.append((f'{value:g}', marker_radius(size)))
    return entries


def marker_radius(size):
    """
    Return the marker radius corresponding to a normalized size.

    Radii are in points for the cartopy backend and in pixels for the
    folium backend.

    :param size: Normalized size, in the [0, 1] range
    :type size: float
    :return: Marker radius
    :rtype: float
    """
    return MIN_MARKER_RADIUS + (MAX_MARKER_RADIUS - MIN_MARKER_RADIUS) * size


def get_family_marker_radii(families, sizeby):
    """
    Return the marker radii for the families and the size legend.

    The marker size is scaled with the quantity given by ``sizeby``. A
    logarithmic scale is used when the values span more than one order of
    magnitude. Families with a missing value get the minimum size.

    :param families: List of families
    :type families: list of requake.families.Family
    :param sizeby: Quantity used to scale the marker size
    :type sizeby: str
    :return: Radii (one per family), size legend entries, as (value label,
        radius) pairs, and the description of the size quantity
    :rtype: tuple

    :raises ValueError: if the sizeby quantity is invalid or if lon0 and/or
        lat0 are not specified when sizeby is 'distance_from'
    """
    values = _size_values(families, sizeby)
    scale = _size_scale(values)
    if scale is None:
        radii = [MIN_MARKER_RADIUS] * values.size
        return radii, [], size_label(sizeby)
    vmin, vmax, use_log = scale
    if vmax > vmin:
        with np.errstate(divide='ignore', invalid='ignore'):
            sizes = np.array([
                _normalized_size(value, vmin, vmax, use_log)
                for value in values
            ])
        legend = _legend_entries(
            _round_values(vmin, vmax, use_log), vmin, vmax, use_log)
    else:
        # all the values are equal: use the maximum size
        sizes = np.ones(values.size)
        radius = marker_radius(1.0)
        legend = [(f'{vmin:g}', radius)]
    # families with a missing value get the minimum size
    sizes = np.where(np.isfinite(values), sizes, 0.0)
    sizes = np.clip(sizes, 0.0, 1.0)
    radii = [marker_radius(size) for size in sizes]
    return radii, legend, size_label(sizeby)
