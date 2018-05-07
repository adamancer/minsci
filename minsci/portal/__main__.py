"""Command line tools for preparing and stitching tilesets"""

import argparse
import sys

import requests_cache

import portal


requests_cache.install_cache('portal', expire_after=86400)


class MinSciParser(argparse.ArgumentParser):
    config = portal.parse_config()

    def error(self, message):
        """Return help text on error with command
           From http://stackoverflow.com/questions/4042452"""
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)


def main(args=None):

    def _download_callback(args):
        """Downloads data from collections portal"""
        args = vars(args)
        if not args['offset']:
            args['offset'] = 0
        del args['func']
        portal.download(**args)

    if args is None:
        args = sys.argv[1:]

    parser = MinSciParser(
        description=('Command line utilities for the minsci module')
    )
    subparsers = parser.add_subparsers(help='sub-command help')

    # Subcommand for downloading
    download_parser = subparsers.add_parser(
        'download',
        help='Download data from the NMNH Geology Collections Data Portal'
    )
    # Construct rules for available args based on the portal setup file
    for arg in MinSciParser.config:
        download_parser.add_argument('-' + arg['dest'], **arg)
    download_parser.set_defaults(func=_download_callback)

    args = parser.parse_args(args)
    args.func(args)


if __name__ == 'main':
    main()
