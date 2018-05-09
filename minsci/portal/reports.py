import csv

from .portal import get_all, filename, encode_for_excel


def meteorites():
    names = {}
    records = get_all(collection='meteorites')
    for rec in records:
        name = rec['catalogNumber'].split('|')[0].rsplit(',', 1)[0].strip()
        names.setdefault(name, []).append(rec.get('higherGeography', ''))
    fn = filename('meteorites')
    antarctics = {}
    with open(fn, 'wb') as f:
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
    print 'Found {:,} total meteorites ({:,} distinct)'.format(len(records),
                                                               len(names))
    # Report total Antarctic meteorites found
    num_antarctics = sum(antarctics.values())
    print 'Found {:,} Antarctic meteorites ({:,} distinct)'.format(num_antarctics,
                                                                   len(antarctics))
    print 'Results saved as {}'.format(fn)
