import pprint as pp
import re
from copy import deepcopy


CATKEYS = (
    'FullNumber',
    'MetPrefix',
    'CatMuseumAcronym',
    'CatPrefix',
    'CatNumber',
    'CatSuffix'
    )
MINCATNUM = 1000


class CatNum(object):
    _attributes = [
        'code',
        'prefix',
        'number',
        'suffix',
        'division'
    ]

    def __init__(self, *args, **kwargs):
        self.verbatim = None
        if args and isinstance(args[0], basestring):
            self.verbatim = args[0]
            self.parse(args[0], **kwargs)
        elif 'CatNumber' in kwargs or 'MetMeteoriteName' in kwargs:
            for key in ['FullNumber', 'MetPrefix']:
                try:
                    del kwargs[key]
                except KeyError:
                    pass
            self.code = kwargs.pop('CatMuseumAcronym', None)
            self.prefix = kwargs.pop('CatPrefix', None)
            self.number = kwargs.pop('CatNumber', None)
            self.suffix = kwargs.pop('CatSuffix', None)
            self.division = kwargs.pop('CatDivision', None)
            self.delim = '-'
            self.metname = kwargs.pop('MetMeteoriteName', None)
        elif 'number' in kwargs or 'metname' in kwargs:
            self.code = kwargs.pop('code', None)
            self.prefix = kwargs.pop('prefix', None)
            self.number = kwargs.pop('number', None)
            self.suffix = kwargs.pop('suffix', None)
            self.delim = kwargs.pop('delim', '-')
            self.division = kwargs.pop('division', None)
            self.metname = kwargs.pop('metname', None)
        else:
            raise ValueError('Cannot parse arguments: {}'.format(args))
        # Raise an error if there are the kwargs dict still has values in it
        if kwargs:
            raise KeyError('Leftover kwargs: %s' % kwargs)
        # Enforce formatting for some fields
        if self.prefix:
            self.prefix = self.prefix.upper()
        if self.suffix:
            self.suffix = self.suffix.strip(self.delim)
        self._params = {
            'code': self.code,
            'prefix': self.prefix,
            'number': self.number,
            'suffix': self.suffix,
            'delim': self.delim,
            'div': self.division[:3].upper() if self.division else None,
            'metname': self.metname
        }
        self._masks = {
            'default': u'{prefix}{number}{delim}{suffix}',
            'include_code': u'{code} {prefix}{number}{delim}{suffix}',
            'include_div': u'{code} {prefix}{number}{delim}{suffix} ({div})',
        }
        self._mask = self._masks['default']


    def __eq__(self, other):
        return (self.code == other.code
                and self.prefix == other.prefix
                and self.number == other.number
                and self.suffix == other.suffix
                and self.delim == other.delim
                and self.division == other.division)


    def __repr__(self):
        keyvals = ['{}={}'.format(attr, getattr(self, attr))
                   for attr in self._attributes if getattr(self, attr)]
        return 'CatNum({})'.format(', '.join(keyvals))


    def __str__(self):
        if self.metname:
            return self.metname
        return self.from_mask(self._mask)


    def set_mask(self, key):
        try:
            self._mask = self._masks[key]
        except KeyError:
            self._mask = key
        return self


    def parse(self, val, *args, **kwargs):
        result = _parse_catnum(val, *args, **kwargs)
        if len(result) != 1:
            raise ValueError('Could not parse catalog number from %s' % val)
        self.code = result[0].get('CatMuseumAcronym')
        self.prefix = result[0].get('CatPrefix')
        self.number = result[0].get('CatNumber')
        self.suffix = result[0].get('CatSuffix')
        self.delim = result[0].get('CatDelimiter', '-')
        self.division = result[0].get('CatDivision')
        self.metname = result[0].get('MetMeteoriteName')
        return self


    def for_emu(self):
        return {
            'CatMuseumAcronym': self.code,
            'CatPrefix': self.prefix,
            'CatNumber': self.number,
            'CatSuffix': self.suffix,
            'CatDivision': self.division,
            'MetMeteoriteName': self.metname
            }


    def for_filename(self, sortable=True, lower=False):
        number = self._to_num_string(sortable)
        catnum = self.metname if self.metname else self.from_mask(number=number)
        return catnum.lower() if lower else catnum


    def sortable(self):
        prefix = self.prefix.zfill(16)
        number = self._to_num_string().zfill(16)
        suffix = self.suffix.zfill(16)
        return self.from_mask(self._masks['default'],
                              prefix=prefix,
                              number=number,
                              suffix=suffix,
                              delim=None)


    def from_mask(self, mask=None, **params):
        if mask is None:
            mask = self._mask
        # Pad prefix with a space if more than one character
        if len(self.prefix) > 1:
            params['prefix'] = self.prefix + ' '
        defaults = {k: v for k, v in self._params.iteritems()}
        defaults.update(params)
        params = {k: v if v else '' for k, v in defaults.iteritems()}
        return mask.format(**params).strip(' -,()')


    def _to_num_string(self, sortable=False):
        if sortable:
            if len(self.prefix) == 1:
                return str(self.number).zfill(5)
            else:
                return str(self.number).zfill(6)
        return str(self.number)




class CatNumList(list):

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            catnums = args[0]
        elif len(args) > 1:
            catnums = args
        else:
            catnums = []
        self.extend([self._coerce(c) for c in catnums])


    def __str__(self):
        vals = ['-'.join([str(v) for v in c]) for c in self.cluster()]
        if len(vals) == 2:
            return ' and '.join(vals)
        elif len(vals) > 1:
            vals[-1] = 'and ' + vals[-1]
        return ', '.join(vals)


    def __repr__(self):
        return pp.pformat([repr(c) for c in self])


    @staticmethod
    def _coerce(val):
        if isinstance(val, basestring):
            return CatNum(val)
        elif isinstance(val, dict):
            return CatNum(**val)
        else:
            return val


    def append(self, catnum):
        super(CatNumList, self).append(self._coerce(catnum))


    def extend(self, catnums):
        super(CatNumList, self).extend([self._coerce(c) for c in catnums])


    def for_emu(self):
        return [catnum.for_emu() for catnum in self]


    def for_filename(self, clustered=True, sortable=True, lower=False, n_max=None):
        if clustered:
            vals = ['-'.join([str(v) for v in c]) for c in self.cluster()]
        else:
            vals = [catnum.for_filename(sortable, lower) for catnum in vals]
        # Limit to the first n values
        if n_max and len(vals) > n_max:
            vals = vals[:n_max] + ['and others']
        filename = '_'.join(vals)
        if lower:
            filename = filename.lower()
        return filename.replace(' ', '_')


    def unique(self):
        return CatNumList([v for i, v in enumerate(self) if not v in self[:i]])


    def cluster(self):
        catnums = self.unique()
        catnums.sort()
        prefixed = {}
        for catnum in catnums:
            prefixed.setdefault(catnum.prefix, CatNumList()).append(catnum)
        clusters = []
        for prefix in sorted(prefixed):
            catnums = prefixed[prefix]
            cluster = []
            for catnum in catnums:
                # Suffixes make this very complicated, so ignore for now
                if catnum.suffix:
                    if cluster:
                        clusters.append([cluster[0], cluster[-1]])
                        cluster = []
                    clusters.append([catnum])
                elif cluster and catnum.number - cluster[-1].number > 1:
                    clusters.append([cluster[0], cluster[-1]])
                    cluster = [catnum]
                else:
                    cluster.append(catnum)
            if cluster:
                clusters.append([cluster[0], cluster[-1]])
        return [c if c[0] != c[-1] else [c[0]] for c in clusters]


    def one(self):
        if len(self) == 1:
            return self[0]
        raise IndexError('List does not have exactly one member')


    def sort(self):
        super(CatNumList, self).sort(key=lambda catnum: catnum.sortable())



def get_catnum(*args, **kwargs):
    catnums = _parse_catnum(*args, **kwargs)
    if any(catnums) and len(catnums) == 1:
        return CatNum(**catnums[0])
    return CatNumList(catnums)


def get_catnums(*args, **kwargs):
    return CatNumList(_parse_catnum(*args, **kwargs))


def _parse_catnum(val, attrs=None, default_suffix='', min_suffix_length=0,
                 strip_suffix=False, prefixed_only=False):
    """Find and parse catalog numbers in a string

    Args:
        s (str): string containing catalog numbers or range
        attrs (dict): additional parameters keyed to EMu field
        default_suffix (str): default suffix to add if none present
        strip_suffx (bool): strip leading zeroes from suffix if True
        prefixed_only (bool): find only those catalog numbers that are
            prefixed by a valid museum code (NMNH or USNM)

    Returns:
        List of dicts containing catalog numbers parsed into prefix, number,
        and suffix: {'CatPrefix': 'G', 'CatNumber': '3551', 'CatSuffix': 00}.
        Pass to format_catnums to convert to strings.
    """
    if attrs is None:
        attrs = {}
    # Cull text we don't want
    val = re.sub(r'(No\. |#|specimens? )', '', val, flags=re.I).replace('  ', ' ')
    # Catch code using the old syntax
    if not isinstance(default_suffix, basestring):
        raise Exception('Default suffix must be a string')
    # Regular expressions for use with catalog number functions
    #p_pre = ur'(?:([A-Z]{3}[A ] ?)|(?:(NMNH[ \-]|USNM[ \-])?(?:([BCGMRS])-?)?))?'
    p_pre = ur'(?:([A-Z]{3}[A ] ?)|(?:(NMNH[ \-]+|USNM[ \-]+)?(?:([A-Z]{1,3})[ \-]?)?))?'
    p_num = ur'([0-9]{1,6})'  # this will pick up ANY number
    if MINCATNUM == 1:
        p_suf = ur'\s?([-\.][A-z0-9\.\- ]+|[-/\.][0-9]{1,4}|[-/\.][A-Z][0-9]{1,2}|[c,]\s?[0-9]{1,2}[A-Z]?|\.[0-9]+|\s?(?:-|thr(?:ough|u))\s?[BCGMRS][0-9]{1,5})?'
    else:
        p_suf = ur'\s?([-/\.][0-9]{1,4}|[-/\.][A-Z][0-9]{1,2}|[c,]\s?[0-9]{1,2}[A-Z]?|\.[0-9]+|\s?(?:-|thr(?:ough|u))\s?[BCGMRS][0-9]{1,5})?'
    regex = re.compile(ur'\b(' + p_pre + p_num + p_suf + ur')\b', re.I)
    all_id_nums = []
    for substring in re.split(ur'\s(and|&)\s', val, flags=re.I):
        id_nums = _parse_matches(regex.findall(substring), prefixed_only)
        id_nums = _fix_misidentified_suffixes(id_nums)
        id_nums = _fill_range(id_nums, substring)
        id_nums = _clean_suffixes(id_nums, attrs, default_suffix,
                                  min_suffix_length, strip_suffix)
        # Require unprefixed numeric catalog numbers integers to meet a
        # minimum length. This reduces false positives at the expense of
        # excluding records with low catalog numbers.
        id_nums = [id_num for id_num in id_nums
                   if id_num.get('CatPrefix')
                   or id_num.get('CatMuseumAcronym')
                   or id_num.get('CatNumber', 0) >= MINCATNUM
                   or id_num.get('MetMeteoriteName')]
        # Format results as tuple
        all_id_nums.extend(id_nums)
    # Return parsed catalog numbers
    return all_id_nums




def _parse_catnums(vals, **kwargs):
    """Parse a list of strings containing catalog numbers

    See _parse_catnum() for a description of the available arguments.

    Returns:
        A list of parsed catnums
    """
    # Return list of parsed catalog numbers
    catnums = []
    for val in vals:
        catnums.extend(_parse_catnum(val, **kwargs))
    return catnums




def format_catnum(parsed, code=True, div=False):
    """Formats parsed catalog number to a string

    Args:
        parsed (dict): parsed catalog number
        code (bool): include museum code in catnum if True
        div (bool): include div abbreviation in catnum if True

    Returns:
        Catalog number formatted as a string, like 'G3551-00'. Use
        format_catnums to process a list of parsed catalog numbers.
    """
    try:
        return parsed['MetMeteoriteName']
    except KeyError:
        pass
    try:
        parsed['CatNumber']
    except KeyError:
        return ''
    keys = ('CatMuseumAcronym', 'CatDivision', 'CatPrefix', 'CatSuffix')
    for key in keys:
        parsed.setdefault(key, '')
        parsed[key] = parsed[key].strip()
    # Set museum code
    if code:
        parsed.setdefault('CatMuseumAcronym', 'NMNH')
        if parsed['CatDivision'] == 'Meteorites':
            parsed['CatMuseumAcronym'] = 'USNM'
    if not parsed['CatPrefix']:
        parsed['CatPrefix'] = u''
    parsed['CatPrefix'] = parsed['CatPrefix'].upper()
    # Format catalog number
    catnum = (
        u'{CatMuseumAcronym} {CatPrefix}{CatNumber}-{CatSuffix}'
        .format(**parsed)
        .rstrip('-')
        .strip()
        )
    # Add division if necessary
    if bool(catnum) and div:
        catnum += u' ({})'.format(parsed['CatDivision'][:3].upper())
        #catnum = u'{} {}'.format(d['CatDivision'][:3].upper(), catnum)
    return catnum




def format_catnums(parsed, code=True, div=False):
    """Converts a list of parsed catalog numbers into strings

    Args:
        parsed (list): list of dicts containing parsed catnums
        code (bool): include museum code in catnum if True
        div (bool): include div abbreviation in catnum if True

    Returns:
        List of catalog numbers formatted as strings: ['G3551-00']
    """
    if not isinstance(parsed, list):
        parsed = [parsed]
    catnums = []
    for catnum in parsed:
        catnums.append(format_catnum(catnum, code, div))
    return catnums


def sort_catnums(catnums):
    """Sort a list of catalog numbers

    Args:
        catnums (list): list of catalog numbers, either as strings or parsed
            into dicts

    Return:
        Sorted list of catalog numebrs. Catalog numbers are formatted in
        the same way as they were in the original list.
    """
    try:
        catnums = _parse_catnums(catnums)
    except IndexError:
        # Catalog numbers were given as dicts, so return them that way
        return sorted(catnums, key=catnum_keyer)
    else:
        # Catalog numbers are strings, so format them before returning them
        return format_catnums(sorted(catnums, key=catnum_keyer))


def catnum_keyer(catnum):
    """Create sortable key for a catalog number by zero-padding each component

    Args:
        catnum (str or dict): the catalog number to key

    Returns:
        Sortable catalog number
    """
    if isinstance(catnum, basestring):
        try:
            catnum = _parse_catnum(catnum)[0]
        except IndexError:
            print('Sort error: ' + catnum)
            raise
            return 'Z' * 63
    keys = ('CatPrefix', 'CatNumber', 'CatSuffix')
    return '|'.join([str(catnum.get(key, '')).zfill(20) for key in keys])


def _parse_matches(matches, prefixed_only=False):
    """Format catalog numbers from a parsed list"""
    id_nums = []
    for match in matches:
        id_num = dict(zip(CATKEYS, [val.rstrip('-, ') for val in match]))
        # FIXME
        if id_num['MetPrefix'] in ['PAL']:
            id_num['CatNumber'] = id_num['CatNumber'].split(id_num['MetPrefix'])[-1].strip()
            id_num['CatPrefix'] = id_num['MetPrefix']
            id_num['MetPrefix'] = None
        # Handle meteorites
        if id_num['MetPrefix']:
            metname = id_num['FullNumber'].replace(', ', ',')
            return [{'MetMeteoriteName': metname}]
        # Handle catalog numbers from other departments
        else:
            # Exclude catalog numbers without a prefix
            if prefixed_only and not id_num['CatMuseumAcronym']:
                continue
            id_num['CatNumber'] = int(id_num['CatNumber'])
            # Handle petrology suffix format (.0001)
            if id_num['CatSuffix'].startswith('.'):
                id_num['CatSuffix'] = id_num['CatSuffix'].lstrip('.0')
            else:
                id_num['CatSuffix'] = id_num['CatSuffix'].strip('-,.')
        id_nums.append(id_num)
    return id_nums


def _fill_range(id_nums, substring):
    """Checks if a pair of catalog numbers appears to be a range"""
    try:
        first_num, last_num = id_nums
    except ValueError:
        pass
    else:
        is_range = (
            ((substring.count('-') > 0 and substring.count('-') != 2)
             or substring.count('through') == 1
             or substring.count('thru') == 1)
            and first_num['CatPrefix'] == last_num['CatPrefix']
            and last_num['CatNumber'] > first_num['CatNumber']
            and not first_num['CatSuffix'] and not last_num['CatSuffix']
            and first_num['CatNumber'] > 10
            )
        # Fill range
        if is_range:
            id_nums = []
            for i in xrange(first_num['CatNumber'], last_num['CatNumber'] + 1):
                id_num = deepcopy(first_num)
                id_num['CatNumber'] = i
                id_num['FullNumber'] = format_catnum(id_num)
                id_nums.append(id_num)
    return id_nums


def _clean_suffixes(id_nums, attrs, default_suffix,
                    min_suffix_length, strip_suffix):
    """Clean the identification numbers based on passed arguments"""
    for i, id_num in enumerate(id_nums):
        # HACK
        if not id_num.get('CatSuffix'):
            continue
        # Clean suffixes
        id_num['CatSuffix'] = id_num['CatSuffix'].strip('/')
        if min_suffix_length:
            suffix = id_num['CatSuffix']
            id_nums[i]['CatSuffix'] = suffix.zfill(min_suffix_length)
        if strip_suffix:
            id_nums[i]['CatSuffix'] = u''
        elif not id_num['CatSuffix']:
            id_nums[i]['CatSuffix'] = default_suffix
        # Add additional attributes passed to the function
        id_nums[i].update(attrs)
        # Remove keys that do not correspond to EMu fields
        for key in ('FullNumber', 'MetPrefix'):
            try:
                del id_nums[i][key]
            except KeyError:
                pass
    return id_nums


def _fix_misidentified_suffixes(id_nums):
    """Check for ranges that have been misidentified as suffixes"""
    if len(id_nums) == 1:
        id_num = id_nums[0]
        try:
            suffix = int(id_num['CatSuffix'])
        except KeyError:
            pass
        except ValueError:
            # Check for where suffix is itself a prefixed catalog number.
            # The delta used to assessed ranges is set to 9 because there
            # are at least ten catalog numbers per page in MinSci's ledgers
            last_num = _parse_catnum(id_num['CatSuffix'])
            if (len(last_num) == 1
                    and (last_num[0]['CatNumber'] - id_num['CatNumber'] >= 9)
                    and (not last_num[0]['CatPrefix']
                         or last_num[0]['CatPrefix'] == id_num['CatPrefix'])):
                id_num['CatSuffix'] = ''
                id_nums = [id_num, last_num[0]]
        else:
            if (suffix - int(id_num['CatNumber'])) >= 9:
                first_num = id_num
                first_num['CatSuffix'] = u''
                last_num = {key: '' for key in CATKEYS}
                last_num['CatNumber'] = suffix
                for key in ('CatPrefix', 'CatMuseumAcronym'):
                    last_num[key] = first_num[key]
                id_nums = [first_num, last_num]
    return id_nums
