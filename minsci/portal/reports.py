import csv

from .portal import get_all, filename, encode_for_excel


def meteorites():
    names = {}
    records = get_all(collection='meteorites')
    for rec in records:
        name = rec['catalogNumber'].split('|')[0].rsplit(',', 1)[0].strip()
        names.setdefault(name, []).append(rec)
    fn = filename('meteorites')
    with open(fn, 'wb') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'Count'])
        for row in [(name, len(names[name])) for name in sorted(names)]:
            writer.writerow([u'{}'.format(s).encode('utf-8') for s in row])
    encode_for_excel(fn)
    print 'Found {:,} total meteorites ({:,} distinct)'.format(len(records),
                                                               len(names))
    print 'Results saved as {}'.format(fn)
