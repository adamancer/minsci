"""Provides helper functions used throughout the minsci module"""
from __future__ import unicode_literals

import logging.config
import os
import yaml

with open(os.path.join(os.path.dirname(__file__), 'logging.yml')) as f:
    logging.config.dictConfig(yaml.safe_load(f.read()))
