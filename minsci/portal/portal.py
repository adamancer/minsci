"""Defines methods to request data from the NMNH Geology Collections Data Portal"""

import codecs
import csv
import datetime as dt
import os
import re
import time
from collections import namedtuple

import requests
from lxml import etree


Results = namedtuple('Results', ['records', 'last_id'])


def get(url='https://geogallery.si.edu/portal', callback=None, **kwargs):
    """Returns one page of records (<=1000 records)"""
    response = requests.get(url, params=kwargs)
    print 'Retrieving {}...'.format(response.url)
    if ('geogallery.si.edu' in url
        and (not hasattr(response, 'from_cache')
             or not response.from_cache)):
        time.sleep(2)
    if response.status_code == 200:
        return callback(response) if callback is not None else response


def get_simpledwr(response):
    data = response.json()
    attributes = data.get('response', {}).get('attributes', {})
    diagnostics = [d['diagnostic'] for d in data.get('response', {}) \
                                                .get('diagnostics', [])]
    if not attributes.get('recordStart'):
        total = attributes.get('totalSearchHits', 0)
        if total == -1:
            print 'More than 1,000 records match this query'
        else:
            print '{:,} records match this query'.format(total)
    try:
        records = data.get('response', {}) \
                      .get('content', {}) \
                      .get('SimpleDarwinRecordSet', [])
    except AttributeError:
        print '\n'.join(['DIAGNOSTIC: ' + d['diagnostic'] for d in diagnostics])
    else:
        # Get the last id
        last_id = [d.split(': ')[-1] for d in diagnostics if d.startswith('Last record:')]
        return Results([rec['SimpleDarwinRecord'] for rec in records], last_id)


def archive(**kwargs):
    # FIXME: Update existing archive file
    defaults = {
        'format': 'xml',
        'schema': 'abcdefg',
        'limit': 1000
    }
    kwargs.update(defaults)
    fn = timestamped('portal.xml')
    count = 0
    with open(fn, 'wb') as f:
        for dept in ['ms', 'pl']:
            kwargs['dept'] = dept
            last_id = 0
            while True:
                response = get(last_id=last_id, **kwargs)
                content = u'{}'.format(response.text)
                try:
                    header, content = content.split('<abcd:Units>', 1)
                except ValueError:
                    break
                else:
                    if not count:
                        f.write(header.encode('utf-8').rstrip())
                    units, footer = content.rsplit('</abcd:Units>', 1)
                    f.write(units.encode('utf-8').rstrip())
                    last_id = re.search('Last record: (\d{7,8})', footer).group(1)
                count += kwargs['limit']
                if not count % 10000:
                    print 'Retrieved {:,} records!'.format(count)
        f.write(footer.encode('utf-8').rstrip())


def download(**kwargs):
    """Saves a set of records as a CSV"""
    defaults = {
        'format': 'json',
        'schema': 'simpledwr',
        'limit': 1000
    }
    kwargs.update(defaults)
    offset = kwargs.pop('offset', 0)
    records = []
    while True:
        new = get(callback=get_simpledwr, offset=offset, **kwargs)
        if new:
            records.extend(new)
            offset += len(new)
        if not new or len(new) < 1000:
            break
    if records:
        keys = []
        for rec in records:
            keys.extend(rec.keys())
        keys = sorted(list(set(keys)))
        fn = timestamped('portal.csv')
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
            if label != 'url':
                arg['action'] = 'append'
            arg['help'] = definition
            args.append(arg)
    return args


def timestamped(base='portal.csv'):
    """Creates a datestamped filename"""
    timestamp = dt.datetime.now().strftime('%Y%m%dt%H%M%S')
    stem, ext = os.path.splitext(base)
    return '{}_{}{}'.format(stem, timestamp, ext)


def encode_for_excel(fp, encoding='utf-8'):
    """Re-encode a document for Excel"""
    with open(fp, 'rb') as f:
        text = f.read().decode(encoding)
    with open(fp, 'wb') as f:
        f.write(codecs.BOM_UTF16_LE)
        f.write(text.encode('utf-16-le'))
