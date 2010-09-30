#-*- coding: utf-8 -*-

'''Implementation of Twitter information and timeline thread control class
'''
 
################################################################################
#
# Copyright (c) 2010 University of Tsukuba Linux User Group
#
# This file is part of "gwit".
#
# "gwit" is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# "gwit" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "gwit".  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################


import sys
import time
import socket
import urllib2
import threading

import twoauth
import twoauth.streaming

# Twitter API Class
class TwitterAPI:
    def __init__(self, screen_name, ckey, csecret, atoken, asecret):
        # Generate API Library instance
        self.api = twoauth.api(ckey, csecret, atoken, asecret, screen_name)
        self.sapi = twoauth.streaming.StreamingAPI(self.api.oauth)
        
        self.myname = self.api.user["screen_name"]
        self.me = None
        self.my_name = screen_name
        #self.threads = list()
        self.apilock = threading.Lock()
        
        # User, Status Buffer
        self.users = dict()
        self.statuses = dict()
        self.followers = set()
        self.following = set()
        
        t = threading.Thread(target=self.get_following_followers)
        t.start()
    
    def init_twitpic(self, apikey):
        import twoauth.twitpic
        self.twitpic = twoauth.twitpic.Twitpic(self.api.oauth, apikey)
    
    def get_following_followers(self):
        # Get followers
        self.followers.update([int(i) for i in self.api_wrapper(self.api.followers_ids)])
        self.following.update([int(i) for i in self.api_wrapper(self.api.friends_ids)])
    
    def add_statuses(self, slist):
        for i in slist:
            self.add_status(i)
    
    def add_status(self, status):
        self.statuses[status.id] = status
        self.add_user(status.user)
        
        if status.retweeted_status != None:
            self.add_status(status.retweeted_status)
    
    def add_user(self, user):
        self.users[user.id] = user
        
        if user.screen_name == self.myname:
            self.me = user
    
    def get_user_from_screen_name(self, screen_name):
        # search user from screen_name
        for user in self.users.itervalues():
            if user.screen_name == screen_name:
                return user
        
        return None
    
    def get_statuses(self, ids):
        return tuple(self.statuses[i] for i in sorted(tuple(ids), reverse=True))
    
    def api_wrapper(self, method, *args, **kwargs):
        for i in range(3):
            try:
                self.apilock.acquire()
                response = None
                response = method(*args, **kwargs)
                break
            except urllib2.HTTPError, e:
                if e.code == 400:
                    print >>sys.stderr, "[Error] Rate Limitting %s (%s)" % (e, method.func_name)
                    break
                elif e.code == 403:
                    print >>sys.stderr, "[Error] Access Denied %s (%s)" % (e, method.func_name)
                    break
                elif e.code == 404:
                    print >>sys.stderr, "[Error] Not Found %s (%s)" % (e, method.func_name)
                    break
                
                if i >= 3:
                    self.on_twitterapi_error(method, e)
                
                print >>sys.stderr, "[Error] %d: TwitterAPI %s (%s)" % (i, e, method.func_name)
            except socket.timeout:
                print >>sys.stderr, "[Error] %d: TwitterAPI timeout (%s)" % (i, method.func_name)
            except Exception, e:
                print >>sys.stderr, "[Error] %d: TwitterAPI %s (%s)" % (i, e, method.func_name)
            finally:
                self.apilock.release()
            
            time.sleep(5)
        
        return response
    
    def on_twitterapi_error(self, method, e): pass
