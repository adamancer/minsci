from __future__ import print_function
from __future__ import unicode_literals
import csv

from .portal import get, get_simpledwr, encode_for_excel, timestamped
from ..geobots.plss import TRS


def meteorites(**kwargs):
    defaults = {
        'format': 'json',
        'schema': 'simpledwr',
        'limit': 1000
    }
    kwargs.update(defaults)
    offset = kwargs.pop('offset', 0)
    records = []
    while True:
        new = get(callback=get_simpledwr,
                  collection='meteorites',
                  offset=offset,
                  **kwargs)
        if new:
            records.extend(new)
            offset += len(new)
        if not new or len(new) < 1000:
            break
    # Get names
    names = {}
    for rec in records:
        name = rec['catalogNumber'].split('|')[0].rsplit(',', 1)[0].strip()
        names.setdefault(name, []).append(rec.get('higherGeography', ''))
    fn = filename('meteorites')
    antarctics = {}
    with open(fn, 'w') as f:
        writer = csv.writer(f, dialect='excel-tab')
        writer.writerow(['Name', 'Count', 'Antarctic'])
        for name in sorted(names):
            count = len(names[name])
            antarctic = 'x' if names[name][0].startswith('Antarctica') else ''
            if antarctic:
                antarctics[name] = len(names[name])
            row = [name, count, antarctic]
            writer.writerow([u'{}'.format(s).encode('utf-8') for s in row])
    encode_for_excel(fn)
    # Report total meteorites found
    print('Found {:,} total meteorites ({:,} distinct)'.format(len(records),
                                                               len(names)))
    # Report total Antarctic meteorites found
    num_antarctics = sum(antarctics.values())
    print('Found {:,} Antarctic meteorites ({:,} distinct)'.format(num_antarctics,
                                                                   len(antarctics)))
    print('Results saved as {}'.format(fn))


def plss(**kwargs):
    trs = TRS(kwargs['string'], kwargs['state'])
    print('Querying BLM webservice...')
    boxes = trs.find()
    if len(boxes) == 1:
        print('Exactly one match found!')
    elif len(boxes) > 1:
        print('Multiple matches found!')
    else:
        print('No matches found!')
    for i, box in enumerate(boxes):
        if len(boxes) > 1:
            print('MATCH #{}'.format(i + 1))
        print('Polygon:', box)
        print('Remarks:', trs.describe(boxes))