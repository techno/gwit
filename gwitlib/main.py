#-*- coding: utf-8 -*-

'''gwit Main class
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
import gobject
import pango

import sys
import os.path
import threading
import random
import time
import uuid
import webbrowser

try:
    import pynotify
except ImportError:
    USE_NOTIFY = False
else:
    USE_NOTIFY = True

from timeline import Timeline
from statusview import StatusView
from timelinethread import BaseThread
from twitterapi import TwitterAPI
from iconstore import IconStore, IconThread
from saveconfig import Config
from userselection import UserSelection
from listsselection import ListsSelection, ListsView
from statusdetail import StatusDetail
from twittertools import TwitterTools
from getfriendswizard import GetFriendsWizard

# Main Class
class Main(object):
    # Default settings
    interval = (300, 300, -1)
    msgfooter = u""
    alloc = gtk.gdk.Rectangle(0, 0, 240, 320)
    scounts = (20, 200)
    iconmode = True
    iconcache = True
    userstream = True
    # My status, Mentions to me, Reply to, Reply to user, Selected user
    status_color = ("#CCCCFF", "#FFCCCC", "#FFCC99", "#FFFFCC", "#CCFFCC")
    
    # Tweet parameters
    twparams = dict()
    
    # Streaming API filter
    _filter_tab = None
    
    _toggle_change_flag = False
    _text_delete_flag = False
    
    # Constractor
    def __init__(self, screen_name, keys):
        # Gtk Multithread Setup
        if sys.platform == "win32":
            gobject.threads_init()
        else:
            gtk.gdk.threads_init()
        
        if USE_NOTIFY:
            pynotify.init("gwit")
        
        # force change gtk icon settings
        settings = gtk.settings_get_default()
        if not getattr(settings.props, 'gtk_button_images', True):
            settings.props.gtk_button_images = True
        
        # init status timelines
        self.timelines = list()
        self.tlhash = dict()
        self.timeline_mention = None
        
        # Twitter class instance
        self.twitter = TwitterAPI(screen_name, *keys)
        self.twitter.on_tweet_event = self.refresh_tweet
        self.twitter.on_notify_event = self.notify
        
        self.read_settings()
        
        # set event (show remaining api count)
        self.twitter.on_twitterapi_requested = self.on_timeline_refresh
        self.twitter.new_timeline = self.new_timeline
        
        # Get configuration
        self.twitter.update_configuration_bg()
        
        # Get users
        self.twitter.get_followers_bg()
        if not self.userstream: self.twitter.get_following_bg()
        
        # init icon store
        IconStore.iconmode = self.iconmode
        self.iconstore = IconStore()
        
        # GtkBuilder instance
        self.builder = gtk.Builder()
        # Glade file input
        gladefile = os.path.join(os.path.dirname(__file__), "ui/gwit.ui")
        self.builder.add_from_file(gladefile)
        # Connect signals
        self.builder.connect_signals(self)
        
        self.notebook = self.builder.get_object("notebook1")
        self.textview = self.builder.get_object("textview1")
        self.btnupdate = self.builder.get_object("button1")
        self.charcount = self.builder.get_object("label1")
        self.dsettings = self.builder.get_object("dialog_settings")
        self.imgtable = self.builder.get_object("table_images")
        
        self.menu_tweet = self.builder.get_object("menu_tweet")
        self.builder.get_object("menuitem_tweet").set_submenu(self.menu_tweet)
        self.menu_timeline = self.builder.get_object("menu_timeline")
        self.builder.get_object("menuitem_timeline").set_submenu(
            self.menu_timeline)
        
        # set class variables
        Timeline.twitter = self.twitter
        StatusView.twitter = self.twitter
        StatusView.iconstore = self.iconstore
        StatusView.iconmode = self.iconmode
        StatusView.pmenu = self.menu_tweet
        BaseThread.twitter = self.twitter
        StatusDetail.twitter = self.twitter
        StatusDetail.iconstore = self.iconstore
        ListsView.twitter = self.twitter
        ListsView.iconstore = self.iconstore
        UserSelection.twitter = self.twitter
        UserSelection.iconstore = self.iconstore
        GetFriendsWizard.twitter = self.twitter
        IconThread.twitter = self.twitter
        IconThread.use_icon_cache = self.iconcache
        
        imgpath = os.path.join(os.path.dirname(__file__), "images/")
        StatusView.favico_off = gtk.gdk.pixbuf_new_from_file(
            imgpath + "favorite.png")
        StatusView.favico_hover = gtk.gdk.pixbuf_new_from_file(
            imgpath + "favorite_hover.png")
        StatusView.favico_on = gtk.gdk.pixbuf_new_from_file(
            imgpath + "favorite_on.png")

        StatusView.rtico_off = gtk.gdk.pixbuf_new_from_file(
            imgpath + "retweet.png")
        StatusView.rtico_hover = gtk.gdk.pixbuf_new_from_file(
            imgpath + "retweet_hover.png")
        StatusView.rtico_on = gtk.gdk.pixbuf_new_from_file(
            imgpath + "retweet_on.png")
        
        self.initialize()
    
    def main(self):
        window = self.builder.get_object("window1")
        
        # settings allocation
        window.resize(self.alloc.width, self.alloc.height)        
        window.show_all()
        
        # Start gtk main loop
        gtk.main()
    
    def read_settings(self):
        # Read settings
        d = Config.get_section("DEFAULT")
        self.interval = eval(d.get("interval", str(self.interval)))
        self.alloc = eval(d.get("allocation", str(self.alloc)))
        self.scounts = eval(d.get("counts", str(self.scounts)))
        self.iconmode = eval(d.get("iconmode", str(self.iconmode)))
        self.iconcache = eval(d.get("iconcache", str(self.iconcache)))
        self.userstream = eval(d.get("userstream", str(self.userstream)))
        self.status_color = eval(d.get("color", str(self.status_color)))
        u = Config.get_section(self.twitter.my_name)
        self.msgfooter = u.get("footer", "")
    
    # Initialize Tabs (in another thread)
    def initialize(self):
        # Set Status Views
        for i in (("Home", "home_timeline", self.userstream),
                  ("@Mentions", "mentions")):
            # create new timeline and tab view
            deny_close = {"deny_close" : True}
            self.new_timeline(*i, **deny_close)
        
        # Set statusbar (Show API Remaining)
        self.label_apilimit = gtk.Label()
        self.statusbar = self.builder.get_object("statusbar1")
        self.statusbar.pack_start(self.label_apilimit,
                                  expand = False, padding = 10)
        self.statusbar.show_all()
        
        # Users tab append
        users = UserSelection()
        self.new_tab(users, "Users", deny_close = True)
        
        # Lists tab append
        lists = ListsSelection()
        self.new_tab(lists, "Lists", deny_close = True)
        
        self.notebook.set_current_page(0)
    
    # Window close event
    def close(self, widget):
        window = self.builder.get_object("window1")

        # Save Allocation (window position, size)
        alloc = repr(window.allocation)
        Config.save("DEFAULT", "allocation", alloc)
        
        # hide window
        window.hide_all()
        
        # Stop Icon Refresh
        self.iconstore.stop()
    
    def exit(self, widget):
        # hide window quickly
        while gtk.events_pending():
            gtk.main_iteration()
        
        # Stop Timeline
        for i in self.timelines:
            if i != None:
                i.destroy()
                if i.timeline != None: i.timeline.join(1)
                if i.stream != None: i.stream.join(1)
        
        gtk.main_quit()
        self.save_settings()
    
    # Create new Timeline and append to notebook
    def new_timeline(self, label, method, userstream = False, *args, **kwargs):
        # Create Timeline Object
        tl = Timeline()
        
        if method == "filter":
            if self.get_filter_tab():
                # filter method only one connection
                self.message_dialog(
                    "May create only one standing connection to the Streaming API.\n"
                    "Please close existing Streaming API tab if you want.")
                tl.destroy()
                return
            
            # set Streaming API stream
            tl.set_stream("filter", kwargs)
        else:
            interval = self.get_default_interval(method)        
            tl.set_timeline(method, interval, self.scounts, args, kwargs)
            # Put error to statubar
            tl.timeline.on_twitterapi_error = self.on_twitterapi_error
        
        # for Event
        tl.view.new_timeline = self.new_timeline
        
        # Add Notebook (Tab view)
        uid = self.new_tab(tl, label, tl, kwargs.get("deny_close", False))
        if method == "filter": self.set_filter_tab(uid)
        
        # Set color
        tl.view.set_color(self.status_color)
        
        if method == "mentions":
            # memory mentions tab_id
            self.timeline_mention = uid
            tl.on_status_added = self.on_mentions_added
        else:
            tl.on_status_added = self.on_status_added
        
        # Put tweet information to statusbar
        tl.view.on_status_selection_changed = self.on_status_selection_changed
        # Reply on double click
        tl.view.on_status_activated = self.on_status_activated
       
        # Set UserStream parameter
        if userstream:
            tl.set_stream("user")
        
        tl.start_stream()
        tl.start_timeline()
    
    # Append Tab to Notebook
    def new_tab(self, widget, label, timeline = None, deny_close = False):
        # close button
        button = gtk.Button()
        button.set_relief(gtk.RELIEF_NONE)
        icon = gtk.image_new_from_stock("gtk-close", gtk.ICON_SIZE_MENU)
        button.set_image(icon)
        
        uid = uuid.uuid4().int
        button.connect("clicked", self.on_tabclose_clicked, uid)
        n = self.notebook.get_n_pages()
        self.tlhash[uid] = n
        self.timelines.append(timeline)
        
        # Label
        lbl = gtk.Label(label)
        
        box = gtk.HBox()
        box.pack_start(lbl, True, True)
        if not deny_close:
            box.pack_start(button, False, False)
        box.show_all()
        
        if timeline != None:
            button.connect("button-press-event", 
                           self.on_notebook_tabbar_button_press)
        
        # append
        self.notebook.append_page(widget, box)
        self.notebook.show_all()
        self.notebook.set_current_page(n)
        
        return uid
    
    def get_selected_status(self):
        tab = self.get_current_tab()
        if tab != None:
            return tab.view.get_selected_status()
    
    def get_current_tab_n(self):
        return self.notebook.get_current_page()
    
    def get_current_tab(self):
        return self.timelines[self.notebook.get_current_page()]
    
    # Get text
    def get_textview(self):
        buf = self.textview.get_buffer()
        start, end = buf.get_start_iter(), buf.get_end_iter()
        return buf.get_text(start, end)
    
    # Set text
    def set_textview(self, txt, focus = False):
        buf = self.textview.get_buffer()
        buf.set_text(txt)
        if focus: self.textview.grab_focus()
    
    # Add text at cursor
    def add_textview(self, txt, focus = False):
        buf = self.textview.get_buffer()
        buf.insert_at_cursor(txt)    
        if focus: self.textview.grab_focus()
    
    # Clear text
    def clear_textview(self, focus = False):
        self.set_textview("", focus)
    
    # Reply to selected status
    def reply_to_selected_status(self):
        status = self.get_selected_status()
        self.reply_to_status(status)
    
    def reply_to_status(self, status):
        self.twparams["reply_to"] = status.id
        name = status.user.screen_name
        
        buf = self.textview.get_buffer()
        buf.set_text("@%s " % (name))
        self.textview.grab_focus()
    
    # Color selection dialog run for settings
    def color_dialog_run(self, title, color, entry):
        # Sample treeview setup
        store = gtk.ListStore(gtk.gdk.Pixbuf, str, str)
        treeview = gtk.TreeView(store)
        cellp = gtk.CellRendererPixbuf()
        colp = gtk.TreeViewColumn("icon", cellp, pixbuf = 0)
        cellt = gtk.CellRendererText()
        cellt.set_property("wrap-mode", pango.WRAP_CHAR)
        colt = gtk.TreeViewColumn("status", cellt, markup = 1)
        colp.add_attribute(cellp, "cell-background", 2)
        colt.add_attribute(cellt, "cell-background", 2)
        treeview.append_column(colp)
        treeview.append_column(colt)
        
        status = self.twitter.statuses.values()[0]
        store.append((self.iconstore.get(status.user),
                      "<b>%s</b>\n%s" % (status.user.screen_name, status.text),
                      color))
        
        def on_changed_cursor(view):
            view.get_selection().unselect_all()
        
        treeview.set_property("can-focus", False)
        treeview.set_headers_visible(False)
        treeview.connect("cursor-changed", on_changed_cursor)
        treeview.show()
        
        swin = gtk.ScrolledWindow()
        swin.add(treeview)
        swin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        swin.show()
        
        label = gtk.Label("Sample")
        label.set_justify(gtk.JUSTIFY_LEFT)
        label.set_padding(0, 10)
        label.set_alignment(0, 0.5)
        label.show()
        
        def on_colorselection_color_changed(colorselection, liststore):
            strcolor = colorselection.get_current_color().to_string()
            liststore.set_value(liststore.get_iter_first(), 2, strcolor)
        
        # Dialog setup
        dialog = gtk.ColorSelectionDialog(title)
        selection = dialog.get_color_selection()
        selection.set_current_color(gtk.gdk.color_parse(color))
        selection.connect("color-changed", 
                          on_colorselection_color_changed, store)
        
        selection.pack_start(label)
        selection.pack_start(swin)
        
        dialog.show_all()
        
        if dialog.run() == -5:
            color = selection.get_current_color().to_string()
            entry.set_text(color)
        else:
            color = None
        
        dialog.destroy()
        
        return color
    
    def status_update_thread(self, status):
        t = threading.Thread(target = self._status_update, args = (status,))
        t.start()
    
    def _status_update(self, status):
        args = dict()
        
        gtk.gdk.threads_enter()
        self.textview.set_sensitive(False)
        self.btnupdate.set_sensitive(False)
        gtk.gdk.threads_leave()
        
        if self.twparams.get("reply_to", None):
            args["in_reply_to_status_id"] = self.twparams.get("reply_to", None)
        elif self.msgfooter != "":
            status = u"%s %s" % (status, self.msgfooter)
        
        if self.twparams.get("media", None):            
            resp = self.twitter.api_wrapper(
                self.twitter.api.status_update_with_media,
                status, self.twparams["media"], **args)
        else:
            resp = self.twitter.api_wrapper(
                self.twitter.api.status_update, status, **args)
        
        if resp:
            gtk.gdk.threads_enter()
            self.clear_textview()
            gtk.gdk.threads_leave()
            self.twparams.pop("reply_to", None)
            self.twparams.pop("media", None)
            self.imgtable.forall(self.imgtable.remove)
            self.imgtable.set_visible(False)
        
        gtk.gdk.threads_enter()
        self.textview.set_sensitive(True)
        self.btnupdate.set_sensitive(True)
        self.textview.grab_focus()
        gtk.gdk.threads_leave()
    
    def get_default_interval(self, method):
        if method == "home_timeline":
            interval = self.interval[0]
        elif method == "mentions":
            interval = self.interval[1]
        else:
            interval = self.interval[2]

        return interval
    
    def get_filter_tab(self):
        if not self._filter_tab:
            return None
        elif self.tlhash.get(self._filter_tab, -1) < 0:
            # filter tab already closed
            self.set_filter_tab(None)
            return None
        else:
            return self._filter_tab
    
    @classmethod
    def set_filter_tab(cls, tab_id):
        cls._filter_tab = tab_id
    
    def save_settings(self):
        conf = (("DEFAULT", "interval", self.interval),
                ("DEFAULT", "counts", self.scounts),
                ("DEFAULT", "iconmode", self.iconmode),
                ("DEFAULT", "iconcache", self.iconcache),
                ("DEFAULT", "userstream", self.userstream),
                ("DEFAULT", "color", self.status_color),
                (self.twitter.my_name, "footer", self.msgfooter))
        Config.save_section(conf)

    # desktop notify
    def notify(self, title, text, icon_user = None):
        if USE_NOTIFY:
            notify = pynotify.Notification(title, text)
            if icon_user:
                icon = self.iconstore.get(icon_user)
                notify.set_icon_from_pixbuf(icon)
            notify.show()
    
    def refresh_tweet(self, i):
        for tl in self.timelines:
            if tl: tl.view.reset_status_text()
    
    def message_dialog(self, message, 
                       type = gtk.MESSAGE_ERROR,
                       buttons = gtk.BUTTONS_OK):
        md = gtk.MessageDialog(type = type, buttons = buttons)
        md.set_markup(message)
        r = md.run()
        md.destroy()
        return r
    
    
    ########################################
    # Original Events
    
    # status added event
    def on_status_added(self, i):
        status = self.twitter.statuses[i]
        myid = self.twitter.my_id
        myname = self.twitter.my_name
        
        if status.in_reply_to_user_id == myid or status.text.find("@%s" % myname) >= 0:
            # add mentions tab
            mentiontab = self.timelines[self.tlhash[self.timeline_mention]]
            if status.id not in mentiontab.get_timeline_ids():
                mentiontab.timeline.add_statuses(((status,)))
    
    def on_mentions_added(self, i):
        status = self.twitter.statuses[i]
        self.notify("@%s mentioned you." % status.user.screen_name,
                    status.text, status.user)
    
    # timeline refreshed event
    def on_timeline_refresh(self):
        if self.twitter.api.ratelimit_iplimit != -1:
            msg = "%d/%d %d/%d" % (
                self.twitter.api.ratelimit_remaining,
                self.twitter.api.ratelimit_limit,
                self.twitter.api.ratelimit_ipremaining,
                self.twitter.api.ratelimit_iplimit)
        else:
            msg = "%d/%d" % (
                self.twitter.api.ratelimit_remaining,
                self.twitter.api.ratelimit_limit)
        
        try:
            self.label_apilimit.set_text("API: %s" % msg)
        except:
            pass
    
    # status selection changed event
    def on_status_selection_changed(self, status):
        self.builder.get_object("menuitem_tweet").set_sensitive(True)
        self.statusbar.pop(0)
        self.statusbar.push(0, TwitterTools.get_footer(status))
    
    # status activated event (to Reply
    def on_status_activated(self, status):
        self.reply_to_status(status)
    
    # show error on statusbar
    def on_twitterapi_error(self, timeline, e):
        if e.code == 400:
            message = "API rate limiting. Reset: %s" % (
                self.twitter.api.ratelimit_reset.strftime("%H:%M:%S"))
        elif e.code == 500 or e.code == 502:
            message = "Twitter something is broken. Try again later."
        elif e.code == 503:
            message = "Twitter is over capacity. Try again later."
        else:
            message = "Oops! Couldn't reload timeline."
        
        self.statusbar.pop(0)        
        self.statusbar.push(0, "[Error] %s %s (%s)" % (
                timeline.getName(), message, e.code))
    
    ########################################
    # Gtk Signal Events
    
    # Status Update
    def on_button1_clicked(self, widget):
        txt = self.get_textview()
        
        if txt != "":
            # Status Update
            self.status_update_thread(txt)
        else:
            # Reload timeline if nothing in textview
            n = self.get_current_tab_n()
            self.twparams.pop("reply_to", None)
            if self.timelines[n] != None:
                self.timelines[n].reload()
    
    # key_press textview (for update status when press Ctrl + Enter)
    def on_textview1_key_press_event(self, textview, event):
        # Enter == 65293
        if event.keyval == 65293 and event.state & gtk.gdk.CONTROL_MASK:
            txt = self.get_textview()
            
            # if update button enabled (== len(text) <= 140
            if self.btnupdate.get_sensitive() and txt != "":
                self.status_update_thread(txt)
            
            return True
    
    # Update menu popup
    def on_button2_button_release_event(self, widget, event):
        menu = self.builder.get_object("menu_update")
        menu.popup(None, None, None, event.button, event.time)
    
    # Add an image to tweet
    def on_menuitem_add_image_activate(self, widget):
        dialog = gtk.FileChooserDialog("Add an image...")
        dialog.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        ret = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        
        if ret == gtk.RESPONSE_OK:
            media = self.twparams.setdefault("media", list())
            
            # duplicate image?
            if filename in media:
                self.message_dialog("Duplicate image.")
                return
            
            # max_media_per_upload check
            max_media = self.twitter.configuration.get("max_media_per_upload",
                                                       1)
            if len(media) >= max_media:
                self.message_dialog(
                    "You can upload max %d images per upload." % max_media)
                return
            
            # ext check
            ext = os.path.splitext(filename)[1].upper()
            if ext not in [".JPG", ".JPEG", ".PNG", ".GIF"]:
                self.message_dialog(
                    "File is not Image. Only JPG, PNG and GIF.")
                return
            
            # filesize check
            fsize = os.stat(filename).st_size
            limit = self.twitter.configuration.get("photo_size_limit", 3145728)
            if fsize > limit:
                self.message_dialog(
                    "Image file size must be less than %d KB." % (
                        limit / 1024))
                return
            
            pix = gtk.gdk.pixbuf_new_from_file(filename)
            ratio = float(pix.get_height()) / float(pix.get_width())
            pix = pix.scale_simple(120, int(ratio * 120), 
                                   gtk.gdk.INTERP_BILINEAR)
            
            img = gtk.Image()
            img.set_from_pixbuf(pix)
            box = gtk.EventBox()
            box.add(img)         
            box.connect("button-release-event",
                        self.on_image_button_release, len(media))
            
            # add new row
            if len(media) % 4 == 0:
                self.imgtable.resize(len(media) / 4 + 1, 4)
            
            # attach image
            self.imgtable.attach(
                box, len(media) % 4, len(media) % 4 + 1,
                len(media) / 4, len(media) / 4 + 1,
                xoptions = gtk.SHRINK, yoptions = gtk.SHRINK,
                xpadding = 0, ypadding = 10)
            
            cursor = gtk.gdk.Cursor(gtk.gdk.HAND1)
            box.window.set_cursor(cursor)
            
            self.imgtable.set_visible(True)
            self.imgtable.show_all()
            
            # add params
            media.append(filename)
    
    def on_image_button_release(self, widget, event, media_num):
        if event.button == 1:
            # image clicked
            if sys.platform == "win32":
                os.startfile(self.twparams["media"][media_num])
            else:
                os.system("xdg-open %s" % self.twparams["media"][media_num])
        elif event.button == 3:
            # image delete
            r = self.message_dialog(
                "Are you sure you want to delete this image?",
                gtk.MESSAGE_QUESTION, gtk.BUTTONS_YES_NO)
            if r == gtk.RESPONSE_YES:
                self.imgtable.remove(widget)
                del self.twparams["media"][media_num]
                if self.twparams["media"]:
                    self.imgtable.set_visible(False)
    
    # Timeline Tab Close
    def on_tabclose_clicked(self, widget, uid):
        n = self.tlhash[uid]
        del self.tlhash[uid]

        if self.timeline_mention == uid:
            self.timeline_mention = None
        
        self.notebook.remove_page(n)
        
        if self.timelines[n] != None:
            self.timelines[n].destroy()
        
        del self.timelines[n]
        
        for i, m in self.tlhash.iteritems():
            if m > n: self.tlhash[i] -= 1
        
        p = self.notebook.get_current_page()
        self.on_notebook1_switch_page(
            self.notebook, self.notebook.get_nth_page(p), p)
    
    # Tab right clicked
    def on_notebook_tabbar_button_press(self, widget, event):
        if event.button == 3:
            self.menu_timeline.popup(
                None, None, None, event.button, event.time)
    
    # Character count
    def on_textbuffer1_changed(self, buf):
        text = self.get_textview().decode("utf-8")
        
        # reply to user suggesstions
        cursor = buf.get_property("cursor-position")
        rspace = text.rfind(" ", 0, cursor)
        rat = text.rfind("@", 0, cursor)
        rhash = text.rfind("#", 0, cursor)
        
        prefix = postfix = None
        
        # is reply?
        if rat == 0 or (rspace > 0 and rat > rspace):
            prefix = text[rat + 1:cursor]
            users = self.twitter.get_users_startswith(prefix)
            if users:
                users.sort(key = lambda u: u.screen_name)
                postfix = users[0].screen_name[len(prefix):]
        
        # is hash?
        if rhash == 0 or (rspace > 0 and rhash > rspace):
            prefix = text[rhash + 1:cursor]
            hashtags = [h for h in self.twitter.hashtags if h.startswith(prefix)]
            if hashtags:
                hashtags.sort()
                postfix = hashtags[0][len(prefix):]
        
        # clear old suggesstions
        if buf.get_has_selection():
            buf.delete_selection(True, True)
            self._text_delete_flag = False
        
        # print screen_name suggesstions
        if prefix and postfix and not self._text_delete_flag:
            cursor_iter = buf.get_iter_at_mark(buf.get_insert())
            buf.insert_at_cursor(postfix)
            buf.select_range(buf.get_iter_at_offset(cursor),
                             buf.get_iter_at_mark(buf.get_insert()))
        
        self._text_delete_flag = False
        
        # add footer
        if self.msgfooter != "" and self.twparams.get("reply_to", None):
            text = u"%s %s" % (text, self.msgfooter)
        
        # calculate tweet length
        n = TwitterTools.get_tweet_length(
            text, len(self.twparams.get("media", [])),
            self.twitter.configuration.get("short_url_length", 20),
            self.twitter.configuration.get("short_url_length_https", 20),
            self.twitter.configuration.get("characters_reserved_per_media", 20)
            )
        
        if n <= 140:
            self.charcount.set_text(str(n))
            self.btnupdate.set_sensitive(True)
        else:
            self.charcount.set_markup(
                "<b><span foreground='#FF0000'>%s</span></b>" % n)
            self.btnupdate.set_sensitive(False)
    
    def on_textbuffer1_delete_range(self, buf, start, end):
        self._text_delete_flag = True
    
    # Help - About menu
    def on_menuitem_about_activate(self, menuitem):
        self.builder.get_object("dialog_about").show_all()
        return True
    
    # About dialog closed
    def on_dialog_about_response(self, dialog, response_id):
        dialog.hide_all()
    
    # disable menu when switched tab
    def on_notebook1_switch_page(self, notebook, page, page_num):
        self.builder.get_object("menuitem_tweet").set_sensitive(False)
        menuitem_timeline = self.builder.get_object("menuitem_timeline")
        menuitem_timeline.set_sensitive(False)
        if page_num < 0: return False
        
        tab = self.timelines[page_num]
        if tab != None and tab.timeline != None:
            self._toggle_change_flg = True
            tl = tab.timeline
            method = tl.method
            default = self.get_default_interval(method)
            
            if default == -1: default = None
            
            menu_default = self.builder.get_object("menuitem_time_default")
            menu_default.get_child().set_text("Default (%s)" % default)
            
            interval = tl.interval
            
            if interval == default:
                menu_default.set_active(True)
            elif interval == -1:
                self.builder.get_object("menuitem_time_none").set_active(True)
            elif interval == 600:
                self.builder.get_object("menuitem_time_600").set_active(True)
            elif interval == 300:
                self.builder.get_object("menuitem_time_300").set_active(True)
            elif interval == 120:
                self.builder.get_object("menuitem_time_120").set_active(True)
            elif interval == 60:
                self.builder.get_object("menuitem_time_60").set_active(True)
            elif interval == 30:
                self.builder.get_object("menuitem_time_30").set_active(True)
            
            self._toggle_change_flg = False
            menuitem_timeline.set_sensitive(True)
    
    # Streaming API tab
    def on_menuitem_streaming_activate(self, menuitem):
        dialog = gtk.MessageDialog(buttons = gtk.BUTTONS_OK)
        dialog.set_markup("Please enter track keywords.")
        dialog.format_secondary_markup(
            "Examples: <i>hashtag, username, keyword</i>\n(Split comma. Unnecessary #, @)")
        entry = gtk.Entry()
        dialog.vbox.pack_start(entry)
        dialog.show_all()
        dialog.run()
        text = entry.get_text().decode("utf-8")
        dialog.destroy()
        
        params = {"track" : text.split(",")}
        self.new_timeline("Stream: %s" % text, "filter", **params)
    
    def on_destroy(self, widget, *args, **kwargs):
        widget.destroy()
    
    ########################################
    # Tweet menu event
    
    def on_menuitem_reply_activate(self, menuitem):
        self.reply_to_selected_status()
    
    # Retweet menu clicked
    def on_menuitem_retweet_activate(self, memuitem):
        self.get_current_tab().view.retweet_selected_status()
    
    # Retweet with comment menu clicked
    def on_menuitem_reteet_with_comment_activate(self, memuitem):
        status = self.get_selected_status()
        name = status.user.screen_name
        text = status.text
        
        self.twparams.pop("reply_to", None)
        self.set_textview("RT @%s: %s" % (name, text), True)
    
    # Added user timeline tab
    def on_menuitem_usertl_activate(self, menuitem):
        status = self.get_selected_status()
        self.new_timeline("@%s" % status.user.screen_name,
                          "user_timeline", user = status.user.id)
    
    # view conversation
    def on_menuitem_detail_activate(self, menuitem):
        status = self.get_selected_status()
        detail = StatusDetail(status)
        self.new_tab(detail, "%s: %s..." % (
                status.user.screen_name, status.text[:10]))
    
    # favorite
    def on_menuitem_fav_activate(self, menuitem):
        self.get_current_tab().view.favorite_selected_status()
    
    # Destroy status
    def on_menuitem_destroy_activate(self, menuitem):
        status = self.get_selected_status()
        self.twitter.destory_tweet(status)
    
    # view on twitter.com
    def on_menuitem_ontwitter_activate(self, menuitem):
        status = self.get_selected_status()
        url = "https://twitter.com/%s/status/%s" % (
            status.user.screen_name, status.id)
        webbrowser.open_new_tab(url)
    
    ########################################
    # Timeline menu Event
    
    def change_interval(self, interval):
        if self._toggle_change_flg: return
        
        tl = self.get_current_tab().timeline
        
        if interval == 0:
            method = tl.api_method.func_name
            interval = self.get_default_interval(method)
        
        old = tl.interval
        tl.interval = interval
        if old == -1: tl.lock.set()
    
    def on_menuitem_time_600_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(600) 
    def on_menuitem_time_300_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(300)
    def on_menuitem_time_120_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(120)
    def on_menuitem_time_60_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(60)
    def on_menuitem_time_30_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(30)
    def on_menuitem_time_default_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(0)
    def on_menuitem_time_none_toggled(self, menuitem):
        if menuitem.get_active() == True:
            self.change_interval(-1)
    
    ########################################
    # Settings dialog event
    
    # Settings
    def on_imageitem_settings_activate(self, menuitem):
        home, mentions, other = self.interval
        
        # interval
        if home == -1:
            self.builder.get_object("checkbutton_home").set_active(False)
        if mentions == -1:
            self.builder.get_object("checkbutton_mentions").set_active(False)
        if other == -1:
            self.builder.get_object("checkbutton_other").set_active(False)        
        self.builder.get_object("spinbutton_home").set_value(home)
        self.builder.get_object("spinbutton_mentions").set_value(mentions)
        self.builder.get_object("spinbutton_other").set_value(other)
        
        # status counts
        self.builder.get_object("spinbutton_firstn").set_value(self.scounts[0])
        self.builder.get_object("spinbutton_maxn").set_value(self.scounts[1])
        # show icons
        self.builder.get_object("checkbutton_showicon").set_active(self.iconmode)
        # icon cache
        self.builder.get_object("checkbutton_iconcache").set_active(self.iconcache)
        # userstream
        self.builder.get_object("checkbutton_userstream").set_active(self.userstream)
        
        # footer
        self.builder.get_object("entry_footer").set_text(self.msgfooter)

        # OAuth information
        self.builder.get_object("entry_myname").set_text(self.twitter.my_name)
        self.builder.get_object("entry_ckey").set_text(self.twitter.api.oauth.ckey)
        self.builder.get_object("entry_csecret").set_text(self.twitter.api.oauth.csecret)
        self.builder.get_object("entry_atoken").set_text(self.twitter.api.oauth.atoken)
        self.builder.get_object("entry_asecret").set_text(self.twitter.api.oauth.asecret)
        
        # Color
        color_entrys = (self.builder.get_object("entry_color_mytweet"),
                        self.builder.get_object("entry_color_mentions"),
                        self.builder.get_object("entry_color_replyto"),
                        self.builder.get_object("entry_color_replyto_user"),
                        self.builder.get_object("entry_color_selected_user"))
        for i, entry in enumerate(color_entrys):
            entry.set_text(self.status_color[i])
        
        self.dsettings.show()
    
    # Close or Cancel
    def on_dialog_settings_close(self, widget):
        self.dsettings.hide()
    
    # OK
    def on_dialog_settings_ok(self, widget):
        # interval
        if self.builder.get_object("checkbutton_home").get_active():
            home = self.builder.get_object("spinbutton_home").get_value_as_int()
        else:
            self.charcount.set_markup("<b><span foreground='#FF0000'>%s</span></b>" % n)
            self.btnupdate.set_sensitive(False)
            home = -1
        if self.builder.get_object("checkbutton_mentions").get_active():
            mentions = self.builder.get_object("spinbutton_mentions").get_value_as_int()
        else:
            mentions = -1
        if self.builder.get_object("checkbutton_other").get_active():
            other = self.builder.get_object("spinbutton_other").get_value_as_int()
        else:
            other = -1

        self.interval = (home, mentions, other)
        
        # status counts
        self.scounts = (
            self.builder.get_object("spinbutton_firstn").get_value_as_int(),
            self.builder.get_object("spinbutton_maxn").get_value_as_int())
        
        # show icons
        self.iconmode = self.builder.get_object("checkbutton_showicon").get_active()
        
        # icon cache
        self.iconcache = self.builder.get_object("checkbutton_iconcache").get_active()
        
        # userstream
        self.userstream = self.builder.get_object("checkbutton_userstream").get_active()
        
        # footer
        self.msgfooter = unicode(self.builder.get_object("entry_footer").get_text())
        
        # Color
        self.status_color = (self.builder.get_object("entry_color_mytweet").get_text(),
                             self.builder.get_object("entry_color_mentions").get_text(),
                             self.builder.get_object("entry_color_replyto").get_text(),
                             self.builder.get_object("entry_color_replyto_user").get_text(),
                             self.builder.get_object("entry_color_selected_user").get_text())
        for t in self.timelines:
            if t != None:
                t.view.set_color(self.status_color)
        
        self.save_settings()
        self.dsettings.hide()
    
    # toggle checkbox
    def on_checkbutton_home_toggled(self, checkbutton):
        sb = self.builder.get_object("spinbutton_home")
        sb.set_sensitive(checkbutton.get_active())
    def on_checkbutton_mentions_toggled(self, checkbutton):
        sb = self.builder.get_object("spinbutton_mentions")
        sb.set_sensitive(checkbutton.get_active())
    def on_checkbutton_other_toggled(self, checkbutton):
        sb = self.builder.get_object("spinbutton_other")
        sb.set_sensitive(checkbutton.get_active())
    
    def on_entry_color_changed(self, entry):
        entry.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse(entry.get_text()))
    
    # Color selection dialog open    
    def on_button_color1_clicked(self, widget):
        entry = self.builder.get_object("entry_color_mytweet")
        self.color_dialog_run("My status", entry.get_text(), entry)
    def on_button_color2_clicked(self, widget):
        entry = self.builder.get_object("entry_color_mentions")
        self.color_dialog_run("Mentions to me", entry.get_text(), entry)
    def on_button_color3_clicked(self, widget):
        entry = self.builder.get_object("entry_color_replyto")
        self.color_dialog_run("Reply to", entry.get_text(), entry)
    def on_button_color4_clicked(self, widget):
        entry = self.builder.get_object("entry_color_replyto_user")
        self.color_dialog_run("Reply to user", entry.get_text(), entry)
    def on_button_color5_clicked(self, widget):
        entry = self.builder.get_object("entry_color_selected_user")
        self.color_dialog_run("Selected user", entry.get_text(), entry)
