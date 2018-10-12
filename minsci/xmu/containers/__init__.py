"""Defines module-specific containers for working with EMu data"""
from __future__ import print_function
from __future__ import unicode_literals

print('Initializing xmu.containers submodule...')

from .xmurecord import XMuRecord
from .auditrecord import AuditRecord
from .bibliorecord import BiblioRecord
from .mediarecord import MediaRecord, EmbedFromEMu
from .minscirecord import MinSciRecord
