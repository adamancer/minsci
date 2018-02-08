"""Provides tools to interact with various georeferencing webservices"""

print 'Initializing geobots submodule...'

from .geobots import GeoNamesBot
from .containers import (GeoList, NAME_TO_ABBR, ABBR_TO_NAME,
                         FROM_COUNTRY_CODE, TO_COUNTRY_CODE)
