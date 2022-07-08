"""Provides tools to read, write, and otherwise process EMu XML files"""
import logging
logger = logging.getLogger(__name__)

logger.debug('Initializing xmu submodule...')

from .xmu import XMu, write, FIELDS, RECORD_SUCCEEDED, RECORD_FAILED, STOP_FAST_ITER
from .xmungo import XMungo, MongoBot
from .fields import XMuField, is_tab, is_ref, is_mod, strip_tab, strip_mod
from .containers.xmurecord import XMuRecord
from .containers.auditrecord import AuditRecord
from .containers.mediarecord import MediaRecord, EmbedFromEMu
from .containers.minscirecord import MinSciRecord
from .containers.transactionrecord import TransactionItem, TransactionRecord
