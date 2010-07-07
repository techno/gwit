#!/usr/bin/env python
#-*- coding: utf-8 -*-

import pygtk
pygtk.require('2.0')
import gtk
import gobject

class ListsView(gtk.ScrolledWindow):
    def __init__(self, user, memberships = False):
        gtk.ScrolledWindow.__init__(self)
        self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        
        self.store = gtk.ListStore(gtk.gdk.Pixbuf, str, gobject.TYPE_INT64, gobject.TYPE_INT64)
        self.treeview = gtk.TreeView(self.store)
        self.treeview.set_headers_visible(False)
        self.treeview.connect("row-activated", self.on_treeview_row_activated)
        
        self.treeview.append_column(
            gtk.TreeViewColumn("Icon", gtk.CellRendererPixbuf(), pixbuf = 0))
        self.treeview.append_column(
            gtk.TreeViewColumn("Lists", gtk.CellRendererText(), text = 1))
        
        self.btn_more = gtk.Button("Get your lists!")
        self.btn_more.connect("clicked", self.on_button_more_clicked)
        
        vbox = gtk.VBox()
        vbox.pack_start(self.treeview, expand = False)
        vbox.pack_start(self.btn_more, expand = False)
        self.add_with_viewport(vbox)
        
        self.user = user
        self.memberships = memberships
        
        self.lists = dict()
        self._cursor = -1
        self.twitter = None
    
    def set_twitterapi(self, api, icons):
        self.twitter = api
        self.icons = icons
        self.icons.add_store(self.store, 2)
    
    # Load Lists index
    def load(self):
        if self.memberships:
            data = self.twitter.api.lists_memberships(self.user, cursor = self._cursor)
        else:
            data = self.twitter.api.lists_subscriptions(self.user, cursor = self._cursor)
        
        for l in data["lists"]:
            user = l["user"]
            userid = int(user["id"])
            screen_name = user["screen_name"]

            listid = int(l["id"])
            listname = l["name"]
            
            self.twitter.add_user(user)
            self.lists[listid] = l
            self.store.append(
                (self.icons.get(l["user"]), "@%s/%s" % (screen_name, listname), userid, listid))
        
        self._cursor = int(data["next_cursor"])
        
        if self._cursor == 0:
            self.btn_more.set_sensitive(False)
            self.btn_more.hide()
        else:
            self.btn_more.set_label("Get more 20 lists.")        
    
    # for override
    def new_timeline(self, label, method, sleep, *args, **kwargs):
        pass
    
    
    ### Event
    def on_button_more_clicked(self, widget):
        self.load()
    
    def on_treeview_row_activated(self, treeview, path, view_column):
        listid = treeview.get_model()[path][3]
        listlabel = treeview.get_model()[path][1]
        l = self.lists[listid]
        self.new_timeline("L: %s" % listlabel, "lists_statuses", -1,
                          list_id = l["name"], user = l["user"]["screen_name"])

class ListsSelection(gtk.Notebook):
    def __init__(self, twitter, icons):
        gtk.Notebook.__init__(self)
        self.twitter = twitter
        self.icons = icons
        
        sub = ListsView(self.twitter.myname, False)
        mem = ListsView(self.twitter.myname, True)
        
        sub.set_twitterapi(self.twitter, self.icons)
        sub.new_timeline = self.new_timeline_wrap
        mem.set_twitterapi(self.twitter, self.icons)
        mem.new_timeline = self.new_timeline_wrap
        
        self.append_page(sub, gtk.Label("Subscriptions"))
        self.append_page(mem, gtk.Label("Memberships"))
    
    def new_timeline_wrap(self, *args, **kwargs):
        self.new_timeline(*args, **kwargs)
    
    # for override
    def new_timeline(self, *args, **kwargs): pass
