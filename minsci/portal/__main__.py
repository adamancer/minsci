"""Command line tools for preparing and stitching tilesets"""

import argparse
import sys

import requests_cache

from .portal import download, parse_config
from .reports import meteorites


requests_cache.install_cache('portal', expire_after=86400)


class MinSciParser(argparse.ArgumentParser):
    config = parse_config()

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
        download(**args)


    def _report_callback(args):
        return {
            'meteorites': meteorites
        }[vars(args)['name']]()


    if args is None:
        args = sys.argv[1:]

    parser = MinSciParser(
        description=('Command line utilities for the minsci module')
    )
    subparsers = parser.add_subparsers(help='sub-command help')

    # Defines subcommand to download data from portal
    download_parser = subparsers.add_parser(
        'download',
        help='Download data from the NMNH Geology Collections Data Portal'
    )
    # Construct rules for available args based on the portal setup file
    for arg in MinSciParser.config:
        download_parser.add_argument('-' + arg['dest'], **arg)
    download_parser.set_defaults(func=_download_callback)

    # Defines subcommand to report data from the portal
    report_parser = subparsers.add_parser(
        'report',
        help=('Build predefined reports using data from the NMNH Geology'
              ' Collections Data Portal')
    )
    report_parser.add_argument(
        '-name',
        dest='name',
        type=str,
        choices=['meteorites'],
        help='the name of a predefined report'
    )
    report_parser.set_defaults(func=_report_callback)

    args = parser.parse_args(args)
    args.func(args)


if __name__ == 'main':
    main()
