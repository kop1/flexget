import logging
from sqlalchemy.schema import Index
from sqlalchemy.sql.expression import desc
from flexget.event import fire_event
from flexget.manager import Base
from flexget.plugin import register_plugin, priority, get_plugin_by_name, PluginError
from flexget.utils.log import log_once
from flexget.utils.titles.movie import MovieParser
from sqlalchemy import Column, Integer, String, Unicode, DateTime
from datetime import datetime, timedelta

log = logging.getLogger('proper_movies')


class ProperMovie(Base):

    __tablename__ = 'proper_movies'

    id = Column(Integer, primary_key=True)
    title = Column(Unicode)
    feed = Column(Unicode)
    imdb_id = Column(String, index=True)
    quality = Column(String)
    proper_count = Column(Integer)
    added = Column(DateTime)

    def __init__(self):
        self.added = datetime.now()

    def __repr__(self):
        return '<ProperMovie(title=%s,feed=%s,imdb_id=%s,quality=%s,proper_count=%s,added=%s)>' % \
            (self.title, self.feed, self.imdb_id, self.quality, self.proper_count, self.added)


# create index
columns = Base.metadata.tables['proper_movies'].c
Index('proper_movies_imdb_id_quality_proper', columns.imdb_id, columns.quality, columns.proper_count)


class FilterProperMovies(object):
    """
        Automatically download proper movies.

        Configuration:

            proper_movies: n <minutes|hours|days|weeks>

        or permanently:

            proper_movies: yes

        Value no will disable plugin.
    """

    def validator(self):
        from flexget import validator
        root = validator.factory('root')
        root.accept('boolean')
        regexp = root.accept('regexp_match')
        regexp.accept('\d+ (minutes|hours|days|weeks)')
        return root

    @priority(512)
    def on_feed_filter(self, feed, config):
        log.debug('check for enforcing')

        # parse config
        if isinstance(config, bool):
            # configured a boolean false, disable plugin
            if not config:
                return
            # configured a boolean true, disable timeframe
            timeframe = None
        else:
            # parse time window
            amount, unit = config.split(' ')
            log.debug('amount: %s unit: %s' % (repr(amount), repr(unit)))
            params = {unit: int(amount)}
            try:
                timeframe = timedelta(**params)
            except TypeError:
                raise PluginError('Invalid time format', log)

        # throws DependencyError if not present aborting feed
        imdb_lookup = get_plugin_by_name('imdb_lookup').instance

        for entry in feed.entries:
            if 'imdb_id' not in entry:
                try:
                    imdb_lookup.lookup(entry)
                except PluginError, pe:
                    log_once(pe.value)
                    continue

            parser = MovieParser()
            parser.data = entry['title']
            parser.parse()

            quality = parser.quality.name

            log.debug('quality: %s' % quality)
            log.debug('imdb_id: %s' % entry['imdb_id'])
            log.debug('current proper count: %s' % parser.proper_count)

            proper_movie = feed.session.query(ProperMovie).\
                filter(ProperMovie.imdb_id == entry['imdb_id']).\
                filter(ProperMovie.quality == quality).\
                order_by(desc(ProperMovie.proper_count)).first()

            if not proper_movie:
                log.debug('no previous download recorded for %s' % entry['imdb_id'])
                continue

            highest_proper_count = proper_movie.proper_count
            log.debug('highest_proper_count: %i' % highest_proper_count)

            accept_proper = False
            if parser.proper_count > highest_proper_count:
                log.debug('proper detected: %s ' % proper_movie)

                if timeframe is None:
                    accept_proper = True
                else:
                    expires = proper_movie.added + timeframe
                    log.debug('propers timeframe: %s' % timeframe)
                    log.debug('added: %s' % proper_movie.added)
                    log.debug('propers ignore after: %s' % str(expires))
                    if datetime.now() < expires:
                        accept_proper = True
                    else:
                        log.verbose('Proper `%s` has past it\'s expiration time' % entry['title'])

            if accept_proper:
                log.info('Accepting proper version previously downloaded movie `%s`' % entry['title'])
                # TODO: does this need to be called?
                # fire_event('forget', entry['imdb_url'])
                fire_event('forget', entry['imdb_id'])
                feed.accept(entry, 'proper version of previously downloaded movie')

    def on_feed_exit(self, feed, config):
        """Add downloaded movies to the database"""
        log.debug('check for learning')
        for entry in feed.accepted:
            if 'imdb_id' not in entry:
                log.debug('`%s` does not have imdb_id' % entry['title'])
                continue

            parser = MovieParser()
            parser.data = entry['title']
            parser.parse()

            quality = parser.quality.name

            log.debug('quality: %s' % quality)
            log.debug('imdb_id: %s' % entry['imdb_id'])
            log.debug('proper count: %s' % parser.proper_count)

            proper_movie = feed.session.query(ProperMovie).\
                filter(ProperMovie.imdb_id == entry['imdb_id']).\
                filter(ProperMovie.quality == quality).\
                filter(ProperMovie.proper_count == parser.proper_count).first()

            if not proper_movie:
                pm = ProperMovie()
                pm.title = entry['title']
                pm.feed = feed.name
                pm.imdb_id = entry['imdb_id']
                pm.quality = quality
                pm.proper_count = parser.proper_count
                feed.session.add(pm)
                log.debug('added %s' % pm)
            else:
                log.debug('%s already exists' % proper_movie)

register_plugin(FilterProperMovies, 'proper_movies', api_ver=2)
