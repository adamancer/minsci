"""Tools to embed metadata in image files"""

import os
import shutil
import subprocess
import tempfile
from collections import namedtuple
from datetime import datetime

from unidecode import unidecode

from .hasher import hash_image_data
from ....helpers import localize_datetime


EmbedField = namedtuple('EmbedField', ['name', 'length', 'function'])
LOGFILE = open('embedder.log', 'ab', 0)

class Embedder(object):
    """Tools to embed metadata in image files"""

    def __init__(self, output_dir, overwrite=True):
        self.metadata_fields = {
            'copyright': EmbedField('Copyright', 128, self.get_copyright),
            'creator': EmbedField('Creator', 64, self.get_creator),
            'datetime_created': EmbedField('CreateDate', 64, self.get_datetime_created),
            'caption': EmbedField('Description', 2000, self.get_caption),
            'credit_line': EmbedField('iptc:credit', 64, self.get_credit_line),
            'date_created': EmbedField('iptc:datecreated', 8, self.get_date_created),
            'headline': EmbedField('iptc:headline', 64, self.get_headline),
            'job_id': EmbedField('iptc:jobid', 64, self.get_job_id),
            'keywords': EmbedField('Keywords', 64, self.get_keywords),
            'object_name': EmbedField('iptc:objectname', 64, self.get_object_name),
            'source': EmbedField('iptc:source', 64, self.get_source),
            'special_instructions': EmbedField('iptc:specialinstructions', 256,
                                               self.get_special_instructions),
            'subject': EmbedField('SubjectCode', 64, self.get_subjects),
            'time_created': EmbedField('iptc:timecreated', 11, self.get_time_created),
            'transmission_reference': EmbedField('iptc:originaltransmissionreference',
                                                 64, self.get_transmission_reference),
        }
        self.output_dir = self.change_output_directory(output_dir)
        self.logfile = LOGFILE
        self.overwrite = overwrite
        self.defaults = [
            ('xmp:copyrightstatus', 'unknown'),
            ('xmp-xmprights:marked', '')
        ]


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


    def get_mtime(self, path, mask='%Y:%m:%d %H:%M:%S%z'):
        """Get modification time for file at path"""
        mtime = datetime.fromtimestamp(int(os.path.getmtime(path)))
        return localize_datetime(mtime, mask=mask)


    def derive_metadata(self, rec, include_empty=False):
        """Derives image metadata from source data"""
        metadata = []
        for field in self.metadata_fields.values():
            vals = field.function(rec)
            if not isinstance(vals, list):
                vals = [vals]
            for val in vals:
                self._check_length(val, field)
                metadata.append((field.name, val))
        # Remove empty fields if not instructed to keep them
        if not include_empty:
            metadata = [(name, val) for name, val in metadata if val]
        # Apply defaults
        metadata.extend(self.defaults)
        return metadata


    def embed_metadata(self, path, rec):
        """Embed metadata in the image file at the specified path

        Args:
            path (str): path to the image file
            rec (dict): metadata about the image

        Returns:
            Boolean indicating whether embed succeeded
        """
        # Copy and hash image data from original file
        fn = os.path.basename(path)
        print 'Embedding metadata into {}...'.format(fn)
        dst = os.path.join(self.output_dir, fn)
        if not self.overwrite:
            try:
                open(dst, 'rb')
            except IOError:
                pass
            else:
                self.logfile.write('Info: {}: Already exists\n'.format(path))
                return dst
        print ' Hashing original image...'
        pre_embed_hash = hash_image_data(path, output_dir=self.output_dir)
        if path != dst:
            print ' Copying file to {}...'.format(self.output_dir)
            shutil.copy2(path, dst)
        # Use exiftool to embed metadata in file
        metadata = self.derive_metadata(rec)
        cmd = ['exiftool', '-overwrite_original', '-v']
        for key, val in metadata:
            if isinstance(val, unicode):
                val = unidecode(val)
            cmd.append('-{}={}'.format(key, val))
        cmd.append(dst)
        print ' Writing metadata...'
        tmpfile = tempfile.NamedTemporaryFile()
        return_code = subprocess.call(cmd, cwd=os.getcwd(), stdout=tmpfile)
        if return_code:
            self.logfile.write('Error: {}: Bad return'
                               ' code ({})\n'.format(path, return_code))
        # Check temporary log for errors
        result = self._parse_log(tmpfile)
        if '1 image files updated' not in result:
            self.logfile.write('Error: {}: Embed failed\n'.format(path))
            return False
        # Check modified file
        print ' Hashing image with embedded metadata...'
        post_embed_hash = hash_image_data(dst, output_dir=self.output_dir)
        if pre_embed_hash == post_embed_hash:
            self.logfile.write('Info: {}: Embed succeeded\n'.format(dst))
            return dst
        else:
            self.logfile.write('Error: {}: Hash check failed\n'.format(dst))
            return False


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
        mask = 'Warning: {} is too long ({}/{} characters)'
        if len(val) > field.length:
            msg = mask.format(field.name, len(val), field.length)
            self.logfile.write('{}: {}\n'.format('Warning', msg))
            return False
        return True


    @staticmethod
    def _parse_log(f):
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
