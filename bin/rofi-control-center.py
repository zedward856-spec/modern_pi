#!/usr/bin/env python3
import os
import sys

# Force X11 backend for GDK so client-side window positioning works under Wayland/XWayland
os.environ["GDK_BACKEND"] = "x11"
os.environ["DISPLAY"] = ":0"

import subprocess
import re
import signal
import atexit
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

PID_FILE = "/tmp/rofi-control-center.pid"

class ControlCenterApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Control Center")
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)  # Hide from the taskbar!
        self.set_skip_pager_hint(True)    # Hide from pager window switcher lists!
        
        # Support transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            
        self.set_app_paintable(False)
        
        # Set size
        self.width = 380
        self.height = 320
        self.set_default_size(self.width, self.height)
        
        # Connect size-allocate signal for dynamic positioning in the bottom-right corner
        self.connect("size-allocate", self.on_size_allocate)
        
        # Style sheet (CSS)
        self.style_provider = Gtk.CssProvider()
        css = b"""
        window, window.background {
            background-color: rgba(130, 0, 20, 0.9);
            border: 2px solid #820014;
            border-radius: 16px;
        }
        .main-box {
            padding: 15px;
        }
        label {
            color: #f7f7f7;
            font-family: 'Noto Sans Mono', 'DejaVu Sans Mono', monospace;
            font-size: 10pt;
        }
        .header-label {
            font-weight: bold;
            font-size: 11pt;
        }
        .tile-box {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 10px;
        }
        button {
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            color: #f7f7f7;
            padding: 6px 12px;
            font-family: 'Noto Sans Mono', monospace;
        }
        button:hover {
            background-color: #820014;
            border-color: #820014;
        }
        scale trough {
            background-color: #2b2b2b;
            border-radius: 5px;
            min-height: 10px;
        }
        scale highlight {
            background-color: #820014;
            border-radius: 5px;
        }
        scale slider {
            background-color: #ffffff;
            border: 2px solid #820014;
            border-radius: 50%;
            min-width: 16px;
            min-height: 16px;
            margin: -3px 0px;
        }
        combobox button {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #f7f7f7;
        }
        """
        self.style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Main Container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.get_style_context().add_class("main-box")
        self.add(main_box)
        
        # 1. Row 1: Wi-Fi Quick Toggle & Selector
        wifi_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        wifi_box.get_style_context().add_class("tile-box")
        
        wifi_icon = Gtk.Image.new_from_icon_name("network-wireless", Gtk.IconSize.BUTTON)
        wifi_box.pack_start(wifi_icon, False, False, 0)
        
        self.wifi_btn = Gtk.Button(label="Wi-Fi: Scanning...")
        self.wifi_btn.connect("clicked", self.on_wifi_toggle)
        wifi_box.pack_start(self.wifi_btn, True, True, 0)
        
        self.wifi_combo = Gtk.ComboBoxText()
        self.wifi_combo.connect("changed", self.on_wifi_select)
        wifi_box.pack_start(self.wifi_combo, False, False, 0)
        
        main_box.pack_start(wifi_box, False, False, 0)
        
        # 2. Row 2: Network Speed & Data Usage Stats (Wi-Fi Dashboard directly below Wi-Fi Part)
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        stats_box.get_style_context().add_class("tile-box")
        
        self.stats_label = Gtk.Label(label="Down: 0 B/s | Up: 0 B/s | Usage: 0.00 GB")
        stats_box.pack_start(self.stats_label, True, True, 0)
        
        main_box.pack_start(stats_box, False, False, 0)
        
        # 3. Row 3: Bluetooth & Power Actions
        bt_power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        bt_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bt_box.get_style_context().add_class("tile-box")
        bt_icon = Gtk.Image.new_from_icon_name("bluetooth", Gtk.IconSize.BUTTON)
        bt_box.pack_start(bt_icon, False, False, 0)
        self.bt_btn = Gtk.Button(label="Bluetooth")
        self.bt_btn.connect("clicked", self.on_bt_toggle)
        bt_box.pack_start(self.bt_btn, True, True, 0)
        bt_power_box.pack_start(bt_box, True, True, 0)
        
        power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        power_box.get_style_context().add_class("tile-box")
        power_icon = Gtk.Image.new_from_icon_name("system-shutdown", Gtk.IconSize.BUTTON)
        power_box.pack_start(power_icon, False, False, 0)
        self.power_btn = Gtk.Button(label="Power")
        self.power_btn.connect("clicked", self.on_power_menu)
        power_box.pack_start(self.power_btn, True, True, 0)
        bt_power_box.pack_start(power_box, True, True, 0)
        
        main_box.pack_start(bt_power_box, False, False, 0)
        
        # 4. Row 4: Embedded Volume Slider (kept at the bottom)
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vol_box.get_style_context().add_class("tile-box")
        
        self.vol_icon = Gtk.Image()
        vol_box.pack_start(self.vol_icon, False, False, 0)
        
        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.connect("value-changed", self.on_volume_changed)
        vol_box.pack_start(self.vol_scale, True, True, 0)
        
        self.vol_label = Gtk.Label(label="Vol: N/A")
        vol_box.pack_start(self.vol_label, False, False, 0)
        
        main_box.pack_start(vol_box, False, False, 0)
        
        # 5. Row 5: Lock Screen & Close Actions
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        lock_btn = Gtk.Button(label="🔒 Lock Screen")
        lock_btn.connect("clicked", self.on_lock_screen)
        action_box.pack_start(lock_btn, True, True, 0)
        
        close_btn = Gtk.Button(label="Exit")
        close_btn.connect("clicked", lambda b: self.destroy())
        action_box.pack_start(close_btn, True, True, 0)
        
        main_box.pack_start(action_box, False, False, 0)
        
        # Initial updates
        self.update_volume_slider()
        self.update_bluetooth_status()
        self.update_wifi_status()
        
        # Start background threads
        self.active_threads = True
        self.stats_thread = threading.Thread(target=self.bg_stats_update, daemon=True)
        self.stats_thread.start()
        
        self.scan_thread = threading.Thread(target=self.bg_wifi_scan, daemon=True)
        self.scan_thread.start()
        
        # Signal bindings
        self.connect("destroy", self.on_destroy)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("key-press-event", self.on_key_press)
        
        self.show_all()
        self.present()

    def run_cmd(self, args):
        try:
            res = subprocess.run(args, capture_output=True, text=True)
            return res.stdout.strip()
        except Exception:
            return ""

    # --- Volume Logic ---
    def update_volume_slider(self):
        try:
            out = self.run_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
            if "[MUTED]" in out:
                self.vol_scale.set_value(0)
                self.vol_label.set_text("Mute")
                self.vol_icon.set_from_icon_name("audio-volume-muted", Gtk.IconSize.BUTTON)
                return
            match = re.search(r"Volume:\s*([0-9.]+)", out)
            if match:
                vol = int(float(match.group(1)) * 100)
                self.vol_scale.handler_block_by_func(self.on_volume_changed)
                self.vol_scale.set_value(vol)
                self.vol_scale.handler_unblock_by_func(self.on_volume_changed)
                
                self.vol_label.set_text(f"{vol}%")
                if vol == 0:
                    icon = "audio-volume-muted"
                elif vol < 30:
                    icon = "audio-volume-low"
                elif vol < 70:
                    icon = "audio-volume-medium"
                else:
                    icon = "audio-volume-high"
                self.vol_icon.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
        except Exception:
            pass

    def on_volume_changed(self, scale):
        val = int(scale.get_value())
        self.vol_label.set_text(f"{val}%" if val > 0 else "Mute")
        
        if val == 0:
            self.vol_icon.set_from_icon_name("audio-volume-muted", Gtk.IconSize.BUTTON)
        elif val < 30:
            self.vol_icon.set_from_icon_name("audio-volume-low", Gtk.IconSize.BUTTON)
        elif val < 70:
            self.vol_icon.set_from_icon_name("audio-volume-medium", Gtk.IconSize.BUTTON)
        else:
            self.vol_icon.set_from_icon_name("audio-volume-high", Gtk.IconSize.BUTTON)
            
        try:
            if val == 0:
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
            else:
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val/100.0:.2f}"])
        except Exception:
            pass

    # --- Bluetooth Logic ---
    def update_bluetooth_status(self):
        state = self.run_cmd(["bluetoothctl", "show"])
        if "Powered: yes" in state:
            self.bt_btn.set_label("BT: Enabled")
        else:
            self.bt_btn.set_label("BT: Disabled")

    def on_bt_toggle(self, btn):
        state = self.run_cmd(["bluetoothctl", "show"])
        if "Powered: yes" in state:
            self.run_cmd(["bluetoothctl", "power", "off"])
            self.run_cmd(["sudo", "/usr/sbin/rfkill", "block", "bluetooth"])
        else:
            self.run_cmd(["sudo", "/usr/sbin/rfkill", "unblock", "bluetooth"])
            self.run_cmd(["sudo", "hciconfig", "hci0", "up"])
            self.run_cmd(["bluetoothctl", "power", "on"])
        self.update_bluetooth_status()

    # --- Wi-Fi Logic ---
    def update_wifi_status(self):
        wifi_state = self.run_cmd(["nmcli", "-t", "-f", "WIFI", "g"])
        if wifi_state != "enabled":
            self.wifi_btn.set_label("Wi-Fi: Disabled")
            self.wifi_combo.set_sensitive(False)
            return
            
        self.wifi_combo.set_sensitive(True)
        ssid_out = self.run_cmd(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
        connected_ssid = None
        for line in ssid_out.splitlines():
            if line.startswith("yes:"):
                connected_ssid = line.split(":", 1)[1]
                break
                
        if connected_ssid:
            self.wifi_btn.set_label(f"Wi-Fi: {connected_ssid}")
        else:
            self.wifi_btn.set_label("Wi-Fi: Disconnected")

    def on_wifi_toggle(self, btn):
        wifi_state = self.run_cmd(["nmcli", "-t", "-f", "WIFI", "g"])
        if wifi_state == "enabled":
            self.run_cmd(["nmcli", "radio", "wifi", "off"])
        else:
            self.run_cmd(["nmcli", "radio", "wifi", "on"])
        self.update_wifi_status()

    def bg_wifi_scan(self):
        while self.active_threads:
            wifi_state = self.run_cmd(["nmcli", "-t", "-f", "WIFI", "g"])
            if wifi_state == "enabled":
                out = self.run_cmd(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi"])
                networks = []
                seen_ssids = set()
                for line in out.splitlines():
                    if not line.strip():
                        continue
                    parts = line.rsplit(':', 3)
                    if len(parts) == 4:
                        ssid, signal, security, active = parts
                        ssid = ssid.replace('\\:', ':')
                        if not ssid or ssid in seen_ssids:
                            continue
                        seen_ssids.add(ssid)
                        networks.append({
                            "ssid": ssid,
                            "signal": int(signal) if signal.isdigit() else 0,
                            "security": security,
                            "active": active == "yes"
                        })
                GLib.idle_add(self.update_wifi_combo, networks)
            time.sleep(10)

    def update_wifi_combo(self, networks):
        self.wifi_networks = networks
        self.wifi_combo.handler_block_by_func(self.on_wifi_select)
        self.wifi_combo.remove_all()
        
        self.wifi_combo.append_text("Select Network...")
        
        active_index = 0
        for idx, net in enumerate(networks, start=1):
            sec_str = " 🔒" if net["security"] and net["security"] != "--" else ""
            status_str = f"{net['ssid']} ({net['signal']}%{sec_str})"
            if net["active"]:
                status_str += " (Connected)"
                active_index = idx
            self.wifi_combo.append_text(status_str)
            
        self.wifi_combo.set_active(active_index)
        self.wifi_combo.handler_unblock_by_func(self.on_wifi_select)

    def on_wifi_select(self, combo):
        active_idx = combo.get_active()
        if active_idx <= 0:
            return
            
        selected_net = self.wifi_networks[active_idx - 1]
        if selected_net["active"]:
            return
            
        requires_pass = selected_net["security"] and selected_net["security"] != "--"
        password = ""
        if requires_pass:
            password = self.prompt_password_dialog(selected_net["ssid"])
            if password is None:
                return
                
        threading.Thread(
            target=self.connect_wifi_worker,
            args=(selected_net["ssid"], password),
            daemon=True
        ).start()

    def prompt_password_dialog(self, ssid):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Password for {ssid}"
        )
        dialog.set_keep_above(True)
        dialog.set_decorated(False)
        dialog.get_style_context().add_provider(
            self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        entry = Gtk.Entry()
        entry.set_visibility(False)
        entry.set_activates_default(True)
        
        box = dialog.get_message_area()
        box.pack_start(entry, True, True, 10)
        dialog.show_all()
        
        response = dialog.run()
        password = entry.get_text() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        return password

    def connect_wifi_worker(self, ssid, password):
        if password:
            res = self.run_cmd(["nmcli", "dev", "wifi", "connect", ssid, "password", password])
        else:
            res = self.run_cmd(["nmcli", "dev", "wifi", "connect", ssid])
        GLib.idle_add(self.update_wifi_status)

    # --- BG Traffic Stats Logic ---
    def bg_stats_update(self):
        while self.active_threads:
            try:
                with open("/sys/class/net/wlan0/statistics/rx_bytes", "r") as f:
                    rx1 = int(f.read().strip())
                with open("/sys/class/net/wlan0/statistics/tx_bytes", "r") as f:
                    tx1 = int(f.read().strip())
                    
                time.sleep(1.0)
                
                with open("/sys/class/net/wlan0/statistics/rx_bytes", "r") as f:
                    rx2 = int(f.read().strip())
                with open("/sys/class/net/wlan0/statistics/tx_bytes", "r") as f:
                    tx2 = int(f.read().strip())
                    
                down_speed = rx2 - rx1
                up_speed = tx2 - tx1
                usage = (rx2 + tx2) / (1024 * 1024 * 1024)
                
                def format_speed(speed_bytes):
                    if speed_bytes < 1024:
                        return f"{speed_bytes} B/s"
                    elif speed_bytes < 1024 * 1024:
                        return f"{speed_bytes / 1024:.1f} KB/s"
                    else:
                        return f"{speed_bytes / (1024 * 1024):.1f} MB/s"
                        
                stats_str = f"Down: {format_speed(down_speed)} | Up: {format_speed(up_speed)} | Usage: {usage:.2f} GB"
                GLib.idle_add(self.stats_label.set_text, stats_str)
            except Exception:
                time.sleep(1.0)

    # --- Actions ---
    def on_lock_screen(self, btn):
        subprocess.Popen(["swaylock", "-p"])
        self.destroy()

    def on_power_menu(self, btn):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Power Actions"
        )
        dialog.set_keep_above(True)
        dialog.set_decorated(False)
        dialog.get_style_context().add_provider(
            self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        box = dialog.get_message_area()
        
        reboot_btn = Gtk.Button(label="🔄 Reboot")
        reboot_btn.connect("clicked", lambda b: subprocess.run(["systemctl", "reboot"]))
        box.pack_start(reboot_btn, True, True, 5)
        
        shutdown_btn = Gtk.Button(label=" Shutdown")
        shutdown_btn.connect("clicked", lambda b: subprocess.run(["systemctl", "poweroff"]))
        box.pack_start(shutdown_btn, True, True, 5)
        
        logout_btn = Gtk.Button(label="👤 Log Out")
        logout_btn.connect("clicked", lambda b: subprocess.run(["pkill", "-u", "sl01220"]))
        box.pack_start(logout_btn, True, True, 5)
        
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        box.pack_start(cancel_btn, True, True, 5)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_size_allocate(self, widget, allocation):
        screen = self.get_screen()
        screen_width = screen.get_width()
        screen_height = screen.get_height()
        x = screen_width - allocation.width - 12
        y = screen_height - allocation.height - 55
        self.move(x, y)

    # --- Window Controls ---
    def on_focus_out(self, widget, event):
        self.destroy()
        return True

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def on_destroy(self, widget):
        self.active_threads = False
        
        try:
            if os.path.exists(PID_FILE):
                with open(PID_FILE, "r") as f:
                    saved_pid = int(f.read().strip())
                if saved_pid == os.getpid():
                    os.remove(PID_FILE)
        except:
            pass
            
        Gtk.main_quit()

if __name__ == "__main__":
    mypid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            os.kill(old_pid, signal.SIGTERM)
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
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

    ControlCenterApp()
    Gtk.main()
