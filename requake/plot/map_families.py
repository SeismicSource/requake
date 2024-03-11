# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot families on a map.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib import colors
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from obspy.geodetics import gps2dist_azimuth
from .cached_tiler import CachedTiler
from .map_tiles import (
    EsriHillshade,
    EsriHillshadeDark,
    EsriOcean,
    EsriImagery,
    StamenTerrain,
)
from ..families.families import FamilyNotFoundError, read_selected_families
from ..config.rq_setup import rq_exit
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
}


def _add_tiles(config, ax, tiler, alpha=1):
    """Add map tiles to basemap."""
    if config.args.zoom is not None:
        tile_zoom_level = config.args.zoom
    else:
        tile_zoom_level = 12 if ax.maxdiagonal <= 100 else 8
        logger.info(f'Map zoom level autoset to: {tile_zoom_level}')
    ax.add_image(tiler, tile_zoom_level, alpha=alpha)


def _make_basemap(config):
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
        _add_tiles(config, ax, tiler)
    if map_style in {'hillshade', 'hillshade_dark', 'ocean', 'satellite'}:
        ax.attribution_text = 'Map powered by Esri and Natural Earth'
    elif map_style == 'stamen_terrain':
        ax.attribution_text = 'Map powered by Stamen Design and Natural Earth'
    else:
        ax.attribution_text = 'Map powered by Natural Earth'
    ax.gridlines(draw_labels=True, color='#777777', linestyle='--')
    return fig, ax


def map_families(config):
    """
    Plot families on a map.
    """
    try:
        families = read_selected_families(config)
    except (FileNotFoundError, FamilyNotFoundError) as m:
        logger.error(m)
        rq_exit(1)
    fig, ax = _make_basemap(config)
    trans = ccrs.PlateCarree()
    cmap = mpl.colormaps['tab10']
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    markers = []
    for family in families:
        fn = family.number
        nevents = len(family)
        duration = (family.endtime - family.starttime)/(365*24*60*60)
        label = (
            f'Family {fn}\n{nevents} evts\n{duration:.1f} yrs\n'
            f'Z {family.depth:.1f} km'
        )
        marker = ax.scatter(
            family.lon, family.lat,
            marker='o', s=100,
            color=cmap(norm(fn % 10)), edgecolor='k',
            transform=trans, label=label, zorder=10)
        markers.append(marker)
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(10), pad=0.1, ax=ax)
    cbar.ax.set_ylabel('mod(family number, 10)')

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox={'boxstyle': 'round', 'fc': 'w'},
        zorder=20
    )
    annot.set_visible(False)

    def hover(event):
        vis = annot.get_visible()
        if event.inaxes == ax:
            for marker in markers:
                cont, _ind = marker.contains(event)
                if cont:
                    color = marker.get_facecolor()[0]
                    marker.set_linewidth(3)
                    annot.xy = (event.xdata, event.ydata)
                    annot.set_text(marker.get_label())
                    annot.get_bbox_patch().set_facecolor(color)
                    annot.get_bbox_patch().set_alpha(0.8)
                    annot.set_visible(True)
                    fig.canvas.draw_idle()
                    break
                marker.set_linewidth(1)
                if vis:
                    annot.set_visible(False)
                    fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', hover)

    plt.show()
