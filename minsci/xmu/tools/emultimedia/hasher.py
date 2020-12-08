"""Contains methods to hash a file or image data from a file"""
import hashlib
import io
import os
import subprocess

from PIL import Image




def hasher(filestream, size=8192):
    """Generate MD5 hash for a file

    Args:
        filestream (file): stream of file to hash
        size (int): size of block. Should be multiple of 128.

    Return:
        Tuple of (filename, hash)
    """
    if size % 128:
        raise ValueError('size must be a multiple of 128')
    md5_hash = hashlib.md5()
    while True:
        chunk = filestream.read(size)
        if not chunk:
            break
        md5_hash.update(chunk)
    return md5_hash.hexdigest()



def hash_file(path):
    """Returns MD5 hash of a file

    Args:
        path (str): path to image

    Returns:
        Hash as string
    """
    #print('Hashing {}'.format(path))
    with open(path, 'rb') as f:
        return hasher(f)


def hash_image_data(path, output_dir='images'):
    """Returns MD5 hash of the image data in a file

    Args:
        path (str): path to image file

    Returns:
        Hash of image data as string
    """
    path = os.path.abspath(path)
    try:
        #print('Hashing image data from {}'.format(path))
        return _hash_image_data(path)
    except IOError as e:
        # Encountered a file format that PIL can't handle. Convert
        # file to something usable, hash, then delete the derivative.
        # The derivatives can be compared to ensure that the image hasn't
        # been messed up. Requires ImageMagick.
        #print('Hashing image data from derivative of {}'.format(path))
        fn = os.path.basename(path)
        jpeg = os.path.splitext(fn)[0] + '_temp.jpg'
        cmd = 'magick convert "{}" "{}"'.format(path, jpeg)
        return_code = subprocess.call(cmd, cwd=output_dir)
        if return_code:
            raise IOError('Hash failed: {}'.format(fn))
        dst = os.path.join(output_dir, jpeg)
        hexhash = _hash_image_data(dst)
        os.remove(dst)
        return hexhash


def _hash_image_data(path):
    """Hashes image data from a single file"""
    # The hashed out code below seems cleaner to me, but does not release the
    # file when it is complete (tested on pillow 6.2.1)
    #with Image.open(path) as im:
    #    return hashlib.md5(im.tobytes()).hexdigest()
    with open(path, 'rb') as f:
        im = Image.open(io.BytesIO(f.read()))
        return hashlib.md5(im.tobytes()).hexdigest()
