# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Map tilers

:copyright:
    2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from cartopy.io.img_tiles import GoogleWTS
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class StamenTerrain(GoogleWTS):
    """
    Retrieves Stamen Terrain tiles from stadiamaps.com.
    """
    def __init__(self,
                 apikey,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        return (
            'http://tiles.stadiamaps.com/tiles/stamen_terrain_background/'
            f'{z}/{x}/{y}.png?api_key={self.apikey}'
        )


class EsriHillshade(GoogleWTS):
    """
    Retrieves Esri Hillshade tiles from argisonline.com.
    """
    def __init__(self,
                 apikey=None,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        maxz = 23
        if z > maxz:
            logger.warning(
                f'Tile zoom level {z} is greater than max zoom level {maxz}. '
                f'Setting zoom level to {maxz}.')
            z = maxz
        return (
            'https://server.arcgisonline.com/ArcGIS/rest/services/'
            f'Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}.jpg'
        )


class EsriHillshadeDark(GoogleWTS):
    """
    Retrieves Esri Hillshade Dark tiles from argisonline.com.
    """
    def __init__(self,
                 apikey=None,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        maxz = 23
        if z > maxz:
            logger.warning(
                f'Tile zoom level {z} is greater than max zoom level {maxz}. '
                f'Setting zoom level to {maxz}.')
            z = maxz
        return (
            'https://server.arcgisonline.com/ArcGIS/rest/services/'
            f'Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}.jpg'
        )


class EsriOcean(GoogleWTS):
    """
    Retrieves Esri Ocean tiles from argisonline.com.
    """
    def __init__(self,
                 apikey=None,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        maxz = 16
        if z > maxz:
            logger.warning(
                f'Tile zoom level {z} is greater than max zoom level {maxz}. '
                f'Setting zoom level to {maxz}.')
            z = maxz
        return (
            'https://server.arcgisonline.com/ArcGIS/rest/services/'
            f'Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}.jpg'
        )


class EsriImagery(GoogleWTS):
    """
    Retrieves Esri Imagery tiles from argisonline.com.
    """
    def __init__(self,
                 apikey=None,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        maxz = 23
        if z > maxz:
            logger.warning(
                f'Tile zoom level {z} is greater than max zoom level {maxz}. '
                f'Setting zoom level to {maxz}.')
            z = maxz
        return (
            'https://server.arcgisonline.com/ArcGIS/rest/services/'
            f'World_Imagery/MapServer/tile/{z}/{y}/{x}.jpg'
        )


class WorldStreetMap(GoogleWTS):
    """
    Retrieves World Street Map tiles from argisonline.com.
    """
    def __init__(self,
                 apikey=None,
                 cache=False):
        super().__init__(cache=cache, desired_tile_form="RGBA")
        self.apikey = apikey

    def _image_url(self, tile):
        x, y, z = tile
        return (
            'https://server.arcgisonline.com/ArcGIS/rest/services/'
            f'World_Street_Map/MapServer/tile/{z}/{y}/{x}.jpg'
        )
