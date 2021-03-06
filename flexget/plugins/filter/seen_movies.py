import logging
from flexget.plugins.filter.seen import FilterSeen
from flexget.plugin import register_plugin, priority, register_parser_option

log = logging.getLogger('seenmovies')


class RepairSeenMovies(object):

    def on_process_start(self, feed):
        if not feed.manager.options.repair_seen_movies:
            return

        feed.manager.disable_feeds()

        from progressbar import ProgressBar, Percentage, Bar, ETA
        from flexget.manager import Session
        from seen import SeenField
        from flexget.utils.imdb import extract_id

        session = Session()

        index = 0
        count = 0
        total = session.query(SeenField).filter(SeenField.field == u'imdb_url').count()

        widgets = ['Repairing: ', ETA(), ' ', Percentage(), ' ', Bar(left='[', right=']')]
        bar = ProgressBar(widgets=widgets, maxval=total).start()

        for seen in session.query(SeenField).filter(SeenField.field == u'imdb_url').all():
            index += 1
            if index % 5 == 0:
                bar.update(index)
            value = u'http://www.imdb.com/title/%s/' % extract_id(seen.value)
            if value != seen.value:
                count += 1
                seen.value = value
                seen.field = unicode('imdb_url')

        bar.finish()
        session.commit()

        print 'Fixed %s/%s URLs' % (count, total)


class FilterSeenMovies(FilterSeen):
    """
        Prevents movies being downloaded twice.
        Works only on entries which have imdb url available.

        How duplicate movie detection works:
        1) Remember all imdb urls from downloaded entries.
        2) If stored imdb url appears again, entry is rejected.
    """

    def __init__(self):
        # remember and filter by these fields
        self.fields = ['imdb_id', 'tmdb_id']
        self.keyword = 'seen_movies'

    def validator(self):
        from flexget import validator
        root = validator.factory('choice', message="must be one of the following: strict, loose")
        root.accept_choices(['strict', 'loose'])
        return root

    # We run last (-255) to make sure we don't reject duplicates before all the other plugins get a chance to reject.
    @priority(-255)
    def on_feed_filter(self, feed, config):
        # strict method
        if config == 'strict':
            for entry in feed.entries:
                if 'imdb_id' not in entry and 'tmdb_id' not in entry:
                    log.info('Rejecting %s because of missing movie (imdb or tmdb) id' % entry['title'])
                    feed.reject(entry, 'missing movie (imdb or tmdb) id, strict')
        # call super
        super(FilterSeenMovies, self).on_feed_filter(feed, True)
        # check that two copies of a movie have not been accepted this run
        imdb_ids = set()
        tmdb_ids = set()
        for entry in feed.accepted:
            if 'imdb_id' in entry:
                if entry['imdb_id'] in imdb_ids:
                    feed.reject(entry, 'already accepted once in feed')
                    continue
                else:
                    imdb_ids.add(entry['imdb_id'])
            if 'tmdb_id' in entry:
                if entry['tmdb_id'] in tmdb_ids:
                    feed.reject(entry, 'already accepted once in feed')
                    continue
                else:
                    tmdb_ids.add(entry['tmdb_id'])

register_plugin(FilterSeenMovies, 'seen_movies', api_ver=2)
register_plugin(RepairSeenMovies, '--repair-seen-movies', builtin=True)

register_parser_option('--repair-seen-movies', action='store_true', dest='repair_seen_movies', default=False,
                       help='Repair seen movies database (required only when upgrading from old problematic version)')
