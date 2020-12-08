"""Provides tools to read, write, and otherwise process EMu XML files"""
import logging
logger = logging.getLogger(__name__)

logger.debug('Initializing xmu submodule...')

from .xmu import XMu, write, FIELDS
from .xmungo import XMungo, MongoBot
from .fields import is_table, is_reference
from .containers.xmurecord import XMuRecord
from .containers.auditrecord import AuditRecord
from .containers.mediarecord import MediaRecord, EmbedFromEMu
from .containers.minscirecord import MinSciRecord
from .containers.transactionrecord import TransactionItem, TransactionRecord
