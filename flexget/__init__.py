#!/usr/bin/python

import os
import sys
import logging
from flexget import logger
from flexget.options import CoreOptionParser
from flexget import plugin
from flexget.manager import Manager

__version__ = '{subversion}'

log = logging.getLogger('main')


def main():
    """Main entry point for Command Line Interface"""

    logger.initialize()

    parser = CoreOptionParser()
    plugin.load_plugins(parser)

    options = parser.parse_args()[0]

    try:
        manager = Manager(options)
    except IOError, e:
        # failed to load config, TODO: why should it be handled here?
        log.exception(e)
        logger.flush_logging_to_console()
        sys.exit(1)

    log_level = logging.getLevelName(options.loglevel.upper())
    logger.start(os.path.join(manager.config_base, 'flexget.log'), log_level)

    manager.execute()
