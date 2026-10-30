"""
GDriveSync System Tray StatusNotifierItem
Exports org.kde.StatusNotifierItem on the user DBus session for native
system tray integration in Ubuntu GNOME / KDE / XFCE / Wayland desktops.
"""

from typing import Callable, Optional
import gi
from gi.repository import Gio, GLib


SNI_XML = """
<node>
  <interface name='org.kde.StatusNotifierItem'>
    <property name='Category' type='s' access='read'/>
    <property name='Id' type='s' access='read'/>
    <property name='Title' type='s' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='IconName' type='s' access='read'/>
    <property name='Menu' type='o' access='read'/>
    <method name='Activate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='SecondaryActivate'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
    <method name='ContextMenu'>
      <arg type='i' name='x' direction='in'/>
      <arg type='i' name='y' direction='in'/>
    </method>
  </interface>
</node>
"""


class TrayIndicator:
    def __init__(self, on_activate: Optional[Callable] = None):
        self.on_activate = on_activate
        self.bus: Optional[Gio.DBusConnection] = None
        self.reg_id = 0
        self.is_registered = False

    def start(self):
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
            iface_info = node_info.interfaces[0]

            def handle_method_call(conn, sender, obj_path, iface, method, params, invocation):
                if method in ("Activate", "SecondaryActivate", "ContextMenu"):
                    if self.on_activate:
                        GLib.idle_add(self.on_activate)
                invocation.return_value(None)

            def handle_get_prop(conn, sender, obj_path, iface, prop):
                if prop == "Category":
                    return GLib.Variant("s", "ApplicationStatus")
                elif prop == "Id":
                    return GLib.Variant("s", "gdrivesync")
                elif prop == "Title":
                    return GLib.Variant("s", "Google Drive")
                elif prop == "Status":
                    return GLib.Variant("s", "Active")
                elif prop == "IconName":
                    return GLib.Variant("s", "folder-remote-symbolic")
                elif prop == "Menu":
                    return GLib.Variant("o", "/MenuBar")
                return None

            self.reg_id = self.bus.register_object(
                "/StatusNotifierItem",
                iface_info,
                handle_method_call,
                handle_get_prop,
                None
            )

            # Register with StatusNotifierWatcher
            self.bus.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", ("/StatusNotifierItem",)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            self.is_registered = True
        except Exception as e:
            # Not all desktop environments run StatusNotifierWatcher, which is completely fine
            pass

    def stop(self):
        if self.bus and self.reg_id:
            try:
                self.bus.unregister_object(self.reg_id)
            except Exception:
                pass
            self.reg_id = 0
            self.is_registered = False
