"""Provides tools to interact with a dictionary of arbitrary depth"""
from __future__ import print_function
from __future__ import unicode_literals

import logging
logger = logging.getLogger(__name__)

logger.debug('Initializing dicts submodule...')

from .deepdict import DeepDict
from .lockabledict import LockableDict
