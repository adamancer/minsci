import os

from lxml import etree

from .helpers import get_circle, get_box


class Kml(object):

    def __init__(self):
        self.nsmap = {None: 'http://www.opengis.net/kml/2.2'}
        self.root = etree.Element('kml', nsmap=self.nsmap)
        self.doc = etree.SubElement(self.root, 'Document')
        self.added = []
        line = {'width': 2}
        poly = None
        self.add_style('candidate', line=line, poly=poly)
        line = {'width': 2, 'color': '501400FF'}
        poly = None
        self.add_style('measured', line=line, poly=poly)
        line = {'width': 2, 'color': '50F00014'}
        poly = None
        self.add_style('final', line=line, poly=poly)


    def add_site(self, site, style, name=None, desc=None):
        self.add_placemark(site, style, name=name, desc=desc)
        try:
            for site in site.directions_from:
                self.add_placemark(site, '#candidate')
        except AttributeError:
            pass
        return self


    def is_new(self, site):
        try:
            radius = site.radius
        except AttributeError:
            radius = site.get_radius()
        try:
            site = site.record
        except AttributeError:
            pass
        point = (site.latitude, site.longitude, radius)
        if not self.added or point not in self.added[1:]:
            self.added.append(point)
            return True
        return False



    def add_style(self, style_id, line=None, poly=None):
        if line or poly:
            style = etree.SubElement(self.doc, 'Style')
            style.attrib['id'] = style_id
            # Apply line styles
            if line is not None:
                line_style = etree.SubElement(style, 'LineStyle')
                for key, val in line.items():
                    etree.SubElement(line_style, key).text = str(val)
            # Apply polygon styles
            if poly is not None:
                poly_style = etree.SubElement(style, 'PolyStyle')
                for key, val in poly.items():
                    etree.SubElement(poly_style, key).text = str(val)
            return style


    def add_placemark(self, site, style, name=None, desc=None):
        if self.is_new(site):
            try:
                radius = site.radius
            except AttributeError:
                radius = site.get_radius()
                site.radius = radius
            if hasattr(site, 'record'):
                site = site.record
                site.radius = radius
            #print(style, radius)
            placemark = etree.SubElement(self.doc, 'Placemark')
            # Add name to placemark
            name_ = etree.SubElement(placemark, 'name')
            name_.text = site.summarize('{name}') if name is None else name
            # Add description to placemark
            description = etree.SubElement(placemark, 'description')
            if desc is None:
                meta = site.simplify(whitelist=['continent',
                                                'country',
                                                'state_province',
                                                'county',
                                                'locality',
                                                'site_source',
                                                'site_num',
                                                'site_kind'])
                if meta.site_kind.startswith('_'):
                    meta.site_kind = None
                html = []
                for attr in ['latitude', 'longitude', 'radius']:
                    mask = '{:.2f}' if attr != 'radius' else '{:.0f}'
                    try:
                        val = mask.format(getattr(site, attr))
                    except ValueError:
                        try:
                            val = mask.format(float(getattr(site, attr)))
                        except ValueError:
                            continue
                    if attr == 'radius':
                        val += ' km'
                    html.append('<strong>{}:</strong> {}'.format(attr.title(),
                                                                 val))
                desc = '<br />'.join(html) + '<br /><br />' + meta.html()
            description.text = desc
            # Add style
            style_url = etree.SubElement(placemark, 'styleUrl')
            style_url.text = '#' + style.lstrip('#')
            # Add multigeometry
            multigeometry = etree.SubElement(placemark, 'MultiGeometry')
            # Add point
            point = etree.SubElement(multigeometry, 'Point')
            coordinates = etree.SubElement(point, 'coordinates')
            coordinates.text = '{},{}'.format(site.longitude, site.latitude)
            # Add radius
            if radius is not None:
                try:
                    self.add_box(multigeometry, site, radius)
                except TypeError:
                    self.add_circle(multigeometry, site, radius)
        return self


    def add_box(self, parent, site, radius):
        # Construct elements
        polygon = etree.SubElement(parent, 'Polygon')
        extrude = etree.SubElement(polygon, 'extrude')
        altitude_mode = etree.SubElement(polygon, 'altitudeMode')
        outer_boundary_is = etree.SubElement(polygon, 'outerBoundaryIs')
        linear_ring = etree.SubElement(outer_boundary_is, 'LinearRing')
        coordinates = etree.SubElement(linear_ring, 'coordinates')
        # Populate elements
        extrude.text = '1'
        altitude_mode.text = 'relativeToGround'
        points = site.polygon(for_plot=True)
        coordinates.text = ' '.join(['{},{}'.format(*pt) for pt in points])
        return self


    def add_circle(self, parent, site, radius):
        # Construct elements
        polygon = etree.SubElement(parent, 'Polygon')
        extrude = etree.SubElement(polygon, 'extrude')
        altitude_mode = etree.SubElement(polygon, 'altitudeMode')
        outer_boundary_is = etree.SubElement(polygon, 'outerBoundaryIs')
        linear_ring = etree.SubElement(outer_boundary_is, 'LinearRing')
        coordinates = etree.SubElement(linear_ring, 'coordinates')
        # Populate elements
        extrude.text = '1'
        altitude_mode.text = 'relativeToGround'
        points = get_circle(site.latitude, site.longitude, radius)
        coordinates.text = ' '.join(['{},{}'.format(*pt[::-1])
                                     for pt in points])
        return self


    def save(self, fp):
        with open(fp, 'wb') as f:
            f.write(etree.tostring(self.root, pretty_print=True))
