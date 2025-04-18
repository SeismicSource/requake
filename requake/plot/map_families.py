# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot families on a map.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as patheffects
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from obspy.geodetics import gps2dist_azimuth
from ..config import config, rq_exit
from ..families import FamilyNotFoundError, read_selected_families
from .plot_utils import (
    plot_title, hover_annotation, duration_string, family_colors, plot_colorbar
)
from .cached_tiler import CachedTiler
from .map_tiles import (
    EsriHillshade,
    EsriHillshadeDark,
    EsriOcean,
    EsriImagery,
    StamenTerrain,
    WorldStreetMap
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42
TILER = {
    'hillshade': EsriHillshade,
    'hillshade_dark': EsriHillshadeDark,
    'ocean': EsriOcean,
    'satellite': EsriImagery,
    'stamen_terrain': StamenTerrain,
    'street': WorldStreetMap,
}


def _add_tiles(ax, tiler, alpha=1):
    """Add map tiles to basemap."""
    if config.args.zoom is not None:
        tile_zoom_level = config.args.zoom
    else:
        tile_zoom_level = 12 if ax.maxdiagonal <= 100 else 8
        logger.info(f'Map zoom level autoset to: {tile_zoom_level}')
    ax.add_image(tiler, tile_zoom_level, alpha=alpha)


def _make_basemap():
    lonmin = config.catalog_lon_min
    lonmax = config.catalog_lon_max
    latmin = config.catalog_lat_min
    latmax = config.catalog_lat_max
    land_10m = cfeature.NaturalEarthFeature(
        'physical', 'land', '10m',
        edgecolor='face',
        facecolor=cfeature.COLORS['land'])
    ocean_10m = cfeature.NaturalEarthFeature(
        'physical', 'ocean', '10m',
        edgecolor='face',
        facecolor=cfeature.COLORS['water'])
    tile_dir = 'maptiles'
    # Create a GeoAxes
    figsize = (8, 8)
    fig = plt.figure(figsize=figsize)
    map_style = config.args.mapstyle
    api_key = config.args.apikey
    if map_style == 'no_basemap':
        ax = fig.add_subplot(111, projection=ccrs.Mercator())
        ax.add_feature(land_10m)
        ax.add_feature(ocean_10m)
    else:
        tile_dir = 'maptiles'
        tiler = CachedTiler(
            TILER[map_style](apikey=api_key),
            tile_dir
        )
        ax = fig.add_subplot(111, projection=tiler.crs)
    trans = ccrs.Geodetic()
    ax.set_extent([lonmin, lonmax, latmin, latmax], crs=trans)
    diagonal, _, _ = gps2dist_azimuth(latmin, lonmin, latmax, lonmax)
    ax.maxdiagonal = diagonal / 1e3
    if map_style != 'no_basemap':
        _add_tiles(ax, tiler)
    if map_style in {'hillshade', 'hillshade_dark', 'ocean', 'satellite'}:
        ax.attribution_text = 'Map powered by Esri and Natural Earth'
    elif map_style == 'street':
        ax.attribution_text = 'Map powered by Esri and OpenStreetMap'
    elif map_style == 'stamen_terrain':
        ax.attribution_text = 'Map powered by Stamen Design and Natural Earth'
    else:
        ax.attribution_text = 'Map powered by Natural Earth'
    ax.gridlines(draw_labels=True, color='#777777', linestyle='--')
    ax.hover_annotation_element = 'markers'
    return fig, ax


def map_families():
    """
    Plot families on a map.
    """
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    fig, ax = _make_basemap()
    trans = ccrs.PlateCarree()
    try:
        fcolors, norm, cmap = family_colors(families)
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    trace_ids = []
    for family, color in zip(families, fcolors):
        if family.trace_id not in trace_ids and family.trace_id is not None:
            trace_ids.append(family.trace_id)
        fn = family.number
        nevents = len(family)
        duration_str = duration_string(family)
        label = (
            f'Family {fn}\n{nevents} evts\n{duration_str}\n'
            f'Z {family.depth:.1f} km'
        )
        # draw markers using a double border:
        # white, then black (through path_effects)
        pe = [patheffects.withStroke(linewidth=2, foreground='k')]
        marker = ax.scatter(
            family.lon, family.lat,
            marker='o', s=100,
            linewidths=1, facecolor=color, edgecolor='w', path_effects=pe,
            transform=trans, label=label, zorder=10)
        marker.to_annotate = True
    plot_colorbar(fig, ax, cmap, norm)
    plot_title(
        ax, len(families), trace_ids, vertical_position=1.05, fontsize=10)

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox={'boxstyle': 'round', 'fc': 'w'},
        zorder=20
    )
    annot.set_visible(False)
    annot.hover_annotation = True
    fig.canvas.mpl_connect('motion_notify_event', hover_annotation)
    plt.show()
