"""Defines module-specific containers for working with EMu data"""
import logging
logger = logging.getLogger(__name__)

logger.debug('Initializing xmu.containers submodule...')

from .xmurecord import XMuRecord
from .auditrecord import AuditRecord
from .bibliorecord import BiblioRecord
from .mediarecord import MediaRecord, EmbedFromEMu
from .minscirecord import MinSciRecord
