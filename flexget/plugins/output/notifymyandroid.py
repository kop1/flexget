from httplib import HTTPSConnection
from urllib import urlencode
import logging
from flexget.plugin import get_plugin_by_name, register_plugin

log = logging.getLogger('notifymyandroid')

__version__ = 0.1
headers = {'User-Agent': "FlexGet NMA plugin/%s" % str(__version__), 
           'Content-type': "application/x-www-form-urlencoded"}


class OutputNotifyMyAndroid(object):
    """
    notifymyandroid:
      apikey: xxxxxxx
      [application: application name, default FlexGet]
      [event: event title, default New Release]
      [priority: -2 - 2 (2 = highest), default 0]
      
    Configuration parameters are also supported from entries (eg. through set).
    """
    
    def validator(self):
        from flexget import validator
        config = validator.factory('dict')
        config.accept('text', key='apikey', required=True)
        config.accept('text', key='application')
        config.accept('text', key='event')
        config.accept('integer', key='priority')
        return config

    def on_process_start(self, feed, config):
        """                                                                                                                                                                                                     
            Register the usable set: keywords.
        """ 
        set_plugin = get_plugin_by_name('set') 
        set_plugin.instance.register_keys({'apikey': 'text', 'application': 'text',
                                           'event': 'text', 'priority': 'integer'})

    def prepare_config(self, config):
        if isinstance(config, bool):
            config = {'enabled': config}
        config.setdefault('apikey', '')
        config.setdefault('application', 'FlexGet')
        config.setdefault('event', 'New release')
        config.setdefault('priority', 0)
        return config                                                                                                                                                                                           

    def on_feed_output(self, feed, config):
        # get the parameters
        config = self.prepare_config(config)
        for entry in feed.accepted:

            if feed.manager.options.test:
                log.info("Would send notifymyandroid message about: %s", entry['title'])
                continue

            apikey = entry.get('apikey', config['apikey'])
            application = entry.get('application', config['application'])
            event = entry.get('event', config['event'])
            priority = entry.get('priority', config['priority'])
            description = entry['title']
            
            # Open connection
            h = HTTPSConnection('nma.usk.bz')
            
            # Send the request
            data = {'priority': priority, 'application': application, 'apikey': apikey, \
                    'event': event, 'description': description}
            h.request("POST", "/publicapi/notify", headers=headers, body=urlencode(data))

            # Check if it succeeded
            response = h.getresponse()
            request_status = response.status

            # error codes and messages from http://nma.usk.bz/api.php
            if request_status == 200:
                log.debug("NotifyMyAndroid message sent")
            elif request_status == 400: 
                log.error("Bad request, the parameters you provided did not validate")
            elif request_status == 401: 
                log.error("Not authorized, the API key given is not valid, and does not correspond to a user.")
            elif request_status == 402: 
                log.error("Not acceptable, your IP address has exceeded the API limit.")
            elif request_status == 500: 
                log.error("Internal server error, something failed to execute properly on the NotifyMyAndroid side.")
            else:
                log.error("Unknown error when sending NotifyMyAndroid message")

register_plugin(OutputNotifyMyAndroid, 'notifymyandroid', api_ver=2)
