#!/usr/bin/env python3
"""DDWriter - A Rufus-like GUI for writing ISO images using dd."""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
import subprocess
import os
import re
import threading
import signal
import hashlib
from pathlib import Path


class Device:
    """Represents a block device."""
    def __init__(self, path, model, size, size_human, removable):
        self.path = path
        self.model = model
        self.size = size
        self.size_human = size_human
        self.removable = removable

    def __str__(self):
        return f"{self.path} - {self.model} ({self.size_human})"


class PasswordDialog(Gtk.Dialog):
    """Dialog to prompt for sudo password."""
    def __init__(self, parent):
        super().__init__(title="Authentication Required", transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Authenticate", Gtk.ResponseType.OK)
        
        box = self.get_content_area()
        box.set_spacing(12)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        
        label = Gtk.Label(label="Enter your password to write to the device:")
        box.add(label)
        
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_hexpand(True)
        self.password_entry.connect("activate", lambda e: self.response(Gtk.ResponseType.OK))
        box.add(self.password_entry)
        
        self.show_all()

    def get_password(self):
        return self.password_entry.get_text()


class DDWriterWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="DDWriter")
        self.set_default_size(500, 400)
        self.set_border_width(12)
        
        self.devices = []
        self.selected_device = None
        self.selected_iso = None
        self.dd_process = None
        self.is_writing = False
        
        self._build_ui()
        self._refresh_devices()
    
    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(main_box)
        
        # Device section
        device_frame = Gtk.Frame(label="Target Device")
        main_box.pack_start(device_frame, False, False, 0)
        
        device_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        device_box.set_margin_start(8)
        device_box.set_margin_end(8)
        device_box.set_margin_top(8)
        device_box.set_margin_bottom(8)
        device_frame.add(device_box)
        
        self.device_combo = Gtk.ComboBoxText()
        self.device_combo.set_hexpand(True)
        self.device_combo.connect("changed", self._on_device_changed)
        device_box.pack_start(self.device_combo, True, True, 0)
        
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", lambda b: self._refresh_devices())
        device_box.pack_start(refresh_button, False, False, 0)
        
        self.device_info_label = Gtk.Label(label="No device selected")
        self.device_info_label.set_xalign(0)
        main_box.pack_start(self.device_info_label, False, False, 0)
        
        # ISO section
        iso_frame = Gtk.Frame(label="Source Image")
        main_box.pack_start(iso_frame, False, False, 0)
        
        iso_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        iso_box.set_margin_start(8)
        iso_box.set_margin_end(8)
        iso_box.set_margin_top(8)
        iso_box.set_margin_bottom(8)
        iso_frame.add(iso_box)
        
        self.iso_label = Gtk.Label(label="No file selected")
        self.iso_label.set_xalign(0)
        self.iso_label.set_hexpand(True)
        iso_box.pack_start(self.iso_label, True, True, 0)
        
        browse_button = Gtk.Button(label="Browse...")
        browse_button.connect("clicked", self._on_browse_clicked)
        iso_box.pack_start(browse_button, False, False, 0)
        
        # Options section
        options_frame = Gtk.Frame(label="Options")
        main_box.pack_start(options_frame, False, False, 0)
        
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        options_box.set_margin_start(8)
        options_box.set_margin_end(8)
        options_box.set_margin_top(8)
        options_box.set_margin_bottom(8)
        options_frame.add(options_box)
        
        self.verify_check = Gtk.CheckButton(label="Verify write after completion")
        self.verify_check.set_active(True)
        options_box.pack_start(self.verify_check, False, False, 0)
        
        self.eject_check = Gtk.CheckButton(label="Eject device after write")
        self.eject_check.set_active(True)
        options_box.pack_start(self.eject_check, False, False, 0)
        
        # Progress section
        progress_frame = Gtk.Frame(label="Progress")
        main_box.pack_start(progress_frame, False, False, 0)
        
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        progress_box.set_margin_start(8)
        progress_box.set_margin_end(8)
        progress_box.set_margin_top(8)
        progress_box.set_margin_bottom(8)
        progress_frame.add(progress_box)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ready")
        progress_box.pack_start(self.progress_bar, False, False, 0)
        
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        progress_box.pack_start(self.status_label, False, False, 0)
        
        # Log section
        log_frame = Gtk.Frame(label="Log")
        main_box.pack_start(log_frame, True, True, 0)
        
        log_scrolled = Gtk.ScrolledWindow()
        log_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_frame.add(log_scrolled)
        
        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer)
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        log_scrolled.add(self.log_view)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_box.pack_start(button_box, False, False, 0)
        
        self.write_button = Gtk.Button(label="Write")
        self.write_button.get_style_context().add_class("suggested-action")
        self.write_button.connect("clicked", self._on_write_clicked)
        button_box.pack_end(self.write_button, False, False, 0)
        
        quit_button = Gtk.Button(label="Quit")
        quit_button.connect("clicked", lambda b: Gtk.main_quit())
        button_box.pack_end(quit_button, False, False, 0)
    
    def _log(self, message):
        def _append():
            end_iter = self.log_buffer.get_end_iter()
            self.log_buffer.insert(end_iter, message + "\n")
            self.log_view.scroll_mark_onscreen(self.log_buffer.get_insert())
        GLib.idle_add(_append)
    
    def _set_status(self, text):
        def _set():
            self.status_label.set_text(text)
            self.progress_bar.set_text(text)
        GLib.idle_add(_set)
    
    def _set_progress(self, fraction, text=None):
        def _set():
            self.progress_bar.set_fraction(fraction)
            if text:
                self.progress_bar.set_text(text)
        GLib.idle_add(_set)
    
    def _refresh_devices(self):
        self.devices.clear()
        self.device_combo.remove_all()
        
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,MODEL,SIZE,RM,TYPE"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode != 0:
                self._log("Error listing devices")
                return
            
            import json
            data = json.loads(result.stdout)
            
            for dev in data.get("blockdevices", []):
                if dev.get("type") != "disk":
                    continue
                
                name = dev.get("name", "")
                model = (dev.get("model") or "Unknown").strip()
                size = dev.get("size", "Unknown")
                removable = dev.get("rm", False)
                
                # Skip non-removable devices (safety)
                if not removable:
                    continue
                
                path = f"/dev/{name}"
                device = Device(path, model, 0, size, removable)
                self.devices.append(device)
                self.device_combo.append_text(str(device))
            
            if self.devices:
                self.device_combo.set_active(0)
                self._log(f"Found {len(self.devices)} removable device(s)")
            else:
                self._log("No removable devices found")
                
        except Exception as e:
            self._log(f"Error: {e}")
    
    def _on_device_changed(self, combo):
        index = combo.get_active()
        if index >= 0 and index < len(self.devices):
            self.selected_device = self.devices[index]
            self.device_info_label.set_text(
                f"Model: {self.selected_device.model}\n"
                f"Size: {self.selected_device.size_human}"
            )
            self._log(f"Selected device: {self.selected_device}")
    
    def _on_browse_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Image File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Open", Gtk.ResponseType.OK
        )
        
        # Add file filters
        filter_iso = Gtk.FileFilter()
        filter_iso.set_name("Image files")
        filter_iso.add_mime_type("application/x-iso9660-image")
        filter_iso.add_pattern("*.iso")
        filter_iso.add_pattern("*.img")
        filter_iso.add_pattern("*.raw")
        filter_iso.add_pattern("*.bin")
        filter_iso.add_pattern("*.dd")
        dialog.add_filter(filter_iso)
        
        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.selected_iso = dialog.get_filename()
            self.iso_label.set_text(os.path.basename(self.selected_iso))
            self._log(f"Selected image: {self.selected_iso}")
        
        dialog.destroy()
    
    def _on_write_clicked(self, button):
        if self.is_writing:
            self._cancel_write()
            return
        
        # Validate selections
        if not self.selected_device:
            self._show_error("Please select a target device.")
            return
        
        if not self.selected_iso:
            self._show_error("Please select an image file.")
            return
        
        if not os.path.exists(self.selected_iso):
            self._show_error("The selected image file does not exist.")
            return
        
        # Confirm
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"This will completely erase {self.selected_device.path} ({self.selected_device.size_human})"
        )
        dialog.format_secondary_text(
            f"Are you sure you want to write {os.path.basename(self.selected_iso)} to {self.selected_device.path}?"
        )
        
        response = dialog.run()
        dialog.destroy()
        
        if response != Gtk.ResponseType.YES:
            return
        
        # Get password
        pass_dialog = PasswordDialog(self)
        response = pass_dialog.run()
        password = pass_dialog.get_password()
        pass_dialog.destroy()
        
        if response != Gtk.ResponseType.OK or not password:
            return
        
        # Start writing
        self._start_write(password)
    
    def _start_write(self, password):
        self.is_writing = True
        self._current_password = password
        self.write_button.set_label("Cancel")
        self.progress_bar.set_fraction(0)
        self._set_status("Writing...")
        self._log(f"Starting write: {self.selected_iso} -> {self.selected_device.path}")
        
        thread = threading.Thread(
            target=self._dd_worker,
            args=(password,),
            daemon=True
        )
        thread.start()
    
    def _dd_worker(self, password):
        try:
            # Build dd command
            cmd = [
                "sudo", "-S", "-k",
                "dd",
                f"if={self.selected_iso}",
                f"of={self.selected_device.path}",
                "bs=4M",
                "status=progress",
                "oflag=sync"
            ]
            
            self._log(f"Running: dd if={self.selected_iso} of={self.selected_device.path}")
            
            self.dd_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Send password
            self.dd_process.stdin.write(password + "\n")
            self.dd_process.stdin.flush()
            
            # Read output
            bytes_pattern = re.compile(r'(\d+)\s+bytes')
            progress_pattern = re.compile(r'(\d+)\s+bytes.*copied.*(\d+\.?\d*)\s*s')
            
            for line in self.dd_process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                self._log(line)
                
                # Parse progress
                match = progress_pattern.search(line)
                if match:
                    bytes_copied = int(match.group(1))
                    time_elapsed = float(match.group(2))
                    
                    # Get file size
                    file_size = os.path.getsize(self.selected_iso)
                    if file_size > 0:
                        fraction = min(bytes_copied / file_size, 1.0)
                        speed = bytes_copied / time_elapsed / (1024 * 1024) if time_elapsed > 0 else 0
                        self._set_progress(fraction, f"{fraction*100:.1f}% - {speed:.1f} MB/s")
            
            self.dd_process.wait()
            
            if self.dd_process.returncode == 0:
                self._set_progress(1.0, "Complete")
                self._set_status("Write completed successfully")
                self._log("Write completed successfully")
                
                # Verify if requested
                if self.verify_check.get_active():
                    self._verify_write()
                
                # Eject if requested
                if self.eject_check.get_active():
                    self._eject_device()
                
                self._show_info("Write completed successfully!")
            else:
                self._set_status("Write failed")
                self._log("Write failed")
                self._show_error("Write failed. Check the log for details.")
        
        except Exception as e:
            self._log(f"Error: {e}")
            self._set_status("Error occurred")
            self._show_error(f"Error: {e}")
        
        finally:
            self.dd_process = None
            self.is_writing = False
            GLib.idle_add(lambda: self.write_button.set_label("Write"))
    
    def _cancel_write(self):
        if self.dd_process:
            self._log("Cancelling write...")
            self.dd_process.terminate()
            try:
                self.dd_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.dd_process.kill()
            self._set_status("Cancelled")
            self.is_writing = False
            self.write_button.set_label("Write")
    
    def _verify_write(self):
        self._set_status("Verifying...")
        self._log("Verifying write...")
        
        try:
            # Get source hash
            self._log("Computing source checksum...")
            source_hash = self._hash_file(self.selected_iso)
            
            # Get target hash
            self._log("Computing target checksum...")
            target_hash = self._hash_device(self.selected_device.path, len(source_hash) * 2)
            
            if source_hash == target_hash:
                self._log("Verification passed: checksums match")
                self._set_status("Verification passed")
            else:
                self._log("Verification FAILED: checksums do not match")
                self._set_status("Verification failed")
                self._show_error("Verification failed! The written data does not match the source.")
        
        except Exception as e:
            self._log(f"Verification error: {e}")
            self._set_status("Verification error")
    
    def _hash_file(self, filepath):
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _hash_device(self, device_path, length):
        sha256 = hashlib.sha256()
        cmd = [
            "sudo", "-S", "-k",
            "dd", f"if={device_path}", "bs=8192", f"count={length // 8192}", "status=none"
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        proc.stdin.write(self._current_password + "\n")
        proc.stdin.flush()
        while True:
            chunk = proc.stdout.read(8192)
            if not chunk:
                break
            sha256.update(chunk.encode('latin-1'))
        proc.wait()
        return sha256.hexdigest()
    
    def _eject_device(self):
        self._log(f"Ejecting {self.selected_device.path}...")
        try:
            # Try udisksctl first
            result = subprocess.run(
                ["sudo", "-S", "-k", "udisksctl", "power-off", "-b", self.selected_device.path],
                input=self._current_password + "\n",
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self._log("Device ejected successfully")
            else:
                # Fallback to eject
                result = subprocess.run(
                    ["sudo", "-S", "-k", "eject", self.selected_device.path],
                    input=self._current_password + "\n",
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self._log("Device ejected successfully")
                else:
                    self._log("Warning: Could not eject device automatically")
        except Exception as e:
            self._log(f"Warning: Eject failed: {e}")
    
    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
    
    def _show_info(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
    
    def do_delete_event(self, event):
        if self.is_writing:
            self._cancel_write()
        return False


def main():
    # Set CSS for better styling
    css = b"""
    .suggested-action {
        font-weight: bold;
    }
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    
    window = DDWriterWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
