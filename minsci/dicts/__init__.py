"""Provides tools to interact with a dictionary of arbitrary depth"""
import logging
logger = logging.getLogger(__name__)

logger.debug('Initializing dicts submodule...')

from .deepdict import DeepDict
from .lockabledict import LockableDict
