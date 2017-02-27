import hashlib
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
    """Get MD5 hash of an image file

    Args:
        path (str): path to image

    Returns:
        Hash as string
    """
    return hasher(open(path, 'rb'))


def hash_image_data(path, output_dir='images'):
    """Returns hash based on image data

    Args:
        path (str): path to image file

    Returns:
        Hash of image data as string
    """
    try:
        return hashlib.md5(Image.open(path).tobytes()).hexdigest()
    except IOError:
        # Encountered a file format that PIL can't handle. Convert
        # file to something usable, hash, then delete the derivative.
        fn = os.path.basename(path)
        jpeg = os.path.splitext(fn)[0] + '.jpg'
        cmd = 'iconvert "{}" "{}"'.format(path, jpeg)
        return_code = subprocess.call(cmd, cwd=output_dir)
        if return_code:
            raise IOError('Hash failed')
        dst = os.path.join(output_dir, jpeg)
        hexhash = hashlib.md5(Image.open(dst).tobytes()).hexdigest()
        os.remove(dst)
        return hexhash
