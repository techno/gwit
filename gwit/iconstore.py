#!/usr/bin/env python
#-*- coding: utf-8 -*-

import pygtk
pygtk.require('2.0')
import gtk

import sys
import threading
import urllib2
import cStringIO
import time
import os.path

try:
    import Image
except ImportError:
    USE_PIL = False
else:
    USE_PIL = True

# User Icon Store
class IconStore:
    def __init__(self, iconmode = True):
        self.iconmode = iconmode
        self.data = dict()
        self.stores = list()
        self.semaphore = threading.BoundedSemaphore(5)
        
        # load default icon
        iconpath = os.path.join(os.path.dirname(__file__), "img/none.png")
        self.default_icon = gtk.gdk.pixbuf_new_from_file(iconpath)
    
    def get(self, user):
        if user.id in self.data:
            # if exist in cache
            return self.data[user.id]
        elif self.iconmode:
            # or get new icon
            self.new(user)
        
        # Return Default Image
        return self.default_icon
    
    def new(self, user):
        # New Icon thread start if iconmode is True
        self.data[user.id] = self.default_icon
        newico = NewIcon(user, self.stores, self.data, self.semaphore)
        newico.start()
    
    def add_store(self, store, n):
        self.stores.append((store, n))

    def remove_store(self, store):
        for i in self.stores:
            if store == i[0]:
                self.stores.remove(i)

class NewIcon(threading.Thread):
    def __init__(self, user, stores, icons, semaphore):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.setName("icon:%s" % user.screen_name)
        
        self.user = user
        self.stores = stores
        self.icons = icons
        self.semaphore = semaphore

    # create pixbuf
    def load_pixbuf(self, ico):
        loader = gtk.gdk.PixbufLoader()
        loader.write(ico)
        pix = loader.get_pixbuf()
        
        try: loader.close()
        except: pix = None
        
        return pix
    
    def convert_pixbuf(self, ico):
        if USE_PIL:
            # use Python Imaging Library if exists
            pix = self.convert_pixbuf_pil(ico)    
        else:
            pix = self.load_pixbuf(ico)
            if pix != None:
                pix = pix.scale_simple(48, 48, gtk.gdk.INTERP_BILINEAR)
        
        return pix
    
    # Convert Pixbuf with PIL
    def convert_pixbuf_pil(self, ico):
        i = cStringIO.StringIO(ico)
        o = cStringIO.StringIO()
        
        self.create_thumbnail(ico, i, o)
        pix = self.load_pixbuf(o.getvalue())
        
        i.close()
        o.close()
        
        return pix
    
    # Try convert PIL, if installed Python Imaging Library
    def create_thumbnail(self, img, i, o):
        pimg = Image.open(i)
        thumb = pimg.resize((48, 48))
        
        ext = self.user.profile_image_url[-3:]        
        if ext == "jpg":
            thumb = thumb.convert("RGB")
        
        thumb.save(o, "png")
    
    def run(self):
        # Icon Data Get (if can get semaphore or block)
        self.semaphore.acquire()
        for i in range(3):
            try:
                ico = urllib2.urlopen(self.user.profile_image_url).read()
                break
            except:
                ico = None
                print >>sys.stderr, "[Error] %d: IconStore %s" % (i, e)
        self.semaphore.release()
        
        # Get pixbuf
        icopix = self.convert_pixbuf(ico)
        
        if icopix == None:
            print >>sys.stderr, "[warning] Can't convert icon image: %s" % self.user.screen_name
            return
        
        # Add iconstore
        self.icons[self.user.id] = icopix
        
        # delay for replace icons (temporary bug fix...
        time.sleep(1)
        
        # Icon Refresh
        for store, n in self.stores:
            i = store.get_iter_first()
            while i:
                uid = store.get_value(i, n)
                if uid == self.user.id:
                    gtk.gdk.threads_enter()
                    store.set_value(i, 0, icopix)
                    gtk.gdk.threads_leave()
                i = store.iter_next(i)
