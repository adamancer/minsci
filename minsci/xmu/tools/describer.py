"""Tools to describe and link multimedia using data from ecatalogue"""
import re
from collections import namedtuple
from copy import deepcopy

from ...helpers import (add_article, lcfirst, oxford_comma,
                        plural, singular, ucfirst)


# Objects that are sometimes found in the cut field and represent a whole
# object, not a setting. Entries in this list are processed in the order they
# appear.
OBJECTS = [
    'box',
    'bead',
    'bowl',
    'bottle',
    'cup',
    'pendant',
    'sphere',
    'urn',
    'vase',
    'carving'
]
INFLECTED = [(singular(_), plural(_)) for _ in OBJECTS]

# Terms that need hyphens to be properly formatted as adjectives
PAIRS = [
    ['  ', ' '],
    [',-', ', '],
    [' med ', ' medium '],
    ['-med-', '-medium-'],
    [' shaped', '-shaped'],
    ['off white', 'off-white'],
    ['play of color', 'play-of-color'],
    ['light medium', 'light-to-medium'],
    ['light to medium', 'light-to-medium'],
    ['light dark', 'light-to-dark'],
    ['light to dark', 'light-to-dark'],
    ['medium light', 'medium-to-light'],
    ['medium to light', 'medium-to-light'],
    ['medium dark', 'medium-to-dark'],
    ['medium to dark', 'medium-to-dark'],
    ['dark light', 'dark-to-light'],
    ['dark to light', 'dark-to-light'],
    ['medium light', 'medium-to-light'],
    ['medium to light', 'medium-to-light']
]

ALWAYS_PLURAL = [
    'bead'
]

Description = namedtuple('Description', ['object', 'caption',
                                         'keywords', 'summary'])


def summarize(rec):
    """Summarizes basic information about an object"""
    rec.module = 'ecatalogue'  # force module to ecatalogue
    descriptors = get_descriptors(rec)
    caption = get_caption(descriptors=descriptors)
    keywords = get_keywords(descriptors=descriptors)
    tags = get_tags(descriptors=descriptors)
    # Write summary line used to make a quick id of sample (for example, when
    # matching media to samples)
    catnum = descriptors['catnum']
    summary = u'{}: {} [{}]'.format(catnum, caption, tags).rstrip('[] ')
    # Cull unneeded keys from descriptors
    keep = ['irn', 'catnum', 'status', 'xname', 'url']
    obj = {key: val for key, val in descriptors.items() if key in keep}
    obj['xname'] = ucfirst(obj['xname'])
    return Description(object=obj, caption=caption,
                       keywords=keywords, summary=summary)


def get_descriptors(rec):
    """Parses basic descriptive information about a record into a dict"""
    name = rec('MinName') if rec('MinName') else rec('MetMeteoriteName')
    catnum = rec.get_identifier(include_div=True, force_catnum=True)
    if catnum.split('(')[0].strip() == 'USNM':
        catnum = name + ' (MET)'
    taxa = rec.get_classification()
    try:
        xname = rec.get_name(taxa=taxa)
    except KeyError:
        xname = name
    taxa_string = lcfirst(rec.get_classification_string(taxa))
    kind = rec('CatCatalog').split(' ')[0].rstrip('s')
    cut, setting = format_gems(rec)
    country, state, county = rec.get_political_geography()
    description = rec('BioLiveSpecimen').lower().rstrip('.').replace('"', "'")
    if description == name.lower():
        description = ''
    weight = rec.get_current_weight() if kind == 'Meteorite' else ''
    descriptors = {
        'irn': rec('irn'),
        'catnum': catnum,
        'name': name,
        'xname': xname,
        'taxa': taxa,
        'tname': taxa_string,
        'kind': kind,
        'cut': cut,
        'setting': setting,
        'colors': format_colors(rec),
        'locality': format_locality(country, state, county),
        'country': country,
        'state': state,
        'weight': weight,
        'description': description,
        'status': rec('SecRecordStatus').lower(),
        'url': rec.get_url()
    }
    if descriptors['kind'] != 'Meteorite':
        descriptors['xname'] = lcfirst(descriptors['xname'])
    return descriptors


def get_caption(rec=None, descriptors=None):
    """Derives a simple descripton of an object"""
    if descriptors is None:
        descriptors = get_descriptors(rec)
    lines = [format_caption(descriptors)]
    # Mark inactive records
    if descriptors['status'] and descriptors['status'] != 'active':
        status = descriptors['status']
        if status == 'inactive':
            status = 'made inactive'
        lines.append('The catalog record associated with this'
                     ' specimen has been {}.'.format(status))
    caption = '. '.join([s.rstrip('. ') for s in lines])
    if not caption.endswith(('.', '"')):
        caption += '.'
    return caption


def get_keywords(rec=None, descriptors=None):
    """Sets multimedia keywords for the given object"""
    if descriptors is None:
        descriptors = get_descriptors(rec)
    keywords = []
    for key in ['kind', 'setting']:
        keywords.append(descriptors[key])
    keywords.extend(descriptors['taxa'])
    keywords.append(descriptors['country'])
    if descriptors['country'].lower() == 'united states':
        keywords.append(descriptors['state'])
    keywords = [kw for i, kw in enumerate(keywords) if not kw in keywords[:i]]
    return [ucfirst(s) for s in keywords if s and not 'unknow' in s.lower()]


def get_tags(rec=None, descriptors=None):
    """Sets tags with special information useful in identifying objects"""
    if descriptors is None:
        descriptors = get_descriptors(rec)
    tags = []
    #if obj.collections and 'polished thin' in obj.collections[0].lower():
    #    tags.append('PTS')
    #if 'GGM' in obj.location.upper():
    #    tags.append('GGM')
    #elif 'POD 4' in obj.location.upper():
    #    tags.append('POD 4')
    return tags


def clean_caption(caption):
    """Cleans vestigial phrases from caption"""
    while '  ' in caption:
        caption = caption.replace('  ', ' ')
    return ucfirst(caption.strip('., ') \
                          .replace('from weighing', 'weighing') \
                          .replace('colored from', 'from') \
                          .replace('weighing .', '.') \
                          .replace('Described as "."', '') \
                          .replace('carved,', 'carved') \
                          .replace(' , ', ' ') \
                          .replace(' . ', '. ') \
                          .replace('..', '.') \
                          .replace(',-', ', '))


def format_caption(descriptors):
    """Formats caption based on the information in descriptors"""
    working = deepcopy(descriptors)
    # Make global changes to descriptors
    if working['catnum'].endswith('(MET)'):
        working['description'] = ''
        xname = re.split('[ -]', working['xname'], 1)[0]
        if xname.isalpha() and not xname == xname.upper():
            working['xname'] = lcfirst(working['xname'])
    # Select a mask and format the data for it
    if (working['cut']
            and not working['cut'] in ('carved', 'intarsia')
            and not 'beads' in working['cut']):
        working['cut'] = format_modifier(working['cut']) + '-cut'
    if (working['setting'].lower() in working['xname'].lower()
        and working['tname'].lower() in working['xname'].lower()
        and not (working['locality'] or working['cut'] or working['colors'])):
        mask = u''
    elif working['setting'].lower() in OBJECTS:
        working['colors'] = format_modifier(oxford_comma(working['colors']))
        mask = u'{cut}, {colors} {tname} {setting}'
    elif working['setting'] and 'beads' in working['cut']:
        working['setting'] = add_article(working['setting'])
        working['colors'] = format_modifier(oxford_comma(working['colors']))
        mask = u'{setting} featuring {colors} {tname} {cut}'
    elif (working['setting']
          and working['locality']
          and not (working['cut'] or working['colors'])):
        working['xname'] = add_article(working['xname'])
        mask = u'{setting} featuring {tname} from {locality}'
    elif working['setting']:
        working['setting'] = add_article(working['setting'])
        working['colors'] = format_modifier(oxford_comma(working['colors']))
        mask = u'{setting} featuring {cut}, {colors} {tname}'
    elif working['cut'] and len(working['colors']) <= 2:
        working['colors'] = format_modifier(oxford_comma(working['colors']))
        mask = u'{cut}, {colors} {tname} from {locality}'
    elif working['cut']:
        working['colors'] = oxford_comma(working['colors'])
        mask = u'{cut} {tname} colored {colors} from {locality}'
    elif working['name'] and not working['locality']:
        mask = u''
    else:
        mask = u'{xname} from {locality}'
    # Add common elements
    prefix = u'{name}.'
    suffix = u'weighing {weight}. Described as "{description}."'
    mask = u' '.join([s for s in [prefix, mask, suffix] if s])
    caption = clean_caption(mask.format(**working))
    # Fix capitalization of second sentence when name is specified
    if working['name']:
        sentences = caption.split('. ', 1)
        if not sentences[1].startswith('Described'):
            sentences[1] = ucfirst(add_article(sentences[1]))
            caption = '. '.join(sentences)
    return caption


def format_colors(rec):
    """Formats colors"""
    colors = rec('MinColor_tab')
    if colors and not ',' in colors[0] and not is_multiple(rec('MinCut')):
        colors = colors[0].lower().replace(' ', '-')
        return [re.sub('\bmed\b', 'medium', s.strip('- '), flags=re.I)
                for s in colors.split(',') if s != 'various']
    return []


def format_locality(country, state, county):
    """Formats locality info as a comma-delimited string"""
    if 'Unknown' in country or 'Synthetic' in country:
        return ''
    if country == 'United States':
        return ', '.join([s for s in [county, state] if s])
    locality = ', '.join([s for s in [county, state, country] if s])
    if 'Ca.' in locality:
        locality = 'near ' + locality.replace(' Ca.', '')
    return locality


def format_gems(rec):
    """Formats setting and cut of jewellery"""
    setting = rec('MinJeweleryType').lower()
    cut = rec('MinCut').lower()
    if is_multiple(cut):
        cut = ''
    if setting or cut:
        # Derive object type from cut if not setting is given
        if not setting:
            for term in INFLECTED:
                for inflection in term:
                    if inflection in cut:
                        setting = inflection
                        if setting in cut:
                            cut = u''
                        break
        if cut == 'intarsia':
            setting = u'{} {}'.format(cut, setting)
            cut = u''
        # Standardize the formatting of cut
        if cut in ALWAYS_PLURAL:
            cut = plural(cut)
        if cut in ['various']:
            cut = ''
        while cut[-4:] in (' cut', '-cut'):
            cut = cut[:-4]
        if setting == 'carving' and not cut:
            cut = u'carved'
            setting = u''
        # Format setting
        if setting in ALWAYS_PLURAL:
            setting = plural(setting)
        if setting in cut:
            setting = u''
        setting = setting.lower().rstrip('. ')
    return cut, setting


def format_modifier(modifier):
    """Formats a string as a compound modifier"""
    words = [s.strip('. ') for s in re.split(r'[\s\-]+', modifier.strip())]
    formatted = [s + ' ' if is_adverb(s) and not i else s + '-'
                 for i, s in enumerate(words)]
    return ''.join(formatted).rstrip('-')


def is_adverb(word):
    """Simplistically checks if a word is an adverb"""
    word = word.lower()
    return word == 'very' or word.endswith('ly')


def is_multiple(phrase):
    """Simplistically checks if a phrase contains multiple items"""
    return ',' in phrase or ' and ' in phrase