"""Defines methods for calculating distances and other site properties"""

import logging
logger = logging.getLogger(__name__)

import csv
import math
import os
import re
from collections import namedtuple

import yaml
from geographiclib.geodesic import Geodesic
from shapely.geometry import mapping
from titlecase import titlecase

from .shapes import MultiPoint
from ....helpers import oxford_comma
from ....standardizer import Standardizer


PointWithUncertainty = namedtuple('PointWithUncertainty', ['latitude',
                                                           'longitude',
                                                           'hull',
                                                           'radius'])
Corners = namedtuple('Corners', ['ne', 'se', 'sw', 'nw'])
Dimensions = namedtuple('Dimensions', ['width', 'height'])


FILES = os.path.realpath(os.path.join(__file__, '..', '..', 'files'))
GEODESIC = Geodesic.WGS84


def get_corners(box):
    """Determines the corners of a bounding box"""
    box = _float(*box)
    lats = [c[0] for c in box]
    lngs = [c[1] for c in box]
    ne = (max(lats), min(lngs))
    se = (min(lats), min(lngs))
    sw = (min(lats), max(lngs))
    nw = (max(lats), max(lngs))
    return Corners(ne, se, sw, nw)


def get_size(polygon):
    """Calcualtes the width and height of a polygon"""
    crnr = get_corners(polygon)
    width = get_distance(crnr.ne[0], crnr.ne[1], crnr.nw[0], crnr.nw[1])
    height = get_distance(crnr.ne[0], crnr.ne[1], crnr.se[0], crnr.sw[1])
    return Dimensions(width, height)


def dec2dms(dec, is_lat):
    """Converts decimal degrees to degrees-minutes-seconds

    Args:
        dec (float): a coordinate as a decimal
        is_lat (bool): specifies if the coordinate is a latitude

    Returns:
        Coordinate in degrees-minutes-seconds
    """
    # Force longitude if decimal degrees more than 90
    if is_lat and dec > 90:
        raise ValueError('Invalid latitude: {}'.format(dec))
    # Get degrees-minutes-seconds
    degrees = abs(int(dec))
    minutes = 60. * (abs(dec) % 1)
    seconds = 60. * (minutes % 1)
    minutes = int(minutes)
    if seconds >= 60:
        minutes += 1
        seconds -= 60
    if minutes == 60:
        degrees += 1
        minutes = 0
    if dec >= 0:
        hemisphere = 'N' if is_lat else 'E'
    else:
        hemisphere = 'S' if is_lat else 'W'
    # FIXME: Estimate precision based on decimal places
    mask = '{} {} {} {}'
    return mask.format(degrees, minutes, seconds, hemisphere)


def get_azimuth(bearing):
    """Converts a compass bearing to an azimuth

    Currently this function handles bearings like N, NE, NNE, or N40E.
    """
    # Set base values for each compass direction
    vals = {'N': 0 if 'E' in bearing else 360, 'S': 180, 'E': 90, 'W': 270}
    # Find the components of the bearing
    pattern = ('([NSEW])(\d*)([NSEW]?)([NSEW]?)')
    match = re.search(pattern, bearing)
    d1, deg, d2, d3 = [match.group(i) for i in range(1, 5)]
    v1, v2, v3 = [float(vals.get(d, 0)) for d in [d1, d2, d3]]
    # Swap the second and third coordinates if both are populated
    if d2 and d3:
        v2, v3 = v3, v2
        d2, d3 = d3, d2
    deg = float(deg) if deg.isnumeric() else 0
    # Determine the quadrant in which the azimuth falls
    quad = ('N' if 'N' in bearing else 'S') + ('E' if 'E' in bearing else 'W')
    # The sign of the major direction is postive when the azimuth is NE or SW
    s2 = 1 if quad in ['NE', 'SW'] else -1
    # The sign of the minor direction is postive when the azimuth is NW or SE
    s3 = 1 if quad in ['NW', 'SE'] else -1
    # Zero the second major direction if same as first (e.g., ENE) or if
    # a precise bearing is given (e.g., N40E)
    if (d1 == d2 and d3) or deg:
        d2 = 0
    # Calculate the azimuth
    azimuth = v1 + (45 if d2 else 0) * s2 + (22.5 if d3 else 0) * s3 + deg * s2
    if azimuth < 0 or azimuth == 360:
        return 360 - azimuth
    logger.debug('Calculated azimuth={} from bearing={}'.format(azimuth,
                                                                bearing))
    return azimuth


def get_distance(lat1, lng1, lat2, lng2):
    """Calculates the distance in kilometers between two points"""
    lat1, lng1, lat2, lng2 = _float(lat1, lng1, lat2, lng2)
    result = GEODESIC.Inverse(lat1, lng1, lat2, lng2)
    return result['s12'] / 1000


def get_distance_and_bearing(lat1, lng1, lat2, lng2):
    """Calculates the distance in kilometers and bearing between two points"""
    lat1, lng1, lat2, lng2 = _float(lat1, lng1, lat2, lng2)
    result = GEODESIC.Inverse(lat1, lng1, lat2, lng2)
    return result['s12'] / 1000


def get_simple_point(lat, lng, distance_km, bearing):
    """Calculates point at a distance along a bearing"""
    lat, lng, distance_km = _float(lat, lng, distance_km)
    azimuth = bearing
    if not isinstance(bearing, (float, int)):
        azimuth = get_azimuth(bearing)
    result = GEODESIC.Direct(lat, lng, azimuth, distance_km * 1000)
    return result['lat2'], result['lon2']


def get_point(coords, *args, **kwargs):
    """Calculates point at a distance along a bearing with uncertainty"""
    if len(coords) == 1:
        lat, lng = coords[0]
        point = get_point_from_coords(lat, lng, *args, **kwargs)
    elif len(coords) == 2 and not isinstance(coords[0], (list, tuple)):
        lat, lng = coords
        point = get_point_from_coords(lat, lng, *args, **kwargs)
    elif len(coords) == 5:
        point = get_point_from_box(coords, *args, **kwargs)
    else:
        raise ValueError('Lines and complex polygons not'
                         ' supported: {}'.format(coords))
    return point


def get_point_from_coords(lat, lng, distance_km, bearing,
                          err_degrees=None, err_distance=None):
    """Calculates point at a distance along a bearing with uncertainty"""
    lat, lng, distance_km = _float(lat, lng, distance_km)
    # Get uncertainty of the distance
    if err_distance is None:
        err_distance = 0.25
    err_distance = distance_km * err_distance
    min_dist, max_dist = distance_km - err_distance, distance_km + err_distance
    # Get error parameters for the azimuth
    azimuth = bearing
    if not isinstance(azimuth, float):
        azimuth = get_azimuth(bearing)
    if err_degrees is None:
        if not azimuth % 90:
            err_degrees = 30
        elif not azimuth % 45:
            err_degrees = 15
        elif not azimuth % 22.5:
            err_degrees = 5
        else:
            err_degrees = 5
    else:
        err_degrees = azimuth * err_degrees
    az1, az2 = azimuth + err_degrees, azimuth - err_degrees
    # Calculate the point, hull, and radius
    point = get_simple_point(lat, lng, distance_km, azimuth)
    hull = [
        get_simple_point(lat, lng, min_dist, az1),
        get_simple_point(lat, lng, max_dist, az1),
        get_simple_point(lat, lng, min_dist, az2),
        get_simple_point(lat, lng, max_dist, az2)
    ]
    dists = [get_distance(point[0], point[1], pt[0], pt[1]) for pt in hull]
    return PointWithUncertainty(point[0], point[1], hull, max(dists))


def get_point_from_box(polygon, distance_km, bearing,
                       err_degrees=None, err_distance=None):
    """Calculates point with error from a non-point reference"""
    polygon = _float(*polygon)
    # Get point at distance from centroid of polygon
    corners = get_corners(polygon)
    points = [(lng, lat) for lat, lng in corners]
    lat, lng = MultiPoint(points).centroid()
    point = get_simple_point(lat, lng, distance_km, bearing)
    # Get points with error from each corner
    args = [distance_km, bearing, err_degrees, err_distance]
    points = []
    for corner in corners:
        lat, lng = corner
        points.extend(get_point((lat, lng), *args).hull)
    # Shapely orders coordinates as x, y so reorder to lng, lat
    points = [(lng, lat) for lat, lng in points]
    lat, lng = point
    hull = MultiPoint(points).hull()
    dists = [get_distance(lat, lng, pt[0], pt[1]) for pt in hull]
    return PointWithUncertainty(lat, lng, hull, max(dists))


def get_polygon(lat, lng, distance_km, sides=4):
    """Calculates a polygon around a central point"""
    points = []
    for i in range(sides):
        points.append(get_simple_point(lat, lng, distance_km, i * 360 / sides))
    return points


def get_box(lat, lng, distance_km):
    """Calculates a box around a central point"""
    return get_polygon(lat, lng, distance_km, 4)


def get_circle(lat, lng, distance_km):
    """Calculates a circle around a central point"""
    return get_polygon(lat, lng, distance_km, 20)


def get_centroid(lats, lngs):
    """Calculates the centroid for a set of lat-longs"""
    lats, lngs = _float(lats, lngs)
    if not isinstance(lats + lngs, list):
        return (lats, lngs)
    points = [(lng, lat) for lat, lng in zip(lats, lngs)]
    return MultiPoint(points).centroid()


def encircle(lats, lngs):
    """Calculates centroid and radius for a circle around a set of lat-longs"""
    lats, lngs = _float(lats, lngs)
    if not isinstance(lats + lngs, list):
        return (lats, lngs, 0)
    # Calculate the outline and properties of the hull
    points = [(lng, lat) for lat, lng in zip(lats, lngs)]
    geoshape = MultiPoint(points)
    clat, clng = geoshape.centroid()
    hull = geoshape.hull()
    # Calculate distance between centroid and each point
    radius = max([get_distance(lat, lng, clat, clng) for lng, lat in points])
    # Fix any corrections made to account for the dateline
    return PointWithUncertainty(clat, clng, hull, radius)


def _float(*args):
    """Converts vals or lists to floats"""
    results = []
    for arg in args:
        if isinstance(arg, (list, tuple)):
            results.append(type(arg)([float(val) for val in arg]))
        else:
            results.append(float(arg))
    return results


def read_config():
    """Reads the sites config file"""
    config = yaml.safe_load(open(os.path.join(FILES, 'config.yaml'), 'r'))
    codes = {}
    classes = {}
    with open(os.path.join(FILES, 'codes.csv'), 'r', encoding='utf-8-sig') as f:
        rows = csv.reader(f, dialect='excel')
        keys = next(rows)
        for row in rows:
            rowdict = {k: v for k, v in zip(keys, row)}
            try:
                rowdict['SizeIndex'] = int(rowdict['SizeIndex'][:-3])
            except ValueError:
                pass
            code = rowdict['FeatureCode']
            codes[code] = rowdict
            classes.setdefault(rowdict['FeatureClass'], []).append(code)
    # Map features classes to related feature codes
    for attr, classes_and_codes in config['codes'].items():
        codes_ = []
        for code in classes_and_codes:
            try:
                expanded = classes[code]
            except KeyError:
                codes_.append(code)
            else:
                for keyword in ['CONT', 'OCN']:
                    try:
                        expanded.remove(keyword)
                    except ValueError:
                        pass
                # HACK to get a list of undersea codes
                if code == 'U':
                    undersea = expanded
                codes_.extend(expanded)
        config['codes'][attr] = codes_
    config['codes']['undersea'] = undersea
    return config, codes


def distance_on_unit_sphere(lat1, lng1, lat2, lng2, unit='km'):
    """Calculates the distance in km between two points on a sphere

    From http://www.johndcook.com/blog/python_longitude_latitude/

    Args:
        lat1 (int or float): latitude of first coordinate pair
        lng1 (int or float): longitude of first coordinate pair
        lat2 (int or float): latitude of second coordinate pair
        lng2 (int or float): longitdue of second coordinate pair

    Returns:
        Distance between two points in km
    """
    raise Exception('Deprecated. Use get_discance instead.')
    # Return 0 if the two sets of coordinates are the same
    if lat1 == lat2 and lng1 == lng2:
        return 0
    # Coerce strings to floats
    lat1, lng1, lat2, lng2 = [float(s) if not isinstance(s, float) else s
                              for s in [lat1, lng1, lat2, lng2]]
    # Convert latitude and lngitude to spherical coordinates in radians.
    degrees_to_radians = math.pi / 180.
    phi1 = (90. - lat1) * degrees_to_radians
    phi2 = (90. - lat2) * degrees_to_radians
    # theta = longitude
    theta1 = lng1 * degrees_to_radians
    theta2 = lng2 * degrees_to_radians
    # Compute spherical distance from spherical coordinates.
    # For two locations in spherical coordinates
    # (1, theta, phi) and (1, theta', phi')
    # cosine( arc length ) =
    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length
    cos = (math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2) +
           math.cos(phi1) * math.cos(phi2))
    arc = math.acos(cos)
    # Remember to multiply arc by the radius of the earth
    # in your favorite set of units to get length.
    units = {
        'km': 6371.
    }
    return arc * units[unit]


def eq(val1, val2, std=None, strict=True):
    """Tests if values are equivalent for the purposes of comparing sites"""
    if std is None:
        std = Standardizer()
    # Standardize values
    vals = [val1, val2]
    for i, val in enumerate(vals):
        if isinstance(val, (list, set)):
            vals[i] = set([std(s) for s in val])
        elif isinstance(val, dict):
            vals[i] = {std(k): std(v) for k, v in val.items()}
        else:
            vals[i] = std(val)
    val1, val2 = vals
    # Compare values
    if isinstance(val1, set) and isinstance(val2, set):
        return val1 == val2 if strict else val1.intersection(val2)
    elif isinstance(val1, set):
        return val2 in val1
    elif isinstance(val2, set):
        return val1 in val2
    else:
        return val1 == val2
