# mindl - A plugin-based downloading tool.
# Copyright (C) 2016 Mino <mino@minomino.org>

# This file is part of mindl.

# mindl is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# mindl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with mindl. If not, see <http://www.gnu.org/licenses/>.

import argparse
import logging
import sys

from mindl import DownloadManager, PluginManager

from collections import namedtuple

ArgumentOption = namedtuple("ArgumentOption", ["plugin", "key", "value"])

class UrlListParseAction(argparse.Action):
    """
    Custom action to avoid having the --file argument overwrite regular URLs, or vice versa.
    Instead, this action will simply merge regular URLs with file URLs.
    """
    def __call__(self, parser, namespace, urls, option_string=None):
        dest = getattr(namespace, self.dest)
        if dest is urls:
            return
        
        for url in urls:
            dest.append(url)

class UrlListFileParseAction(argparse.Action):
    """Custom action to append all the URLs in a file into its destination list."""
    def __call__(self, parser, namespace, file, option_string=None):
        dest = getattr(namespace, self.dest)
        if dest is None:
            dest = []
            setattr(namespace, self.dest, dest)
        
        for line in [l.strip() for l in file.readlines() if l.strip()]:
            dest.append(line)

def init_logger(debug=False):
    logger = logging.getLogger("mindl")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    # Console
    console_fmt = logging.Formatter("(%(asctime)s %(levelname)s) %(message)s", "%H:%M")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger

def configure_parser():
    def key_value_parse(text):
        split = text.split("=", 1)
        if len(split) == 1:
            logger = logging.getLogger("mindl")
            logger.critical("The key-value pair '{}' is not in the right format. Please use 'key=value'.".format(text))
            return ""
            exit(1)

        key, value = split
        plugin = None
        split = key.split(":", 1)
        if len(split) == 2:
            plugin, key = split
        
        return ArgumentOption(plugin, key, value)
    
    parser = argparse.ArgumentParser(description='A plugin-based downloader.', prog="mindl")
    parser.add_argument("url", metavar="URL", nargs="*", help="the URL to download from", default=[], action=UrlListParseAction)
    parser.add_argument("-o", "--option", dest="options", metavar="KEY=VALUE", type=key_value_parse, default=[], action="append",
                        help="a key-value pair to be passed to the plugin to define its options")
    parser.add_argument("-v", "--verbose", action="store_true", help="makes the logger output debugging strings")
    parser.add_argument("-d", "--defaults", action="store_true",
                        help="makes the plugin use default values for options if it can instead of prompting")
    parser.add_argument("-p", "--plugin", help="explicitly set which plugin should handle the URL in the case where"
                        "two or more plugins can handle the same URL")
    parser.add_argument("-f", "--file", help="the path to a text file containing URLs to be processed, separated by lines",
                        metavar="PATH", type=argparse.FileType("r", encoding="UTF-8"), dest="url", action=UrlListFileParseAction)
    parser.add_argument("-D", "--directory", help="the directory in which the downloads will go to ('downloads' by default)",
                        default="downloads")
    
    return parser

def main(args):
    logger = init_logger(debug=args.verbose)

    # Set the base download directory. Defaults to "downloads".
    DownloadManager.base_directory = args.directory
    
    if not args.url:
        logger.info("Nothing to do, as no URLs were passed. Use the -h argument to see the usage.")
        exit()
    for url in args.url:
        pm = PluginManager()
        eligible = pm.find_handlers(url)

        # If --plugin is used, only allow the plugin with that particular name.
        if args.plugin:
            new_eligible = []
            for p, v in eligible:
                if p.name.lower() == args.plugin.lower():
                    new_eligible.append((p, v))
                    break
            if not new_eligible:
                logger.critical("The explicitly set plugin '{}' was not not found in the list of plugins that"
                                "were eligible to deal with the URL.".format(args.plugin))
                exit(1)
            
            eligible = new_eligible

        if eligible:
            if len(eligible) > 1:
                plugin, version = pm.select_plugin(url, eligible)
            else:
                plugin, version = eligible[0]
            
            logger.info("URL is being handled by plugin: {} v{}".format(plugin.name, version))
            plugin.process_options()
            # If options as key-value pairs were passed using arguments, we allow the user to explicitly set the plugin
            # the option will apply for, so we need to filter them out if that is the case.
            options = dict([(o.key, o.value) for o in args.options if o.plugin is None or o.plugin.lower() == plugin.name.lower()])
            # Let the plugin manager set the key-value pairs if any, then ask for manual input if needed.
            plugin.input_options(options, defaults=args.defaults)
            plugin._debug_logger = args.verbose
            dm = DownloadManager(plugin(url))
            dm.start_download()
            dm.finalize()
        else:
            logger.error("No plugins can handle the passed URL: {}".format(url))
    
if __name__ == '__main__':
    parser = configure_parser()
    if len(sys.argv) < 2:
        parser.print_help()
        exit()

    main(parser.parse_args())
