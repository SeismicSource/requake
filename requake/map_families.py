# -*- coding: utf8 -*-
"""
Plot families on a map.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt
import cartopy.feature as cfeature
from obspy.geodetics import gps2dist_azimuth
from .cached_tiler import CachedTiler
from .families import read_selected_families
from .rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def _make_basemap(config):
    lonmin = config.catalog_lon_min
    lonmax = config.catalog_lon_max
    latmin = config.catalog_lat_min
    latmax = config.catalog_lat_max
    tile_dir = 'maptiles'
    stamen_terrain = CachedTiler(cimgt.Stamen('terrain-background'), tile_dir)
    # Create a GeoAxes
    figsize = (8, 8)
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection=stamen_terrain.crs)
    trans = ccrs.Geodetic()
    ax.set_extent([lonmin, lonmax, latmin, latmax], crs=trans)
    diagonal, _, _ = gps2dist_azimuth(latmin, lonmin, latmax, lonmax)
    diagonal /= 1e3
    tile_zoom_level = 12 if diagonal <= 100 else 8
    ax.add_image(stamen_terrain, tile_zoom_level)
    ax.gridlines(draw_labels=True, color='#777777', linestyle='--')
    countries = cfeature.NaturalEarthFeature(
        category='cultural',
        name='admin_0_countries',
        scale='10m',
        facecolor='none')
    ax.add_feature(countries, edgecolor='k')
    return fig, ax


def map_families(config):
    try:
        families = read_selected_families(config)
    except Exception as msg:
        logger.error(msg)
        rq_exit(1)
    fig, ax = _make_basemap(config)
    trans = ccrs.PlateCarree()
    cmap = cm.tab10
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    markers = []
    for family in families:
        fn = family.number
        nevents = len(family)
        duration = (family.endtime - family.starttime)/(365*24*60*60)
        label = 'Family {}\n{} evts\n{:.1f} yrs\nZ {:.1f} km'.format(
            fn, nevents, duration, family.depth)
        marker = ax.scatter(
            family.lon, family.lat,
            marker='o', s=100,
            color=cmap(norm(fn % 10)), edgecolor='k',
            transform=trans, label=label, zorder=10)
        markers.append(marker)
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(10), pad=0.1)
    cbar.ax.set_ylabel('mod(family number, 10)')

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox=dict(boxstyle='round', fc='w'),
        zorder=20
    )
    annot.set_visible(False)

    def hover(event):
        vis = annot.get_visible()
        if event.inaxes == ax:
            for marker in markers:
                cont, ind = marker.contains(event)
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
                else:
                    marker.set_linewidth(1)
                    if vis:
                        annot.set_visible(False)
                        fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', hover)

    plt.show()
