import pyproj
from shapely.geometry import (
    mapping,
    Point as ShPoint,
    Polygon as ShPolygon,
    MultiPoint as ShMultiPoint
)


class GeoShape(object):
    shape = None

    def __init__(self, lng_lat, proj='EPSG:4326'):
        self.proj = pyproj.Proj(init=proj)
        self.xy = [self.proj(x, y) for x, y in lng_lat]
        self.lat_lng = [(y, x) for x, y in lng_lat]


    def centroid(self):
        lat_lng = self._dateline_in(*self.lat_lng)
        lng_lat = [(lng, lat) for lat, lng in lat_lng]
        shape = self.shape(lng_lat)
        lng, lat = mapping(shape.convex_hull.centroid)['coordinates']
        return self._dateline_out((lat, lng))[0]


    def hull(self):
        lng_lat = [(lng, lat) for lat, lng in self.lat_lng]
        hull = self.shape(lng_lat).convex_hull
        return [(c[1], c[0]) for c in mapping(hull)['coordinates'][0]]


    @staticmethod
    def _dateline_in(*args):
        """Fixes lat-longs that cross the international dateline"""
        lats = [c[0] for c in args]
        lngs = [c[1] for c in args]
        # Standardize combinations of high positive and negative longitudes
        posvals = [c for c in lngs if c >= 100]
        negvals = [c for c in lngs if c <= -100]
        if posvals and negvals:
            # Standardize to positive
            lngs = [c if c >= 0 else 360 - abs(c) for c in lngs]
        return [(lat, lng) for lat, lng in zip(lats, lngs)]


    @staticmethod
    def _dateline_out(*args):
        """Fixes lat-longs that cross the international dateline"""
        lats = [c[0] for c in args]
        lngs = [c[1] for c in args]
        if max(lngs) > 180 :
            lngs = [c - 360 if c > 180 else c for c in lngs]
        if min(lngs) < -180:
            lngs = [c + 360 if c < -180 else c for c in lngs]
        return [(lat, lng) for lat, lng in zip(lats, lngs)]


class Point(GeoShape):
    shape = ShPoint


class Polygon(GeoShape):
    shape = ShPolygon


class MultiPoint(GeoShape):
    shape = ShMultiPoint
