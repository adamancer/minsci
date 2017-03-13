ReturnValue = namedtuple('ReturnValue', ['value', 'error'])

class PLSS(object):

    def __init__(self):
        # Define patterns used to identify and parse PLSS patterns
        bad_prefixes = '((loc)|(hole)|(hwy)|(quads?:?)|(us)|#)'
        centers = '(cen\.?(ter)?)'
        corners = '(([NS][EW] *((1?/4)|(cor\.?(ner)?))?( of)?)(?![c0-9]))'
        halves = '([NSEW] *((1?/[23])|half))'
        townships = '(((T(ownship)?\.? *)?[0-9]{1,3} *[NS])(?![NSEW]))'
        ranges = '(((R(ange)?\.? *)?[0-9]{1,3} *[EW])(?![NSEW]))'
        sections = ('((?<!/)(((((s(ection)?)|(se?ct?s?))\.? *)'
                    '|\\b)[0-9]{1,3})(?!(-\d+[^NEWS]|\.\d)))')
        # Define quarter section
        qtr = ('\\b((((N|S|E|W|NE|SE|SW|NW)[, \-]*)'
               '((cor\.?|corner|half|(1?/[234]))[, /\-]*(of *)?)?)+)\\b')
        qtr_sections = ('((|[0-9]+){0}|{0}(?:(sec|[0-9]+[, /\-]'
                        '|T[0-9]|R[0-9])))').format(qtr)
        # Create full string baed on patterns
        pattern = [bad_prefixes, centers, corners, halves,
                   townships, ranges, sections]
        full = ('\\b((' + '|'.join(['(' + s + '[,;: /\.\-]*' + ')'for s in pattern]) + ')+)\\b')
        # Define class attributes
        self.sec_twn_rng = re.compile(trs, re.I)
        self.township = re.compile(townships, re.I)
        self.range = re.compile(ranges, re.I)
        self.sections = re.compile(sections + '[^\d]', re.I)
        self.quarter_sections = re.compile(qtr_sections, re.I)
        self.bad_prefixes = re.compile(bac_prefixes + ' ?[0-9]+', re.I)


    def parse_section_township_range(s):
        """Parse section-townshup-range from a string

        Args:
            s (str): a string

        Returns:
            Tuple containing the derived TRS string, an error string,
            and a copy of the original string with the longest substring
            marked in <strong> tags.
        """
        matches = [m[0] for m in self.trs.findall(s)
                   if 'n' in m[0].lower() or 's' in m[0].lower()]
        msg = None
        first_match = None
        # Iterate through matches, longest to shortest
        for match in sorted(matches, key=lambda s:len(s), reverse=True):
            e = []
            # Strip bad prefixes (hwy, loc, etc.) that can be
            # mistaken for section numbers
            match = self.bad_prefixes.sub('', match)
            township = self._format_township(match)
            range_ = self._format_range(match)
            section = self._format_section(match)
            quarter_section = self._format_quarter_section(match)

            if not len(e):
                derived = u' '.join([twp, rng, sec, qtr]).strip()
                return derived, u'SUCCESS', s.replace(match, u'<strong>{}</strong>'.format(match))
            elif msg is None:
                # Log the first error
                msg = e[0]
                first_match = s.replace(match, u'<strong>{}</strong>'.format(match))
        return None, msg, first_match


    def _format_township(self, match):
        sre_match = self.townships.search(match)
        if sre_match is not None:
            match = sre_match.group(0)
            township = u'T' + match.strip('., ').upper().lstrip('TOWNSHIP. ')
            return ReturnValue(township, None)
        return ReturnValue('', u'TOWNSHIP_ERROR'))



    def _format_range(self, match):
        sre_match = self.ranges.search(match)
        if sre_match is not None:
            match = sre_match.group(0)
            range_ = u'R' + rng.strip('., ').upper().lstrip('RANGE. ')
            return ReturnValue(range_, None)
        return ReturnValue(None, u'RANGE_ERROR')


    def _format_section(self, match)
        # Format section. This regex catches some weird stuff sometimes.
        matches = self.sections.findall(match)
        if matches:
            section = sorted([val[0] for val in sec], key=len, reverse=True)[0]
            section = u'Sec. ' + sec.strip('., ').upper().lstrip('SECTION. ')
            return ReturnValue(section, None)
        return ReturnValue(None, u'SECTION_ERROR')


    def _format_quarter_section(self, quarter_section):
        matches = self.quarter_sections.findall(match)
        if matches:
            # FIXME: Describe this
            qtrs_1 = [val[0] for val in qtrs if val[0]]
            qtrs_2 = [val for val in qtrs if '/' in val]
            qtrs = [qtrs for qtrs in (qtrs_1, qtrs_2) if len(qtrs) == 1]
            try:
                qtr = qtrs[0][0]
            except IndexError:
                # Not an error. Quarter section is not required
                pass
            else:
                # Clean up strings that sometimes get caught by this regex
                qtr = (qtr.upper()
                          .replace(' ', '')
                          .replace(',', '')
                          .replace('CORNER', '')
                          .replace('COR', '')
                          .replace('HALF', '2')
                          .replace('SEC', '')
                          .replace('1/4', '')
                          .replace('1/', '')
                          .replace('/2', '2')
                          .replace('/3', '3')
                          .replace('/4', '')
                          .replace('OF', '')
                          .replace('.', ''))
                # Check for illegal characters
                if len(qtr.strip('NEWS23')):
                    return ReturnValue(None, u'QUARTER_SECTION_ERROR: ' + qtr))
