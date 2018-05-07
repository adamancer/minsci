import csv
import datetime as dt
import time
from collections import namedtuple

import requests
import requests_cache


requests_cache.install_cache()


def get(**kwargs):
    url = 'https://geogallery.si.edu/portal'
    params = {
        'format': 'json',
        'schema': 'simpledwr',
        'limit': 1000
    }
    params.update(kwargs)
    response = requests.get(url, params=params)
    print 'Retrieving {}...'.format(response.url)
    if not response.from_cache:
        time.sleep(3)
    if response.status_code == 200:
        data = response.json()
        if not params.get('offset'):
            total = data.get('response', {}) \
                        .get('attributes', {}) \
                        .get('totalSearchHits', 0)
            if total == -1:
                print 'More than 1,000 records match this query'
            else:
                print '{:,} records match this query'.format(total)
        try:
            records = data.get('response', {}) \
                          .get('content', {}) \
                          .get('SimpleDarwinRecordSet', [])
        except AttributeError:
            diagnostics = data.get('response', {}).get('diagnostics', [])
            print '\n'.join(['DIAGNOSTIC: ' + d['diagnostic'] for d in diagnostics])
        else:
            return [rec['SimpleDarwinRecord'] for rec in records]
    return []


def get_all(**kwargs):
    offset = kwargs.pop('offset', 0)
    records = []
    while True:
        new = get(offset=offset, **kwargs)
        if new:
            records.extend(new)
            offset += len(new)
        if not new or len(new) < 1000:
            break
    return records


def download(**kwargs):
    records = get_all(**kwargs)
    if records:
        keys = []
        for rec in records:
            keys.extend(rec.keys())
        keys = sorted(list(set(keys)))
        fn = 'download_{}.csv'.format(dt.datetime.now().strftime('%Y%m%dt%H%M%S'))
        with open(fn, 'wb') as f:
            writer = csv.writer(f)
            writer.writerow(keys)
            for rec in records:
                writer.writerow([rec.get(key, '').encode('utf-8') for key in keys])
        print 'Results saved as {}'.format(fn)
    else:
        print 'No records found!'
