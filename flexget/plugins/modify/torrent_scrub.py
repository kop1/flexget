""" Torrent Scrubber Plugin.
"""
from flexget import plugin, validator
from flexget.utils import bittorrent
from flexget.plugins.modify import torrent as modify_torrent


class TorrentScrub(plugin.Plugin):
    """ Scrubs torrents from unwanted keys.

        Example:
            feeds:
              rutorrent-fast-resume-infected-feed:
                torrent_scrub: resume
    """
    # Scrub at high level, but BELOW "torrent"
    SCRUB_PRIO = modify_torrent.TorrentFilename.TORRENT_PRIO - 10

    # Scrubbing modes
    SCRUB_MODES = ("off", "on", "all", "resume", "rtorrent",)

    # Keys of rTorrent / ruTorrent session data
    RT_KEYS = ("libtorrent_resume", "log_callback", "err_callback", "rtorrent")

    def validator(self):
        """ Our configuration model.
        """
        root = validator.factory()
        root.accept("boolean")
        root.accept("choice").accept_choices(self.SCRUB_MODES, ignore_case=True)
        root.accept("list").accept("text") # list of keys to scrub
        return root

    @plugin.priority(SCRUB_PRIO)
    def on_feed_modify(self, feed, config):
        """ Scrub items that are torrents, if they're affected.
        """
        if isinstance(config, list):
            mode = "fields"
        else:
            mode = str(config).lower()
            if mode in ("off", "false"):
                self.log.debug("Plugin configured, but disabled")
                return

        for entry in feed.entries:
            # Skip non-torrents
            if "torrent" not in entry:
                continue

            # Scrub keys as configured
            modified = set()
            metainfo = entry["torrent"].content
            infohash = entry["torrent"].get_info_hash()

            if mode in ("on", "all", "true"):
                modified = bittorrent.clean_meta(metainfo, including_info=(mode == "all"), logger=self.log.debug)
            elif mode in ("resume", "rtorrent"):
                if mode == "resume":
                    self.RT_KEYS = self.RT_KEYS[:1]

                for key in self.RT_KEYS:
                    if key in metainfo:
                        self.log.debug("Removing key '%s'..." % (key,))
                        del metainfo[key]
                        modified.add(key)
            elif mode == "fields":
                # Scrub all configured fields
                for key in config:
                    fieldname = key # store for logging
                    key = bittorrent.Torrent.KEY_TYPE(key)
                    field = metainfo

                    while field and '.' in key:
                        name, key = key.split('.', 1)
                        try:
                            field = field[name]
                        except KeyError:
                            # Key not found in this entry
                            field = None
                        self.log.trace((key, field))

                    if field and key in field:
                        self.log.debug("Removing key '%s'..." % (fieldname,))
                        del field[key]
                        modified.add(fieldname)
            else:
                raise ValueError("INTERNAL ERROR: Unknown mode %r" % mode)

            # Commit any changes back into entry
            if modified:
                entry["torrent"].content = metainfo
                entry["torrent"].modified = True
                self.log.info((("Key %s was" if len(modified) == 1 else "Keys %s were")
                    + " scrubbed from torrent '%s'!") % (", ".join(sorted(modified)), entry['title']))
                new_infohash = entry["torrent"].get_info_hash()
                if infohash != new_infohash:
                    self.log.warn("Info hash changed from #%s to #%s in '%s'" % (infohash, new_infohash, entry['filename']))

plugin.register(TorrentScrub, groups=["torrent"])
