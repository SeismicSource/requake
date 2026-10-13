# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot families on a map using folium.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import logging
import tempfile
import webbrowser
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from matplotlib.colors import to_hex
from matplotlib.dates import date2num
from matplotlib.ticker import MaxNLocator
from ..config import config, rq_exit
from .plot_utils import family_colors, duration_string
from .map_families_utils import get_family_marker_radii
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])

# folium is an optional dependency: this module must be importable without it
try:
    import folium
    import branca
except ImportError:
    folium = None
    branca = None

# default basename for the output HTML file
_DEFAULT_OUTPUT_BASENAME = 'family_map'
# output formats supported by image-based backends only
_IMAGE_FORMATS = ('pdf', 'svg', 'png', 'jpg', 'jpeg')
# matplotlib date number of the Unix epoch, used to convert the matplotlib
# dates of the family start times into JavaScript dates; cast to float, so
# that it is rendered as a plain number in the JavaScript code
_UNIX_EPOCH_MPL_DATE = float(
    date2num(datetime(1970, 1, 1, tzinfo=timezone.utc))
)
# number of colors sampled from the matplotlib colormap for the legend
_LEGEND_COLORS = 16
# maximum number of ticks in the legend
_MAX_LEGEND_TICKS = 8

_ESRI_ATTRIBUTION = (
    'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, '
    'and the GIS User Community'
)
_ESRI_BASE_ATTRIBUTION = 'Tiles &copy; Esri'
_STAMEN_ATTRIBUTION = (
    'Map tiles by Stamen Design, under CC BY 4.0. '
    'Data by OpenStreetMap, under ODbL.'
)
# base map tiles available to the folium backend, keyed by --mapstyle value
_TILES = {
    'satellite': (
        'Esri World Imagery',
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
        _ESRI_ATTRIBUTION,
    ),
    'street': (
        'Esri World Street Map',
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        _ESRI_BASE_ATTRIBUTION,
    ),
    'ocean': (
        'Esri Ocean Base',
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
        _ESRI_BASE_ATTRIBUTION,
    ),
    'hillshade': (
        'Esri World Hillshade',
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}',
        _ESRI_BASE_ATTRIBUTION,
    ),
    'hillshade_dark': (
        'Esri World Hillshade Dark',
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}',
        _ESRI_BASE_ATTRIBUTION,
    ),
}


def _get_tile_definition(map_style, apikey):
    """
    Return the tile name, URL and attribution for a map style.

    :param map_style: Map style, as from the --mapstyle option
    :type map_style: str
    :param apikey: API key, as from the --apikey option
    :type apikey: str or None
    :return: Tile name, tile URL, attribution
    :rtype: tuple of str
    """
    if map_style == 'stamen_terrain':
        url = (
            'https://tiles.stadiamaps.com/tiles/stamen_terrain_background/'
            f'{{z}}/{{x}}/{{y}}.png?api_key={apikey}'
        )
        return 'Stamen Terrain', url, _STAMEN_ATTRIBUTION
    return _TILES[map_style]


def _get_map_extent():
    """
    Return the map extent, from the config file.

    :return: lon_min, lon_max, lat_min, lat_max
    :rtype: tuple of float
    """
    return (
        config.catalog_lon_min, config.catalog_lon_max,
        config.catalog_lat_min, config.catalog_lat_max,
    )


def _create_map(extent, zoom):
    """
    Create the folium map, centered and zoomed on the requested extent.

    :param extent: Map extent (lon_min, lon_max, lat_min, lat_max)
    :type extent: tuple of float
    :param zoom: Map zoom level, or None to fit the map extent
    :type zoom: int or None
    :return: The folium map
    :rtype: folium.Map
    """
    lonmin, lonmax, latmin, latmax = extent
    m = folium.Map(
        location=[(latmin + latmax) / 2, (lonmin + lonmax) / 2],
        zoom_start=zoom if zoom is not None else 5,
        tiles=None,
    )
    if zoom is None:
        m.fit_bounds([[latmin, lonmin], [latmax, lonmax]])
    return m


def _add_tile_layers(m, map_style, apikey):
    """
    Add the base map layers to the map.

    The map style selected with the --mapstyle option is enabled by default,
    while the other styles can be selected interactively. The Stamen Terrain
    style is skipped when no API key is available.

    :param m: The folium map
    :type m: folium.Map
    :param map_style: Map style, as from the --mapstyle option
    :type map_style: str
    :param apikey: API key, as from the --apikey option
    :type apikey: str or None
    """
    if map_style == 'no_basemap':
        return
    available_styles = list(_TILES) + ['stamen_terrain']
    if map_style not in available_styles:
        logger.warning(f'Unknown map style: "{map_style}"')
        return
    if map_style == 'stamen_terrain' and not apikey:
        logger.error(
            'The "stamen_terrain" map style requires an API key. '
            'Use the -k/--apikey option.'
        )
        rq_exit(1)
    styles = [map_style] + [
        style for style in available_styles if style != map_style
    ]
    if not apikey:
        # Stamen Terrain tiles are not available without an API key
        styles.remove('stamen_terrain')
    for style in styles:
        name, url, attribution = _get_tile_definition(style, apikey)
        folium.TileLayer(
            name=name, tiles=url, attr=attribution, show=style == map_style,
        ).add_to(m)
    folium.LayerControl().add_to(m)


def _add_title(m, families):
    """
    Add an HTML title with the trace IDs and the number of families.

    :param m: The folium map
    :type m: folium.Map
    :param families: List of families
    :type families: list of requake.families.Family
    """
    trace_ids = []
    for family in families:
        if family.trace_id is not None and family.trace_id not in trace_ids:
            trace_ids.append(family.trace_id)
    title = f'{len(families)} families'
    if trace_ids:
        title = f'{"|".join(trace_ids)} {title}'
    html = (
        '<div style="position: fixed; top: 8px; left: 55px; z-index: 9999; '
        'background-color: white; padding: 2px 8px; font-size: 14px; '
        f'border-radius: 4px;">{escape(title)}</div>'
    )
    m.get_root().html.add_child(branca.element.Element(html))


def _format_value(value, fmt=''):
    """
    Format a family attribute for the popup.

    :param value: Attribute value
    :type value: any
    :param fmt: Optional format specification
    :type fmt: str
    :return: Formatted value
    :rtype: str
    """
    return 'n/a' if value is None else escape(format(value, fmt))


def _family_popup_html(family):
    """
    Return the HTML content of the popup of a family.

    :param family: Family
    :type family: requake.families.Family
    :return: HTML content
    :rtype: str
    """
    mag_range = (
        f'{_format_value(family.magmin, ".1f")} - '
        f'{_format_value(family.magmax, ".1f")}'
    )
    fields = (
        ('Longitude', _format_value(family.lon, '.4f')),
        ('Latitude', _format_value(family.lat, '.4f')),
        ('Depth', f'{_format_value(family.depth, ".1f")} km'),
        ('Number of events', str(len(family))),
        ('Start time', _format_value(family.starttime)),
        ('End time', _format_value(family.endtime)),
        ('Duration', duration_string(family)),
        ('Magnitude range', mag_range),
        ('Cumulative slip', f'{_format_value(family.cumul_slip, ".2f")} cm'),
        ('Slip rate', f'{_format_value(family.slip_rate, ".1f")} cm/y'),
        ('Cumulative moment',
         f'{_format_value(family.cumul_moment, ".2e")} N&middot;m'),
    )
    title = f'<b>Family {family.number}</b>'
    if family.trace_id is not None:
        title += f'<br><i>{escape(str(family.trace_id))}</i>'
    lines = [title]
    lines.extend(f'{label}: {value}' for label, value in fields)
    return '<br>'.join(lines)


def _add_family_markers(m, families, fcolors, radii):
    """
    Add the family markers to the map.

    :param m: The folium map
    :type m: folium.Map
    :param families: List of families
    :type families: list of requake.families.Family
    :param fcolors: Colors for the families, as RGBA tuples
    :type fcolors: list of tuple
    :param radii: Marker radii, in pixels
    :type radii: list of float
    """
    for family, color, radius in zip(families, fcolors, radii):
        if family.lon is None or family.lat is None:
            logger.warning(
                f'Family "{family.number}" has no coordinates. Skipping it.'
            )
            continue
        popup = folium.Popup(
            folium.Html(_family_popup_html(family), script=True),
            min_width=260,
            max_width=260,
        )
        hexcolor = to_hex(color)
        folium.CircleMarker(
            location=[family.lat, family.lon],
            radius=radius,
            color=hexcolor,
            weight=1,
            fill=True,
            fill_color=hexcolor,
            fill_opacity=0.8,
            popup=popup,
        ).add_to(m)


def _add_size_legend(m, legend, label):
    """
    Add an HTML legend explaining the marker size.

    :param m: The folium map
    :type m: folium.Map
    :param legend: Size legend entries, as (value label, radius) pairs
    :type legend: list of tuple
    :param label: Description of the quantity used for the marker size
    :type label: str
    """
    if not legend:
        return
    rows = []
    for value_label, radius in legend:
        diameter = 2 * radius
        rows.append(
            '<div style="display: flex; align-items: center; '
            f'height: {diameter:.0f}px;">'
            '<span style="display: inline-block; box-sizing: border-box; '
            f'width: {diameter:.0f}px; height: {diameter:.0f}px; '
            'border-radius: 50%; border: 1px solid #555555; '
            'background-color: rgba(136, 136, 136, 0.3); '
            'margin-right: 6px;"></span>'
            f'{escape(value_label)}</div>'
        )
    html = (
        '<div style="position: fixed; bottom: 25px; left: 20px; '
        'z-index: 9999; background-color: rgba(255, 255, 255, 0.8); '
        'padding: 6px 10px; border-radius: 4px; font-size: 13px;">'
        '<div style="font-weight: 600; margin-bottom: 2px;">'
        f'{escape(label)}</div>{"".join(rows)}</div>'
    )
    m.get_root().html.add_child(branca.element.Element(html))


def _legend_tick_labels(colorby, vmin, vmax):
    """
    Return explicit legend tick labels.

    :param colorby: Quantity used to color the families
    :type colorby: str
    :param vmin: Legend minimum value
    :type vmin: float
    :param vmax: Legend maximum value
    :type vmax: float
    :return: Tick labels
    :rtype: list of float
    """
    if colorby == 'family_number':
        # one tick for each of the ten colors of the color map
        return [float(value) for value in range(10)]
    if colorby == 'time':
        # numeric matplotlib dates, relabeled as dates by _time_label_script()
        return [
            vmin + index * (vmax - vmin) / 4
            for index in range(5)
        ]
    locator = MaxNLocator(
        nbins=_MAX_LEGEND_TICKS, integer=colorby == 'number_of_events'
    )
    labels = [
        # get rid of the floating point noise of the locator
        float(f'{value:.12g}')
        for value in locator.tick_values(vmin, vmax)
        if vmin <= value <= vmax
    ]
    return labels or [vmin, vmax]


def _time_label_script():
    """
    Return the JavaScript code that relabels legend ticks as UTC dates.

    :return: JavaScript code
    :rtype: str
    """
    return (
        '<script>'
        '(function () {'
        'function pad(v) { return String(v).padStart(2, "0"); }'
        'function utcDate(mplDate) {'
        f'  var ms = (mplDate - {_UNIX_EPOCH_MPL_DATE!r}) * 86400000;'
        '  var d = new Date(ms);'
        '  return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + '
        '    pad(d.getUTCDate());'
        '}'
        'var attempts = 0;'
        'var timer = setInterval(function () {'
        '  attempts += 1;'
        '  var legend = document.getElementById("legend");'
        '  var ticks = legend ? legend.querySelectorAll(".tick text") : [];'
        '  if (!ticks.length) {'
        '    if (attempts > 40) { clearInterval(timer); }'
        '    return;'
        '  }'
        '  ticks.forEach(function (node) {'
        '    var val = Number(String(node.textContent).replace(/,/g, ""));'
        '    if (isFinite(val)) { node.textContent = utcDate(val); }'
        '  });'
        '  clearInterval(timer);'
        '}, 100);'
        '})();'
        '</script>'
    )


def _add_colormap(m, cmap, norm, colorby):
    """
    Add a colormap legend to the map.

    :param m: The folium map
    :type m: folium.Map
    :param cmap: Matplotlib colormap
    :type cmap: matplotlib.colors.Colormap
    :param norm: Matplotlib normalization object
    :type norm: matplotlib.colors.Normalize
    :param colorby: Quantity used to color the families
    :type colorby: str
    """
    vmin = float(norm.vmin)
    vmax = float(norm.vmax)
    if vmin == vmax:
        vmax = vmin + 1
    if colorby == 'family_number':
        # discrete colormap: one color per value, as for the markers
        colors = [to_hex(cmap(norm(value))) for value in range(10)]
        legend = branca.colormap.StepColormap(
            colors, vmin=vmin, vmax=vmax, caption=cmap.label,
        )
    else:
        colors = [
            to_hex(cmap(index / (_LEGEND_COLORS - 1)))
            for index in range(_LEGEND_COLORS)
        ]
        legend = branca.colormap.LinearColormap(
            colors, vmin=vmin, vmax=vmax, caption=cmap.label,
        )
    legend.tick_labels = _legend_tick_labels(colorby, vmin, vmax)
    # make the legend bar larger than the branca default
    legend.width = 520
    legend.height = 64
    legend.add_to(m)
    if colorby == 'time':
        m.get_root().header.add_child(
            branca.element.Element(_time_label_script())
        )


def _get_output_file(output):
    """
    Return the output file for the map, or None to open it in a browser.

    :param output: Value of the --output option
    :type output: str or None
    :return: Output file, or None
    :rtype: str or None
    """
    if output == 'NO_OUTPUT':
        return None
    if output is None or output.lower() == 'html':
        return f'{_DEFAULT_OUTPUT_BASENAME}.html'
    if output.lower() in _IMAGE_FORMATS:
        logger.error(
            f'Invalid output format "{output}" for the folium backend. '
            'Use "html" or a filename with the ".html" extension.'
        )
        rq_exit(1)
    if not output.lower().endswith('.html'):
        logger.error(
            f'Invalid output file "{output}" for the folium backend. '
            'The output file must have the ".html" extension.'
        )
        rq_exit(1)
    return output


def _save_or_open_map(m, out_file):
    """
    Save the map to an HTML file, or open it in a web browser.

    :param m: The folium map
    :type m: folium.Map
    :param out_file: Output file, or None to open the map in a web browser
    :type out_file: str or None
    """
    if out_file is None:
        file_descriptor, temp_file = tempfile.mkstemp(suffix='.html')
        os.close(file_descriptor)
        m.save(temp_file)
        print('Opening the map in the default web browser...')
        webbrowser.open_new(Path(temp_file).as_uri())
        return
    out_dir = os.path.dirname(out_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    m.save(out_file)
    print(f'Map saved as {out_file}')


def plot_families_map_with_folium(families):
    """
    Plot families on a map, using folium.

    :param families: List of families
    :type families: list of requake.families.Family
    """
    if folium is None:
        logger.error(
            'Folium is not installed. Install it to use the folium map '
            'backend, e.g. with "pip install folium".'
        )
        rq_exit(1)
    args = config.args
    out_file = _get_output_file(args.output)
    m = _create_map(_get_map_extent(), args.zoom)
    _add_tile_layers(m, args.mapstyle, args.apikey)
    _add_title(m, families)
    try:
        fcolors, norm, cmap = family_colors(families)
        radii, legend, size_label = get_family_marker_radii(
            families, args.sizeby)
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    _add_family_markers(m, families, fcolors, radii)
    _add_colormap(m, cmap, norm, args.colorby)
    _add_size_legend(m, legend, size_label)
    _save_or_open_map(m, out_file)
