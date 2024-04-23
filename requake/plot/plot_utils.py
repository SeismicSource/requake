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
import matplotlib.dates as mdates


def format_time_axis(ax, which='xaxis'):
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
            else:
                color = element.get_facecolor()[0]
            element.set_linewidth(3)
            annot.xy = (event.xdata, event.ydata)
            annot.set_text(element.get_label())
            annot.get_bbox_patch().set_facecolor(color)
            annot.get_bbox_patch().set_alpha(0.8)
            annot.set_visible(True)
            fig.canvas.draw_idle()
            break
        element.set_linewidth(1)
        if vis:
            annot.set_visible(False)
            fig.canvas.draw_idle()


def duration_string(family):
    """
    Return a string representing the duration of a family.

    :param family: Family object
    :type family: Family
    :return: Duration string
    :rtype: str
    """
    duration = (family.endtime - family.starttime)/(365*24*60*60)
    duration_str = f'{duration:.1f} yrs'
    if duration < 1:
        duration *= 12
        duration_str = f'{duration:.1f} mos'
    if duration < 1:
        duration *= 30
        duration_str = f'{duration:.1f} days'
    if duration < 1:
        duration *= 24
        duration_str = f'{duration:.1f} hrs'
    if duration < 1:
        duration *= 60
        duration_str = f'{duration:.1f} mins'
    if duration < 1:
        duration *= 60
        duration_str = f'{duration:.1f} secs'
    return duration_str
