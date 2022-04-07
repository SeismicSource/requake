#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Functions for computing P and S arrivals.

:copyright:
    2021-2022 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
model = TauPyModel(model='ak135')


def get_arrivals(trace_lat, trace_lon, ev_lat, ev_lon, ev_depth):
    dist_deg = locations2degrees(trace_lat, trace_lon, ev_lat, ev_lon)
    distance, _, _ = gps2dist_azimuth(
        trace_lat, trace_lon, ev_lat, ev_lon)
    distance /= 1e3
    P_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['p', 'P'])
    S_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['s', 'S'])
    return P_arrivals[0], S_arrivals[0], distance, dist_deg
