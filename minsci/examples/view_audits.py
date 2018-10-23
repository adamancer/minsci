"""Creates a readable report summarizing data from eaudits

Multiple audits on the same record are summarized into first and last values.

You must provide your own report to run this script. The report from eaudits
must be exported as XML and include the following fields:
    + irn
    + AudTable
    + AudOperation
    + AudProgram
    + AudUser
    + AudDate
    + AudTime
    + AudKey
    + AudOldValue_tab
    + AudNewValue_tab
"""
from __future__ import unicode_literals

import csv
import os

from minsci.xmu.tools.audits import Auditor


# The optional users and modules arguments can be used to filter the original
# report to a subset. For example, this formulation means that only my audits
# will be reported. Both users and modules should be given as a list.
#
# By default, summary and timestamp tags are not shown in the report; this
# behavior can be modified using the blacklist and whitelist keyword arguments.
xmudata = Auditor('eaudits.xml', percent_to_review=100, users=['mansura'])

# Retrieve a list of the irns modified for each module
xmudata.fast_iter(xmudata.itermodified)
with open('modified.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['module', 'irn'])
    for module in sorted(xmudata.records):
        for irn in sorted(list(set(xmudata.records[module]))):
            writer.writerow([module, irn])

# Write a readable summary of the changes from audits. The resulting report
# can be viewed from your web browser.
xmudata.records = {}  # reset the records container
xmudata.fast_iter(report=10000, callback=xmudata.finalize)
xmudata.write_html(os.path.join('reports', 'eaudits.htm'))
