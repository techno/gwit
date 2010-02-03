#!/usr/bin/env python
#-*- coding: utf-8 -*-

import pygtk
pygtk.require('2.0')
import gtk

from objects import GtkObjects
from twitterapi import twitterapi
from statusview import statusview

# Main Class
class Main:
    # Constractor
    def __init__(self, glade):
        # GtkBuilder instance
        builder = gtk.Builder()
        # Glade file input
        builder.add_from_file(glade)
        # Connect signals
        builder.connect_signals(self)
        
        # GtkObjects instance
        # usage: self.obj.`objectname`
        # ex) self.obj.button1
        self.obj = GtkObjects(builder.get_objects())

        # Setting TreeView Column
        cr_txt = gtk.CellRendererText()
        tcol = list()
        tcol.append(
            gtk.TreeViewColumn("Name", cr_txt, text = 0))
        tcol.append(
            gtk.TreeViewColumn("Text", cr_txt, text = 1))

        # Add Column
        for i in tcol:
            self.obj.treeview1.append_column(i)
        
        # Auto scroll to top setup
        vadj = self.obj.scrolledwindow1.get_vadjustment()
        vadj.connect("changed", self.vadj_changed)
        self.vadj_upper = vadj.get_upper()

        mentions = statusview()
        mentions.add(self.obj.notebook1, "Mentions")
    
    def main(self, keys):
        # Twitter class instance
        self.twitter = twitterapi(keys)
        # Set Event Hander (exec in every get home_timeline
        self.twitter.EventHandler = self.refresh
        
        self.obj.window1.show_all()
        
        # Gtk Multithread Setup
        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        # Twitter class thread start
        self.twitter.start()
        # Start gtk main loop
        gtk.main()
        gtk.gdk.threads_leave()
    
    # Refresh TreeView
    def refresh(self, *args):
        gtk.gdk.threads_enter()
        
        # Insert New Status
        for i in self.twitter.home:
            self.obj.liststore1.prepend(
                (i.user.screen_name, i.text))
        
        gtk.gdk.threads_leave()
    
    # Window close event
    def close(self, widget):
        gtk.main_quit()
    
    def vadj_changed(self, adj):
        # Scroll to top if upper(list length) changed
        if self.vadj_upper < adj.get_upper():
            self.vadj_upper = adj.get_upper()
            adj.set_value(0)

    # Status Update
    def on_button1_clicked(self, widget):
        txt = self.get_text()
        if self.re == 1:
            self.twitter.api.status_update(
                txt, in_reply_to_status_id = None)
            self.clear_buf()
            self.re = 0
        else:
            self.twitter.api.status_update(txt)
            self.clear_buf()

    # Reply
    def on_treeview1_row_activated(self, treeview, path, view_column):
        self.re = 1
        path_name = self.obj.liststore1[path]
        buf = self.obj.textview1.get_buffer()
        buf.set_text("@%s " %(path_name[0]))

    # Get text
    def get_text(self):
        buf = self.obj.textview1.get_buffer()
        start, end = buf.get_start_iter(), buf.get_end_iter()
        return  buf.get_text(start, end)

    # Clear Buf
    def clear_buf(self):
        buf = self.obj.textview1.get_buffer()
        buf.set_text("")
