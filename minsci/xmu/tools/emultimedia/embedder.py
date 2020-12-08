"""Tools to embed metadata in image files"""
import os
import shutil
import subprocess
import tempfile
from collections import namedtuple
from datetime import datetime

from nmnh_ms_tools.utils import localize_datetime
from unidecode import unidecode

from .hasher import hash_image_data




EmbedField = namedtuple('EmbedField', ['name', 'length', 'function'])


class Embedder:
    """Tools to embed metadata in image files"""

    def __init__(self, output_dir, overwrite=True, in_place=False,
                 verify_images=True):
        self.metadata_fields = {
            'imageuniqueid': EmbedField('xmp:imageuniqueid',
                                        64, self.get_url),
            'copyright': EmbedField(['mwg:copyright', 'iptc:copyrightnotice'],
                                     128, self.get_copyright),
            'creator': EmbedField('mwg:creator', 64, self.get_creator),
            'datetime_created': EmbedField('mwg:createdate', 64, self.get_datetime_created),
            'caption': EmbedField('mwg:description', 2000, self.get_caption),
            'credit_line': EmbedField(['iptc:credit', 'xmp:credit'], 64, self.get_credit_line),
            'date_created': EmbedField(['iptc:datecreated',
                                        'xmp:datecreated'], 8, self.get_date_created),
            'headline': EmbedField(['iptc:headline',
                                    'xmp:headline'], 64, self.get_headline),
            'job_id': EmbedField(['iptc:originaltransmissionreference',
                                  'iptc:jobid',
                                  'xmp:transmissionreference'],
                                 32, self.get_job_id),
            'keywords': EmbedField('mwg:keywords', 64, self.get_keywords),
            'object_name': EmbedField(['iptc:objectname', 'title'], 64, self.get_object_name),
            'source': EmbedField(['iptc:source', 'xmp:source'], 64, self.get_source),
            'special_instructions': EmbedField(['iptc:specialinstructions',
                                                'xmp:instructions'], 256,
                                               self.get_special_instructions),
            'subject': EmbedField('SubjectCode', 64, self.get_subjects),
            'time_created': EmbedField('iptc:timecreated', 11, self.get_time_created),
            'transmission_reference': EmbedField(['iptc:originaltransmissionreference',
                                                  'iptc:jobid',
                                                  'xmp:transmissionreference'],
                                                 32, self.get_transmission_reference),
        }
        self.output_dir = self.change_output_directory(output_dir)
        self.overwrite = overwrite or in_place
        self.in_place = in_place
        self.verify_images = verify_images
        self.defaults = [
            ('xmp:copyrightstatus', 'unknown'),
            ('xmp-xmprights:marked', '')
        ]
        self.logfile = open('embedder.log', 'a')


    def get_caption(self, rec):
        """Placeholder function returning the caption"""
        return rec.get('caption')


    def get_copyright(self, rec):
        """Placeholder function returning copyright info"""
        return rec.get('copyright')


    def get_creator(self, rec):
        """Placeholder function returning the creator"""
        return rec.get('creator')


    def get_credit_line(self, rec):
        """Placeholder function returning the credit line"""
        return rec.get('credit_line')


    def get_date_created(self, rec):
        """Placeholder function returning the date created"""
        return rec.get('date_created')


    def get_datetime_created(self, rec):
        """Placeholder function returning the full date and time created"""
        return rec.get('datetime_created')


    def get_headline(self, rec):
        """Placeholder function returning the headline"""
        return rec.get('headline')


    def get_inventory_numbers(self, rec):
        """Placeholder function returning the headline"""
        return rec.get('inventory_number')


    def get_job_id(self, rec):
        """Placeholder function returning the job ID"""
        return rec.get('job_id')


    def get_keywords(self, rec):
        """Placeholder function returning keywords"""
        return rec.get('keywords')


    def get_object_name(self, rec):
        """Placeholder function returning the object name"""
        return rec.get('object_name')


    def get_source(self, rec):
        """Placeholder function returning the media source"""
        return rec.get('source')


    def get_special_instructions(self, rec):
        """Placeholder function returning special instructions"""
        return rec.get('special_instructions')


    def get_subjects(self, rec):
        """Placeholder function returning subject codes"""
        return rec.get('subject_codes')


    def get_time_created(self, rec):
        """Placeholder function returning the time created"""
        return rec.get('time_created')


    def get_transmission_reference(self, rec):
        """Placeholder function returning the transmission reference"""
        return rec.get('transmission_reference')


    def get_url(self, rec):
        """Placeholder function returning the URL for this asset"""
        return rec.get_url()


    def get_mtime(self, path, mask='%Y:%m:%d %H:%M:%S%z'):
        """Get modification time for file at path"""
        mtime = datetime.fromtimestamp(int(os.path.getmtime(path)))
        return localize_datetime(mtime, mask=mask)


    def derive_metadata(self, rec, include_empty=False):
        """Derives image metadata from source data"""
        metadata = []
        for field in list(self.metadata_fields.values()):
            vals = field.function(rec)
            if not isinstance(vals, list):
                vals = [vals]
            for val in vals:
                self._check_length(val, field)
                if isinstance(field.name, list):
                    for fld in field.name:
                        metadata.append((fld, val))
                else:
                    metadata.append((field.name, val))
        # Remove empty fields if not instructed to keep them
        if not include_empty:
            metadata = [(name, val) for name, val in metadata if val]
        # Apply defaults
        metadata.extend(self.defaults)
        return metadata


    def embed_metadata(self, rec, path, new_name=None):
        """Embed metadata in the image file at the specified path

        Args:
            path (str): path to the image file
            rec (dict): metadata about the image

        Returns:
            Boolean indicating whether embed succeeded
        """
        # Copy and hash image data from original file
        fn = new_name if new_name else os.path.basename(path)
        #print('Embedding metadata into {}...'.format(fn))
        output_dir = self.output_dir
        if not self.in_place:
            # Preserve directory structure when copying files, but strip
            # the common prefix to keep the path names a reasonable length
            abspath = os.path.dirname(os.path.abspath(path))
            prefix = os.path.commonprefix([output_dir, abspath])
            dirpath = os.path.splitdrive(abspath[len(prefix):])[1].lstrip('/\\')
            output_dir = os.path.join(output_dir, dirpath)

        try:
            os.makedirs(output_dir)
        except OSError:
            pass

        dst = os.path.join(output_dir, fn)
        if not self.overwrite:
            try:
                open(dst, 'rb')
            except IOError:
                pass
            else:
                self.logfile.write('Info: {}: Already exists\n'.format(path))
                return dst

        # Verify original file
        if self.verify_images and not fn.lower().endswith(('.jp2')):
            pre_embed_hash = hash_image_data(path, output_dir=output_dir)

        try:
            shutil.copy2(path, dst)
        except shutil.SameFileError:
            pass

        # Use exiftool to embed metadata in file
        metadata = self.derive_metadata(rec.expand())
        cmd = ['exiftool', '-overwrite_original', '-v', '-m']
        for key, val in metadata:
            if isinstance(val, str):
                val = unidecode(val)
            cmd.append('-{}={}'.format(key, val))
        cmd.append(dst)

        tmpfile = tempfile.NamedTemporaryFile('w+')
        return_code = subprocess.call(cmd, cwd=os.getcwd(), stdout=tmpfile)
        if return_code:
            mask = 'Error: {}: Bad return code: {} ({})\n'
            msg = mask.format(path, cmd, return_code)
            self.logfile.write(msg)
            raise ValueError(msg)

        # Check temporary log for errors
        result = self._parse_exiftool_log(tmpfile)
        if '1 image files updated' not in result:
            msg = 'Error: {}: Embed failed\n'.format(path)
            self.logfile.write(msg)
            raise ValueError(msg)

        # Verify modified file
        if self.verify_images and not fn.lower().endswith(('.jp2')):
            #print(' Hashing image with embedded metadata...')
            post_embed_hash = hash_image_data(dst, output_dir=output_dir)
            if pre_embed_hash == post_embed_hash:
                self.logfile.write('Info: {}: Embed succeeded\n'.format(dst))
                return dst
            else:
                msg = 'Error: {}: Hash check failed\n'.format(dst)
                self.logfile.write(msg)
                raise ValueError(msg)
        else:
            self.logfile.write('Info: {}: Embed not checked\n'.format(dst))
            return dst


    def change_output_directory(self, output_dir):
        """Change the output directory"""
        self.output_dir = os.path.abspath(output_dir)
        try:
            os.makedirs(self.output_dir)
        except OSError:
            pass
        return self.output_dir


    def _check_length(self, val, field):
        """Verify that the length of the field"""
        mask = '{}="{}" is too long ({}/{} characters)'
        if val and len(val) > field.length:
            msg = mask.format(field.name, val, len(val), field.length)
            self.logfile.write('{}: {}\n'.format('Warning', msg))
            return False
        return True


    @staticmethod
    def _parse_exiftool_log(f):
        """Parses success/failure info from exiftool log"""
        result = []
        f.seek(0)
        for line in f:
            line = line.strip()
            if line.startswith('========'):
                result.append(line.split(' ', 1)[1])
            elif line.endswith('updated'):
                result.append(line)
        f.seek(0)
        return ': '.join(result)
