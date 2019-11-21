"""Provides helper functions used throughout the minsci module"""
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())
