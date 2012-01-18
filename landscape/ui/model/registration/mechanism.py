import select
import subprocess
import os

import dbus
import dbus.service
import dbus.glib
from landscape.ui.lib.polkit import PolicyKitMechanism


SERVICE_NAME = "com.canonical.LandscapeClientRegistration"
POLICY_NAME = SERVICE_NAME + ".register"
INTERFACE_NAME = \
    "com.canonical.LandscapeClientRegistration.RegistrationInterface"
OBJECT_PATH = \
    "/com/canonical/LandscapeClientRegistration/RegistrationInterface"


class PermissionDeniedByPolicy(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.LandscapeClientRegistration.PermissionDeniedByPolicy"


class RegistrationMechanism(PolicyKitMechanism):

    def __init__(self, bus_name, bypass=False, conn=None):
        super(RegistrationMechanism, self).__init__(
            OBJECT_PATH, bus_name, PermissionDeniedByPolicy,
            bypass=bypass, conn=conn)
        self.process = None
        self.message_list = []
        self.error_list = []

    def _do_regisration(self, config_path):
        self.message_list.append("Trying to register ...\n")
        cmd = ["landscape-config", "--silent", "-c",
               os.path.abspath(config_path)]
        self.process = subprocess.Popen(cmd, 
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        return_code = None
        while return_code is None:
            readables, w, x = select.select(
                [self.process.stdout, self.process.stderr], [], [], 0)
            for readable in readables:
                message = readable.readline()
                if readable is self.process.stdout:
                    self.message_list.append(message)
                else:
                    self.error_list.append(message)
            return_code = self.process.poll()
        return return_code

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s",
                         out_signature="bs",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def register(self, config_path, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            return_code = self._do_registration(config_path)
            if return_code == 0:
                return True, "Connected\n"
            else:
                return (False, 
                        "Failed to connect [code %s]\n" % str(return_code))

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="",
                         out_signature="{sas}",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def poll(self, sender=None, conn=None):
        messages = {"error":[""], "message":[""]}
        while len(self.message_list) > 0:
            messages["message"].append(self.message_list.pop())
        while len(self.error_list) > 0:
            messages["error"].append(self.error_list.pop())
        return messages
 
            

# class RegistrationMechanism(object):
#     """
#     L{RegistrationMechanism} provides the ability to run the landscape-client
#     registration in a way that can be observed by code using it via DBus.  This
#     allows for registration in an environment other than an interactive
#     terminal session.

#     @param on_idle: Optionally, a callable which will be invoked by repeatedly
#     during the registration process to allow cooperative yielding of control.
#     This can be used, for example, with Gtk to allow processing of Gtk events
#     without requiring either threading or the leaking of Gtk into the model
#     layer.
#     """

#     def __init__(self, on_idle=None):
#         self._notification_observers = []
#         self._error_observers = []
#         self._succeed_observers = []
#         self._fail_observers = []
#         self._on_idle = on_idle

#     def do_idle(self):
#         if self._on_idle:
#             self._on_idle()

#     def notify_observers(self, message, end="\n", error=False):
#         for function in self._notification_observers:
#             function(message, error)
#             self.do_idle()

#     def error_observers(self, error_list):
#         for function in self._error_observers:
#             function(error_list)
#             self.do_idle()

#     def register_notification_observer(self, function):
#         self._notification_observers.append(function)

#     def register_error_observer(self, function):
#         self._error_observers.append(function)

#     def register_succeed_observer(self, function):
#         self._succeed_observers.append(function)

#     def register_fail_observer(self, function):
#         self._fail_observers.append(function)

#     def succeed(self):
#         for function in self._succeed_observers:
#             function()
#             self.do_idle()

#     def fail(self, error=None):
#         for function in self._fail_observers:
#             function(error=error)
#             self.do_idle()

#     def register(self, config):
#         self.notify_observers("Trying to register ...\n")
#         cmd = ["landscape-config", "--silent", "-c",
#                os.path.abspath(config.get_config_filename())]
#         process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
#                                    stderr=subprocess.PIPE)
#         return_code = None
#         while return_code is None:
#             readables, w, x = select.select([process.stdout, process.stderr],
#                                             [], [], 0)
#             for readable in readables:
#                 message = readable.readline()
#                 if readable is process.stdout:
#                     self.notify_observers(message)
#                 else:
#                     self.error_observers(message)
#                 self.do_idle()
#             return_code = process.poll()
#             self.do_idle()
#         if return_code == 0:
#             self.succeed()
#             return True
#         else:
#             self.fail("Failed with code %s" % str(return_code))
#             return False
