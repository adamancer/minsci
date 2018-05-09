"""Defines methods to request data from the NMNH Geology Collections Data Portal"""

import codecs
import csv
import datetime as dt
import os
import re
import time
from collections import namedtuple

import requests


def get(**kwargs):
    """Returns one page of records (<=1000 records)"""
    url = 'https://geogallery.si.edu/portal'
    params = {
        'format': 'json',
        'schema': 'simpledwr',
        'limit': 1000
    }
    params.update(kwargs)
    response = requests.get(url, params=params)
    print 'Retrieving {}...'.format(response.url)
    if not hasattr(response, 'from_cache') or not response.from_cache:
        time.sleep(2)
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
    """Returns all matching records (1000 at a time)"""
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
    """Saves a set of records as a CSV"""
    records = get_all(**kwargs)
    if records:
        keys = []
        for rec in records:
            keys.extend(rec.keys())
        keys = sorted(list(set(keys)))
        fn = filename('portal')
        with open(fn, 'wb') as f:
            writer = csv.writer(f)
            writer.writerow(keys)
            for rec in records:
                writer.writerow([rec.get(key, '').encode('utf-8') for key in keys])
        encode_for_excel(fn)
        print 'Results saved as {}'.format(fn)
    else:
        print 'No records found!'


def parse_config():
    """Parses the current portal keyword definitions"""
    args = []
    with open(os.path.join(os.path.dirname(__file__), 'files', 'config.txt'), 'rb') as f:
        for line in f:
            arg = {}
            label, definition = line.strip().split('\t', 1)
            # Skip fields that have required values
            if label in ['schema', 'limit', 'format', 'bcp']:
                continue
            if 'One of' in definition:
                definition, options = definition.rstrip('.').split(' One of ')
                arg['choices'] = re.split(',? or ', options)
            arg['dest'] = label
            arg['type'] = str
            arg['action'] = 'append'
            arg['help'] = definition
            args.append(arg)
    return args


def filename(stem='portal'):
    """Creates a datestamped filename"""
    return '{}_{}.csv'.format(stem, dt.datetime.now().strftime('%Y%m%dt%H%M%S'))

def encode_for_excel(fp, encoding='utf-8'):
    """Re-encode a document for Excel"""
    with open(fp, 'rb') as f:
        text = f.read().decode(encoding)
    with open(fp, 'wb') as f:
        f.write(codecs.BOM_UTF16_LE)
        f.write(text.encode('utf-16-le'))
