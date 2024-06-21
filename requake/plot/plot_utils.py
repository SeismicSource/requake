# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot utils.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import contextlib
import matplotlib.dates as mdates
import numpy as np
from matplotlib import cm, colors
from ..config import config
from .colormaps import cmaps
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def format_time_axis(ax, which='xaxis', grid=True):
    """
    Format the time axis of a Matplotlib plot.
    """
    if which == 'both':
        axes = [ax.xaxis, ax.yaxis]
    elif which == 'xaxis':
        axes = [ax.xaxis]
    elif which == 'yaxis':
        axes = [ax.yaxis]
    else:
        raise ValueError(f'Invalid value for "which": {which}')
    for axis in axes:
        dmin, dmax = axis.get_view_interval()
        timespan = dmax-dmin
        if timespan > 2*365:
            _major_locator = mdates.YearLocator()   # every year
            _major_fmt = mdates.DateFormatter('%Y')
            _minor_locator = mdates.MonthLocator()  # every month
        else:
            _major_locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
            _major_fmt = mdates.ConciseDateFormatter(_major_locator)
            if timespan > 365/2:
                _minor_locator = mdates.MonthLocator()  # every month
            else:
                _minor_locator = mdates.DayLocator()  # every day
        axis.set_major_locator(_major_locator)
        axis.set_major_formatter(_major_fmt)
        axis.set_minor_locator(_minor_locator)
        if grid:
            axis.grid(True, which='major', linestyle='--', color='0.5')
            axis.grid(True, which='minor', linestyle=':', color='0.8')
    ax.figure.canvas.draw()


def plot_title(
        ax, nfamilies, trace_ids=None, vertical_position=1, fontsize=10):
    """
    Set the title of a plot.

    :param ax: Matplotlib axis
    :type ax: matplotlib.axes.Axes
    :param nfamilies: Number of families
    :type nfamilies: int
    :param trace_ids: List of trace IDs
    :type trace_ids: list
    :param vertical_position: Vertical position of the title
    :type vertical_position: float
    :param fontsize: Font size
    :type fontsize: int
    """
    if trace_ids is not None:
        title_left = '|'.join(trace_ids)
        ax.set_title(
            title_left, loc='left', y=vertical_position, fontsize=fontsize)
    title_right = f'{nfamilies} families'
    ax.set_title(
        title_right, loc='right', y=vertical_position, fontsize=fontsize)


def hover_annotation(event):
    """
    Show annotation on hover.

    This function is called when the mouse hovers over a line or a marker.

    :param event: Matplotlib event
    :type event: matplotlib.backend_bases.MouseEvent
    """
    ax = event.inaxes
    if ax is None:
        return
    hover_on = getattr(ax, 'hover_annotation_element', None)
    if hover_on is None:
        return
    fig = ax.get_figure()
    try:
        annot = [
            child for child in ax.get_children()
            if getattr(child, 'hover_annotation', False)
        ][0]
    except IndexError:
        return
    vis = annot.get_visible()
    if hover_on == 'lines':
        elements = ax.get_lines()
    elif hover_on == 'markers':
        elements = [
            el for el in ax.collections if getattr(el, 'to_annotate', False)]
    else:
        return
    for element in elements:
        cont, _ind = element.contains(event)
        if cont:
            if hover_on == 'lines':
                color = element.get_color()
            elif hover_on == 'markers':
                color = element.get_facecolor()[0]
            element.set_linewidth(3)
            annot.xy = (event.xdata, event.ydata)
            # set a color contrasting with the element color
            contrast_color = 'k' if sum(color[:3]) > 1.8 else 'w'
            if hover_on == 'markers':
                element.set_edgecolor(contrast_color)
            annot.set_color(contrast_color)
            annot.set_text(element.get_label())
            annot.get_bbox_patch().set_facecolor(color)
            annot.get_bbox_patch().set_alpha(0.8)
            annot.set_visible(True)
            fig.canvas.draw_idle()
            break
        element.set_linewidth(1)
        if hover_on == 'markers':
            element.set_edgecolor('w')
        if vis:
            annot.set_visible(False)
            fig.canvas.draw_idle()


def _duration_units(duration):
    """
    Return the duration and the units.

    :param duration: Duration in years
    :type duration: float
    :return: Duration, units
    :rtype: float, str
    """
    units = 'years'
    if duration < 1:
        duration *= 12
        units = 'months'
    if duration < 1:
        duration *= 30
        units = 'days'
    if duration < 1:
        duration *= 24
        units = 'hours'
    if duration < 1:
        duration *= 60
        units = 'minutes'
    if duration < 1:
        duration *= 60
        units = 'seconds'
    return duration, units


_short_units = {
    'years': 'yrs',
    'months': 'mos',
    'days': 'days',
    'hours': 'hrs',
    'minutes': 'mins',
    'seconds': 'secs',
}


def duration_string(family):
    """
    Return a string representing the duration of a family.

    :param family: Family object
    :type family: Family
    :return: Duration string
    :rtype: str
    """
    duration = (family.endtime - family.starttime)/(365*24*60*60)
    duration, units = _duration_units(duration)
    return f'{duration:.1f} {_short_units[units]}'


def family_colors(families):
    """
    Return the family colors, according to the colorby parameter.

    :param families: List of families
    :type families: list
    :return: List of colors, normalization object, colormap
    :rtype: list, matplotlib.colors.Normalize, matplotlib.cm.ScalarMappable

    :raises ValueError: If the colorby parameter is invalid or if lon0 and/or
        lat0 are not specified when colorby is 'distance_from'
    """
    colorby = config.args.colorby
    try:
        cmap = cmaps[colorby]
        logger.info(f'Using Matplotlib colormap "{cmap.name}"')
    except KeyError as err:
        raise ValueError(f'Invalid value for "colorby": {colorby}') from err
    # special cases
    if colorby == 'family_number':
        norm = colors.Normalize(vmin=-0.5, vmax=9.5)
        fcolors = [cmap(norm(family.number % 10)) for family in families]
        return fcolors, norm, cmap
    if colorby == 'duration':
        return _family_colors_duration(families, cmap)
    if colorby == 'number_of_events':
        return _family_color_number_of_events(families, cmap)
    # general cases
    if colorby == 'cumul_moment':
        values = [family.cumul_moment for family in families]
    elif colorby == 'cumul_slip':
        values = [family.cumul_slip for family in families]
    elif colorby == 'depth':
        values = [family.depth for family in families]
    elif colorby == 'distance_from':
        lon0, lat0 = config.distance_from_lon, config.distance_from_lat
        if lon0 is None or lat0 is None:
            raise ValueError(
                '"colorby" set to "distance_from", '
                'but "distance_from_lon" and/or "distance_from_lat" '
                'are not specified in the config file')
        values = [family.distance_from(lon0, lat0) for family in families]
        cmap.label = f'{cmap.label} ({lat0:.1f}°N,{lon0:.1f}°E) (km)'
    elif colorby == 'latitude':
        values = [family.lat for family in families]
    elif colorby == 'longitude':
        values = [family.lon for family in families]
    elif colorby == 'slip_rate':
        values = [
            family.slip_rate if family.slip_rate is not np.inf
            else np.nan for family in families
        ]
    elif colorby == 'time':
        values = [family.starttime.matplotlib_date for family in families]
    # Convert values to float numpy array. This changes None values to np.nan
    values = np.array(values, dtype=float)
    norm = colors.Normalize(vmin=min(values), vmax=max(values))
    fcolors = [cmap(norm(value)) for value in values]
    return fcolors, norm, cmap


def _family_color_number_of_events(families, cmap):
    """
    Return the family colors, according to the number of events.

    :param families: List of families
    :type families: list
    :param cmap: Colormap
    :type cmap: matplotlib.colors.Colormap
    :return: List of colors, normalization object, colormap
    :rtype: list, matplotlib.colors.Normalize, matplotlib.cm.ScalarMappable
    """
    values = [len(family) for family in families]
    boundaries = np.arange(min(values), max(values)+1)
    if len(boundaries) % 2 == 0:
        boundaries = np.append(boundaries, max(values)+1)
    boundaries = boundaries - 0.5
    norm = colors.BoundaryNorm(boundaries, cmap.N)
    return [cmap(norm(value)) for value in values], norm, cmap


def _family_colors_duration(families, cmap):
    """
    Return the family colors, according to the duration.

    :param families: List of families
    :type families: list
    :param cmap: Colormap
    :type cmap: matplotlib.colors.Colormap
    :return: List of colors, normalization object, colormap
    :rtype: list, matplotlib.colors.Normalize, matplotlib.cm.ScalarMappable
    """
    durations = [family.duration for family in families]
    max_duration = max(durations)
    max_duration_new_units, units = _duration_units(max_duration)
    multiplier = max_duration_new_units/max_duration
    min_duration_new_units = min(durations)*multiplier
    norm = colors.Normalize(
        vmin=min_duration_new_units, vmax=max_duration_new_units)
    fcolors = [cmap(norm(duration*multiplier)) for duration in durations]
    cmap.label = f'{cmap.label} ({units})'
    return fcolors, norm, cmap


def plot_colorbar(fig, ax, cmap, norm):
    """
    Add a colorbar to a plot.

    :param fig: Matplotlib figure
    :type fig: matplotlib.figure.Figure
    :param ax: Matplotlib axis
    :type ax: matplotlib.axes.Axes
    :param cmap: Colormap
    :type cmap: matplotlib.colors.Colormap
    :param norm: Normalization object
    :type norm: matplotlib.colors.Normalize
    """
    colorby = config.args.colorby
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar_ticks = None
    if colorby == 'family_number':
        cbar_ticks = range(10)
    elif colorby == 'number_of_events':
        cbar_ticks = norm.boundaries + 0.5
    cbar = fig.colorbar(sm, ticks=cbar_ticks, pad=0.1, ax=ax)
    # turn off minor ticks
    cbar.ax.yaxis.set_tick_params(which='minor', size=0)
    cbar.ax.set_zorder(-1)
    if colorby == 'time':
        format_time_axis(cbar.ax, which='yaxis', grid=False)
    with contextlib.suppress(AttributeError):
        cbar.ax.set_ylabel(cmap.label)
