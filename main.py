#!/usr/bin/env python
#-*- coding: utf-8 -*-

import pygtk
pygtk.require('2.0')
import gtk

from objects import GtkObjects
from twitterapi import twitterapi

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
    
    def main(self):
        # Twitter class instance
        self.twitter = twitterapi(keys)
        # Set Event Hander (exec in every get home_timeline
        self.twitter.EventHandler = self.refresh
        # Twitter class thread start
        self.twitter.start()
        
        # Start gtk main loop
        self.obj.window1.show_all()
        gtk.gdk.threads_init()
        gtk.main()
    
    # Refresh TreeView
    def refresh(self, *args):
        gtk.gdk.threads_enter()
        for i in self.twitter.home:
            self.obj.liststore1.append(
                (i.user.screen_name, i.text))
        gtk.gdk.threads_leave()
    
    # Window close event
    def close(self, widget):
        gtk.main_quit()

if __name__ == "__main__":
    execfile("config")
    gladefile = "gwit.glade"
    gwit = Main(gladefile)
    gwit.main()
