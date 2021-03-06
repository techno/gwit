#-*- coding: utf-8 -*-

'''User icon getter and store
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


import pygtk
pygtk.require('2.0')
import gtk

import sys
import os
import os.path
import threading
import urllib2
import cStringIO
import time
import hashlib
import random
import Queue
try:
    import Image
except ImportError:
    USE_PIL = False
else:
    USE_PIL = True

# User Icon Store
class IconStore(object):
    iconmode = True
    
    # Cache attrs
    ICON_CACHE_PATH = os.path.expanduser("~/.gwit/ico/")
    ICON_CACHE_MAX = 10 * 1024 * 1024    # 10MB
    
    def __init__(self, background_slot = 2):
        self.icons = dict()
        self.stores = list()
        self.iconthread = list()
        
        self.background_slot = background_slot
        
        # load default icon
        iconpath = os.path.join(os.path.dirname(__file__), "images/none.png")
        self.default_icon = gtk.gdk.pixbuf_new_from_file(iconpath)
        
        for i in range(background_slot):
            t = IconThread(self.icons, self.stores)
            t.start()
            self.iconthread.append(t)
    
    def get(self, user):
        # get from cache
        icon = self.icons.get(user.profile_image_url)
        
        if not icon:
            icon = self.default_icon
            if user.id not in self.icons:
                self.icons[user.profile_image_url] = self.default_icon
                self.new(user)
        
        return icon
    
    def new(self, user):
        # New Icon thread start if iconmode is True
        if self.iconmode:
            n = random.randint(0, self.background_slot - 1)
            self.iconthread[n].put(user)
    
    def add_store(self, store, n):
        self.stores.append((store, n))
    
    def remove_store(self, store):
        remove = None
        
        for i in self.stores:
            if store == i[0]:
                remove = i
                break
        
        if remove:
            self.stores.remove(remove)
    
    def stop(self):
        for t in self.iconthread:
            t.stop()
        
        path = IconStore.ICON_CACHE_PATH
        stats = [(f, os.stat(os.path.join(path, f)))
                 for f in os.listdir(path)]
        
        # icon cache > ICON_CACHE_MAX
        cache_size = sum([s.st_size for _, s in stats])
        if cache_size > IconStore.ICON_CACHE_MAX:
            # sort by last access time
            def get_st_atime(stat): return stat[1].st_atime
            stats.sort(key = get_st_atime)
            
            # remove cache
            for f, s in stats:
                try: os.remove(os.path.join(path, f))
                except: continue
                cache_size -= s.st_size
                if cache_size < IconStore.ICON_CACHE_MAX: break

class IconThread(threading.Thread):
    twitter = None
    use_icon_cache = True
    
    def __init__(self, icons, stores):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.setName("icon")
        
        self.icons = icons
        self.stores = stores
        self.queue = Queue.Queue()
        
        self._die = False
        
        if not os.path.exists(IconStore.ICON_CACHE_PATH):
            os.mkdir(IconStore.ICON_CACHE_PATH)
    
    def put(self, user):
        self.queue.put(user)
    
    def run(self):
        while not self._die:
            user = self.queue.get()
            
            sha1 = hashlib.sha1(user.profile_image_url).hexdigest()
            ico_path = os.path.join(IconStore.ICON_CACHE_PATH, sha1)
            
            # read from icon cache
            if self.use_icon_cache and os.path.exists(ico_path):
                ico = open(ico_path, "rb").read()
            else:
                ico = None
            
            # Icon image get from web
            for i in range(3):
                if ico: break
                if self._die: return
                
                try:
                    ico = urllib2.urlopen(user.profile_image_url).read()
                except Exception, e:
                    ico = None
                    print >>sys.stderr, "[Error] %d: Icon %s" % (i, e)
                    time.sleep(3)
                    continue
                
                if self.use_icon_cache and ico:
                    try:
                        # save to icon cache
                        self.save_icon_cache(ico, ico_path)
                    except Exception, e:
                        print >>sys.stderr, "[Error] %d: IconCache %s" % (i, e)
                
                break
            
            # Get pixbuf
            icopix = self.convert_pixbuf(ico)
            
            if icopix == None:
                print >>sys.stderr, "[warning] Can't convert icon image: %s" % (
                    user.screen_name)
            else:
                # Add iconstore
                self.icons[user.profile_image_url] = icopix
                
                # Icon Refresh
                for store, n in self.stores:
                    for row in store:
                        if self._die: return
                        
                        # replace icon to all user's status
                        if row[n] == user.id:
                            gtk.gdk.threads_enter()
                            store[row.path][0] = icopix
                            gtk.gdk.threads_leave()
                            # FIXME: slow magic???
                            store.row_changed(row.path, store.get_iter(row.path))
    
    # create pixbuf
    def load_pixbuf(self, ico):
        loader = gtk.gdk.PixbufLoader()
        
        try:
            loader.write(ico)
            pix = loader.get_pixbuf()
            loader.close()
        except:
            pix = None
        
        if pix and pix.get_width() > 48:
            pix = pix.scale_simple(48, 48, gtk.gdk.INTERP_BILINEAR)
        
        return pix
    
    def convert_pixbuf(self, ico):
        if ico == None: return None
        if USE_PIL:
            # use Python Imaging Library if exists
            pix = self.load_pixbuf(ico) or self.convert_pixbuf_pil(ico)
        else:
            pix = self.load_pixbuf(ico)
        
        return pix
    
    # Convert Pixbuf with PIL
    def convert_pixbuf_pil(self, ico):
        i = cStringIO.StringIO(ico)
        o = cStringIO.StringIO()
        
        try:
            self.create_thumbnail(ico, i, o)
            pix = self.load_pixbuf(o.getvalue())
            
            # fix for win32
            if not pix:
                i.seek(0)
                o.seek(0)
                o.truncate()
                self.create_thumbnail(ico, i, o, "PPM")
                pix = self.load_pixbuf(o.getvalue())
        except Exception, e:
            pix = None
        finally:
            i.close()
            o.close()
        
        return pix
    
    # Try convert PIL, if installed Python Imaging Library
    def create_thumbnail(self, img, i, o, filetype = "BMP"):
        pimg = Image.open(i)
        pimg.thumbnail((48, 48), Image.ANTIALIAS)
        pimg = pimg.convert("RGB")
        pimg.save(o, filetype)
    
    # save icon thumbnail to filesystem cache
    def save_icon_cache(self, ico, ico_path):
        open(ico_path, "wb").write(ico)
        
        if USE_PIL: 
            ico = Image.open(ico_path)
            if ico.size != (48, 48):
                ico.thumbnail((48, 48), Image.ANTIALIAS)
                ico.save(ico_path, "PNG")
    
    def stop(self):
        self._die = True
