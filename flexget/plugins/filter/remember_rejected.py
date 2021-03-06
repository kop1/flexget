import hashlib
import logging
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Unicode, DateTime, ForeignKey, and_, Index
from sqlalchemy.orm import relation
from flexget import schema
from flexget.event import event
from flexget.manager import Session
from flexget.plugin import register_plugin, register_parser_option, register_feed_phase
from flexget.utils.sqlalchemy_utils import table_columns, drop_tables, table_add_column
from flexget.utils.tools import parse_timedelta

log = logging.getLogger('remember_rej')
Base = schema.versioned_base('remember_rejected', 3)


@schema.upgrade('remember_rejected')
def upgrade(ver, session):
    if ver is None:
        columns = table_columns('remember_rejected_entry', session)
        if 'uid' in columns:
            # Drop the old table
            log.info('Dropping old version of remember_rejected_entry table from db')
            drop_tables(['remember_rejected_entry'], session)
            # Create new table from the current model
            Base.metadata.create_all(bind=session.bind)
            # We go directly to version 2, as remember_rejected_entries table has just been made from current model
            # TODO: Fix this somehow. Just avoid dropping tables?
            ver = 3
        else:
            ver = 0
    if ver == 0:
        log.info('Adding reason column to remember_rejected_entry table.')
        table_add_column('remember_rejected_entry', 'reason', String, session)
        ver = 1
    if ver == 1:
        log.info('Adding `added` column to remember_rejected_entry table.')
        table_add_column('remember_rejected_entry', 'added', DateTime, session, default=datetime.now)
        ver = 2
    if ver == 2:
        log.info('Adding expires column to remember_rejected_entry table.')
        table_add_column('remember_rejected_entry', 'expires', DateTime, session)
        ver = 3
    return ver


class RememberFeed(Base):

    __tablename__ = 'remember_rejected_feeds'

    id = Column(Integer, primary_key=True)
    name = Column(Unicode)
    hash = Column(String)

    entries = relation('RememberEntry', backref='feed', cascade='all, delete, delete-orphan')


class RememberEntry(Base):

    __tablename__ = 'remember_rejected_entry'

    id = Column(Integer, primary_key=True)
    added = Column(DateTime, default=datetime.now)
    expires = Column(DateTime)
    title = Column(Unicode)
    url = Column(String)
    rejected_by = Column(String)
    reason = Column(String)

    feed_id = Column(Integer, ForeignKey('remember_rejected_feeds.id'), nullable=False)

Index('remember_feed_title_url', RememberEntry.feed_id, RememberEntry.title, RememberEntry.url)


class FilterRememberRejected(object):
    """Internal.
    Rejects entries which have been rejected in the past.

    This is enabled when item is rejected with remember=True flag.

    Example:
        feed.reject(entry, 'message', remember=True)
    """

    def on_process_start(self, feed, config):
        """Purge remembered entries if the config has changed and write new hash"""
        # No session on process start, make our own
        session = Session()
        # Delete expired items
        session.query(RememberEntry).filter(RememberEntry.expires < datetime.now()).delete()
        # Generate hash for current config
        config_hash = hashlib.md5(str(feed.config.items())).hexdigest()
        # See if the feed has the same hash as last run
        old_feed = session.query(RememberFeed).filter(RememberFeed.name == feed.name).first()
        if old_feed and (old_feed.hash != config_hash or feed.manager.options.forget_rejected):
            if feed.manager.options.forget_rejected:
                log.info('Forgetting feed %s previous rejections.' % feed.name)
            else:
                log.debug('Feed %s config has changed since last run, purging remembered entries.' % feed.name)
            session.delete(old_feed)
            old_feed = None
        if not old_feed:
            # Create this feed in the db if not present
            session.add(RememberFeed(name=feed.name, hash=config_hash))
        session.commit()

    # This runs before metainfo phase to avoid re-parsing metainfo for entries that will be rejected
    def on_feed_prefilter(self, feed, config):
        """Reject any remembered entries from previous runs"""
        (feed_id,) = feed.session.query(RememberFeed.id).filter(RememberFeed.name == feed.name).first()
        reject_entries = feed.session.query(RememberEntry).filter(RememberEntry.feed_id == feed_id)
        if reject_entries.count():
            # Reject all the remembered entries
            for entry in feed.entries:
                if not entry.get('url'):
                    # We don't record or reject any entries without url
                    continue
                reject_entry = reject_entries.filter(and_(RememberEntry.title == entry['title'],
                                                          RememberEntry.url == entry['url'])).first()
                if reject_entry:
                    feed.reject(entry, 'Rejected on behalf of %s plugin: %s' %
                                       (reject_entry.rejected_by, reject_entry.reason))

    def on_entry_reject(self, feed, entry, remember=None, remember_time=None, **kwargs):
        # We only remember rejections that specify the remember keyword argument
        if not remember and not remember_time:
            return
        if entry.get('imaginary'):
            log.debug('Not remembering rejection for imaginary entry `%s`' % entry['title'])
            return
        expires = None
        if remember_time:
            if isinstance(remember_time, basestring):
                remember_time = parse_timedelta(remember_time)
            expires = datetime.now() + remember_time
        if not entry.get('title') or not entry.get('original_url'):
            log.debug('Can\'t remember rejection for entry without title or url.')
            return
        message = 'Remembering rejection of `%s`' % entry['title']
        if remember_time:
            message += ' for %i minutes' % (remember_time.seconds / 60)
        log.info(message)
        (remember_feed_id,) = feed.session.query(RememberFeed.id).filter(RememberFeed.name == feed.name).first()
        feed.session.add(RememberEntry(title=entry['title'], url=entry['original_url'], feed_id=remember_feed_id,
                                       rejected_by=feed.current_plugin, reason=kwargs.get('reason'), expires=expires))
        # The test stops passing when this is taken out for some reason...
        feed.session.flush()


@event('manager.db_cleanup')
def db_cleanup(session):
    # Remove entries older than 30 days
    result = session.query(RememberEntry).filter(RememberEntry.added < datetime.now() - timedelta(days=30)).delete()
    if result:
        log.verbose('Removed %d entries from remember rejected table.' % result)


register_plugin(FilterRememberRejected, 'remember_rejected', builtin=True, api_ver=2)
register_feed_phase('prefilter', after='input')
register_parser_option('--forget-rejected', action='store_true', dest='forget_rejected',
                       help='Forget all previous rejections so entries can be processed again.')
