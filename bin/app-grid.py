#!/usr/bin/env python3
import os
import sys

# Force X11 backend for GDK so window positioning/centering works reliably under Wayland/XWayland
os.environ["GDK_BACKEND"] = "x11"
os.environ["DISPLAY"] = ":0"

import subprocess
import re
import glob
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

PID_FILE = "/tmp/app-grid.pid"

class AppGrid(Gtk.Window):
    def __init__(self):
        super().__init__(title="App Grid")
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        
        # Support transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            
        self.set_app_paintable(False)
        
        # Set exact size matching the original rofi theme
        self.width = 820
        self.height = 540
        self.set_default_size(self.width, self.height)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Load and parse apps
        self.all_apps = self.get_apps()
        self.filtered_apps = list(self.all_apps)
        
        # Pagination state
        self.items_per_page = 15  # 5x3 grid
        self.current_page = 0
        self.selected_index = 0  # Index on the current page
        
        # CSS Styling
        self.style_provider = Gtk.CssProvider()
        css = b"""
        window, window.background {
            background-color: rgba(18, 18, 20, 0.9);
            border: 2px solid #820014;
            border-radius: 16px;
        }
        .main-box {
            padding: 25px;
        }
        entry {
            background-color: #1a1a1f;
            border: 2px solid rgba(255, 255, 255, 0.15);
            border-radius: 24px;
            color: #f7f7f7;
            padding: 10px 20px;
            font-family: 'Noto Sans Mono', monospace;
            font-size: 11pt;
            margin-bottom: 10px;
        }
        entry:focus {
            border-color: #820014;
        }
        .grid-box {
            margin: 15px 0px;
        }
        .app-item {
            padding: 12px 6px;
            border-radius: 12px;
            background-color: transparent;
        }
        .app-item:hover, .app-item.selected {
            background-color: #820014;
        }
        .app-label {
            color: #f7f7f7;
            font-family: 'Noto Sans', sans-serif;
            font-size: 12pt;
            margin-top: 8px;
        }
        .app-item.selected .app-label {
            color: #ffffff;
            font-weight: bold;
        }
        .footer-box {
            margin-top: 10px;
        }
        .dot {
            color: rgba(255, 255, 255, 0.25);
            font-size: 16pt;
            margin: 0px 6px;
        }
        .dot.active {
            color: #820014;
        }
        .page-label {
            color: rgba(255, 255, 255, 0.6);
            font-family: 'Noto Sans Mono', monospace;
            font-size: 9pt;
            margin-left: 15px;
        }
        """
        self.style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # --- UI Build ---
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.get_style_context().add_class("main-box")
        self.add(main_box)
        
        # 1. Search Box
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Type to search...")
        self.search_entry.connect("changed", self.on_search_changed)
        main_box.pack_start(self.search_entry, False, False, 0)
        
        # 2. App Grid (5 columns, 3 rows)
        self.grid = Gtk.Grid()
        self.grid.set_column_spacing(15)
        self.grid.set_row_spacing(15)
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        self.grid.get_style_context().add_class("grid-box")
        main_box.pack_start(self.grid, True, True, 0)
        
        # Create the grid items once and reuse them
        self.grid_widgets = []
        for row in range(3):
            for col in range(5):
                eb = Gtk.EventBox()
                eb.get_style_context().add_class("app-item")
                eb.set_visible_window(True)
                
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                eb.add(box)
                
                img = Gtk.Image()
                box.pack_start(img, True, True, 0)
                
                lbl = Gtk.Label()
                lbl.get_style_context().add_class("app-label")
                lbl.set_line_wrap(True)
                lbl.set_max_width_chars(14)
                lbl.set_alignment(0.5, 0.5)
                box.pack_start(lbl, False, False, 0)
                
                # Connect mouse events
                eb.connect("button-press-event", self.on_item_clicked, len(self.grid_widgets))
                
                self.grid.attach(eb, col, row, 1, 1)
                self.grid_widgets.append((eb, img, lbl))
                
        # 3. Footer (Pagination Dots & Label)
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer_box.get_style_context().add_class("footer-box")
        footer_box.set_center_widget(None) # Clear default center
        
        # Center container for dots
        self.dots_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        footer_box.set_center_widget(self.dots_box)
        
        # Page info label on the right
        self.page_label = Gtk.Label()
        self.page_label.get_style_context().add_class("page-label")
        footer_box.pack_end(self.page_label, False, False, 0)
        
        main_box.pack_start(footer_box, False, False, 0)
        
        # Event connections
        self.connect("destroy", self.on_destroy)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("key-press-event", self.on_key_press)
        self.connect("scroll-event", self.on_scroll)
        
        # Initial Render
        self.update_grid()
        self.show_all()
        self.present()

    # --- App Parsing ---
    def get_apps(self):
        apps = []
        seen = set()
        dirs = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications")
        ]
        for d in dirs:
            if not os.path.exists(d):
                continue
            for path in glob.glob(os.path.join(d, "*.desktop")):
                fname = os.path.basename(path)
                if fname in seen:
                    continue
                seen.add(fname)
                
                try:
                    name = None
                    icon = None
                    exec_cmd = None
                    no_display = False
                    is_application = True
                    
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        in_entry = False
                        for line in f:
                            line = line.strip()
                            if line == "[Desktop Entry]":
                                in_entry = True
                                continue
                            elif line.startswith("[") and line.endswith("]"):
                                in_entry = False
                                
                            if in_entry and "=" in line:
                                key, val = line.split("=", 1)
                                key = key.strip()
                                val = val.strip()
                                
                                if key == "Name":
                                    name = val
                                elif key == "Icon":
                                    icon = val
                                elif key == "Exec":
                                    exec_cmd = val
                                elif key == "NoDisplay":
                                    no_display = (val.lower() == "true")
                                elif key == "Type":
                                    is_application = (val.lower() == "application")
                                    
                    if name and exec_cmd and not no_display and is_application:
                        # Strip Exec flags
                        exec_clean = re.sub(r'%[fFuUiDdknmNv]', '', exec_cmd).strip()
                        apps.append({
                            "name": name,
                            "icon": icon or "application-x-executable",
                            "exec": exec_clean
                        })
                except Exception:
                    pass
                    
        # Sort alphabetically
        apps.sort(key=lambda x: x["name"].lower())
        return apps

    # --- Render / Grid Refresh ---
    def update_grid(self):
        # Calculate pagination
        total_items = len(self.filtered_apps)
        total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
        
        # Boundaries check
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
        if self.current_page < 0:
            self.current_page = 0
            
        page_start = self.current_page * self.items_per_page
        page_end = page_start + self.items_per_page
        page_apps = self.filtered_apps[page_start:page_end]
        
        # Ensure selected index is within bounds of current page items
        if self.selected_index >= len(page_apps):
            self.selected_index = max(0, len(page_apps) - 1)
            
        # Draw items in the grid
        for idx, (eb, img, lbl) in enumerate(self.grid_widgets):
            # Clear selection styling
            eb.get_style_context().remove_class("selected")
            
            if idx < len(page_apps):
                app = page_apps[idx]
                lbl.set_text(app["name"])
                
                # Load icon
                self.load_app_icon(img, app["icon"])
                
                # Enable interaction
                eb.set_sensitive(True)
                
                # Apply selection style
                if idx == self.selected_index:
                    eb.get_style_context().add_class("selected")
                    
                eb.show_all()
            else:
                # Keep the widget in the grid so layout is preserved, but clear it and disable interaction
                lbl.set_text("")
                img.clear()
                eb.set_sensitive(False)
                eb.show_all()
                
        # Update pagination dots
        for child in self.dots_box.get_children():
            self.dots_box.remove(child)
            
        # Only show dots if there are multiple pages
        if total_pages > 1:
            for p in range(total_pages):
                dot = Gtk.Label(label="●")
                dot.get_style_context().add_class("dot")
                if p == self.current_page:
                    dot.get_style_context().add_class("active")
                self.dots_box.pack_start(dot, False, False, 0)
            self.dots_box.show_all()
            
        # Update page label
        self.page_label.set_text(f"Page {self.current_page + 1} of {total_pages}")

    def load_app_icon(self, img_widget, icon_name):
        try:
            # Check if icon_name is an absolute file path
            if os.path.isabs(icon_name) and os.path.exists(icon_name):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_name, 64, 64, True)
                img_widget.set_from_pixbuf(pixbuf)
                return
                
            icon_theme = Gtk.IconTheme.get_default()
            if icon_theme.has_icon(icon_name):
                img_widget.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
                # Ensure dialog icon fits around 64px
                return
                
            # Try parsing extension-less absolute paths or default back
            test_path = os.path.join("/usr/share/pixmaps", icon_name)
            if os.path.exists(test_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(test_path, 64, 64, True)
                img_widget.set_from_buf(pixbuf)
                return
                
            # Default fallback
            img_widget.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        except Exception:
            img_widget.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)

    # --- Interaction Events ---
    def on_search_changed(self, entry):
        query = entry.get_text().lower().strip()
        if query:
            self.filtered_apps = [a for a in self.all_apps if query in a["name"].lower()]
        else:
            self.filtered_apps = list(self.all_apps)
            
        self.current_page = 0
        self.selected_index = 0
        self.update_grid()

    def on_item_clicked(self, widget, event, idx):
        page_start = self.current_page * self.items_per_page
        app_idx = page_start + idx
        if app_idx < len(self.filtered_apps):
            self.launch_app(self.filtered_apps[app_idx])
        return True

    def launch_selected(self):
        page_start = self.current_page * self.items_per_page
        app_idx = page_start + self.selected_index
        if app_idx < len(self.filtered_apps):
            self.launch_app(self.filtered_apps[app_idx])

    def launch_app(self, app):
        try:
            # Launch asynchronously
            subprocess.Popen(app["exec"], shell=True, start_new_session=True)
        except Exception:
            pass
        self.destroy()

    def next_page(self):
        total_items = len(self.filtered_apps)
        total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.selected_index = 0
            self.update_grid()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.selected_index = 0
            self.update_grid()

    # --- Key and Mouse Navigation ---
    def on_key_press(self, widget, event):
        keyval = event.keyval
        
        # Escape closes window
        if keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
            
        # Enter launches selected application
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.launch_selected()
            return True
            
        # Get count of current visible apps
        page_start = self.current_page * self.items_per_page
        page_end = page_start + self.items_per_page
        page_apps = self.filtered_apps[page_start:page_end]
        num_apps = len(page_apps)
        
        if num_apps == 0:
            return False
            
        if keyval == Gdk.KEY_Right:
            col = self.selected_index % 5
            row = self.selected_index // 5
            
            if col == 4:
                # Last column: try to go to next page, same row
                total_items = len(self.filtered_apps)
                total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                    next_page_start = self.current_page * self.items_per_page
                    next_page_apps = self.filtered_apps[next_page_start : next_page_start + self.items_per_page]
                    target_idx = row * 5
                    self.selected_index = min(target_idx, len(next_page_apps) - 1)
                    self.update_grid()
            else:
                new_idx = self.selected_index + 1
                if new_idx < num_apps:
                    self.selected_index = new_idx
                    self.update_grid()
            return True
            
        elif keyval == Gdk.KEY_Left:
            col = self.selected_index % 5
            row = self.selected_index // 5
            
            if col == 0:
                # First column: try to go to previous page, same row
                if self.current_page > 0:
                    self.current_page -= 1
                    prev_page_start = self.current_page * self.items_per_page
                    prev_page_apps = self.filtered_apps[prev_page_start : prev_page_start + self.items_per_page]
                    target_idx = row * 5 + 4
                    self.selected_index = min(target_idx, len(prev_page_apps) - 1)
                    self.update_grid()
            else:
                new_idx = self.selected_index - 1
                if new_idx >= 0:
                    self.selected_index = new_idx
                    self.update_grid()
            return True
            
        elif keyval == Gdk.KEY_Down:
            new_idx = self.selected_index + 5
            if new_idx < num_apps:
                self.selected_index = new_idx
                self.update_grid()
            else:
                # Wrap within same column if possible or go to next page
                pass
            return True
            
        elif keyval == Gdk.KEY_Up:
            new_idx = self.selected_index - 5
            if new_idx >= 0:
                self.selected_index = new_idx
                self.update_grid()
            return True
            
        elif keyval == Gdk.KEY_Page_Down:
            self.next_page()
            return True
            
        elif keyval == Gdk.KEY_Page_Up:
            self.prev_page()
            return True
            
        # Redirect typing directly to the search entry if not focused
        if not self.search_entry.is_focus():
            self.search_entry.grab_focus_without_selecting()
            # Feed key event to entry
            self.search_entry.event(event)
            return True
            
        return False

    def on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.DOWN:
            self.next_page()
        elif event.direction == Gdk.ScrollDirection.UP:
            self.prev_page()
        return True

    def on_focus_out(self, widget, event):
        self.destroy()
        return True

    def on_destroy(self, widget):
        try:
            if os.path.exists(PID_FILE):
                with open(PID_FILE, "r") as f:
                    saved_pid = int(f.read().strip())
                if saved_pid == os.getpid():
                    os.remove(PID_FILE)
        except Exception:
            pass
        Gtk.main_quit()

if __name__ == "__main__":
    mypid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            os.kill(old_pid, 15) # SIGTERM
            sys.exit(0)
        except (ValueError, OSError, IOError):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
                
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(mypid))
    except Exception:
        pass
        
    AppGrid()
    Gtk.main()
