import socket
from landscape.monitor.networkactivity import NetworkActivity
from landscape.tests.helpers import LandscapeTest, MonitorHelper


class NetworkActivityTest(LandscapeTest):

    helpers = [MonitorHelper]

    stats_template = """\
Inter-|   Receive                           |  Transmit
 face |bytes    packets compressed multicast|bytes    packets errs drop fifo
    lo:%(lo_in)d   %(lo_in_p)d   0     0   %(lo_out)d %(lo_out_p)d  0  0  0
    eth0: %(eth0_in)d   12539    0     62  %(eth0_out)d   12579  0  0  0
    %(extra)s
"""

    def setUp(self):
        super(NetworkActivityTest, self).setUp()
        self.activity_file = open(self.makeFile(), "w+")
        self.write_activity()
        self.plugin = NetworkActivity(
            network_activity_file=self.activity_file.name,
            create_time=self.reactor.time)
        self.monitor.add(self.plugin)

    def tearDown(self):
        self.activity_file.close()
        super(NetworkActivityTest, self).tearDown()

    def write_activity(self, lo_in=0, lo_out=0, eth0_in=0, eth0_out=0,
                        extra="", lo_in_p=0, lo_out_p=0, **kw):
        kw.update(dict(
            lo_in=lo_in,
            lo_out=lo_out,
            lo_in_p=lo_in_p,
            lo_out_p=lo_out_p,
            eth0_in=eth0_in,
            eth0_out=eth0_out,
            extra=extra))
        self.activity_file.seek(0, 0)
        self.activity_file.truncate()
        self.activity_file.write(self.stats_template % kw)
        self.activity_file.flush()

    def test_read_proc_net_dev(self):
        """
        When the network activity plugin runs it reads data from
        /proc/net/dev which it parses and accumulates to read values.
        This test ensures that /proc/net/dev is always parseable and
        that messages are in the expected format and contain data with
        expected datatypes.
        """
        plugin = NetworkActivity(create_time=self.reactor.time)
        self.monitor.add(plugin)
        plugin.run()
        self.reactor.advance(self.monitor.step_size)
        # hmmm. try to connect anywhere to advance the net stats
        try:
            socket.socket().connect(("localhost", 9999))
        except socket.error:
            pass
        plugin.run()
        message = plugin.create_message()
        self.assertTrue(message)

    def test_message_contents(self):
        """
        The network plugin sends messages with the traffic delta along with the
        step per network interface. Only interfaces which have deltas are
        present in the message.
        """
        self.write_activity(lo_in=2000, lo_out=1900)
        self.plugin.run()
        self.reactor.advance(self.monitor.step_size)
        self.write_activity(lo_in=2010, lo_out=1999)
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertTrue(message)
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "network-activity")
        self.assertEqual(message["activities"][b"lo"],
                         [(300, 10, 99)])
        # Ensure that b"eth0" is not in activities
        self.assertEqual(len(message["activities"]), 1)

    def test_proc_rollover(self):
        """
        If /proc/net/dev rollovers, the network plugin handles the value and
        gives a positive value instead.
        """
        self.plugin._rollover_maxint = 10000
        self.write_activity(lo_in=2000, lo_out=1900)
        self.plugin.run()
        self.reactor.advance(self.monitor.step_size)
        self.write_activity(lo_in=1010, lo_out=999)
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertTrue(message)
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "network-activity")
        self.assertEqual(message["activities"][b"lo"],
                         [(300, 9010, 9099)])
        # Ensure that b"eth0" is not in activities
        self.assertEqual(len(message["activities"]), 1)

    def test_no_message_without_traffic_delta(self):
        """
        If no traffic delta is detected between runs, no message will be
        generated by the plugin.
        """
        self.plugin.run()
        self.reactor.advance(self.monitor.step_size)
        message = self.plugin.create_message()
        self.assertFalse(message)
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertFalse(message)

    def test_no_message_without_traffic_delta_across_steps(self):
        """
        A traffic delta needs to cross step boundaries before a message
        is generated.
        """
        self.plugin.run()
        self.write_activity(lo_out=1000, eth0_out=1000)
        self.reactor.advance(self.monitor.step_size)
        message = self.plugin.create_message()
        self.assertFalse(message)

    def test_interface_temporarily_disappears(self):
        """
        When an interface is removed (ie usb hotplug) and then activated again
        its delta will not be retained, because the values may have been reset.
        """
        self.write_activity(extra="wlan0: 2222 0 0 0 2222 0 0 0 0")
        self.plugin.run()
        self.reactor.advance(self.monitor.step_size)
        self.write_activity()
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertFalse(message)
        self.write_activity(extra="wlan0: 1000 0 0 0 1000 0 0 0 0")
        self.reactor.advance(self.monitor.step_size)
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertFalse(message)

    def test_messaging_flushes(self):
        """
        Duplicate message should never be created.  If no data is available, no
        message is created.
        """
        self.plugin.run()
        self.reactor.advance(self.monitor.step_size)
        self.write_activity(eth0_out=1111)
        self.plugin.run()
        message = self.plugin.create_message()
        self.assertTrue(message)
        message = self.plugin.create_message()
        self.assertFalse(message)

    def test_exchange_no_message(self):
        """
        No message is sent to the exchange if there isn't a traffic delta.
        """
        self.reactor.advance(self.monitor.step_size)
        self.mstore.set_accepted_types([self.plugin.message_type])
        self.plugin.exchange()
        self.assertFalse(self.mstore.count_pending_messages())

    def test_exchange_messages(self):
        """
        The network plugin queues message when an exchange happens. Each
        message should be aligned to a step boundary; messages collected
        between exchange periods should be delivered in a single message.
        """
        self.reactor.advance(self.monitor.step_size)
        self.write_activity(lo_out=1000, eth0_out=1000)
        self.plugin.run()
        self.mstore.set_accepted_types([self.plugin.message_type])
        self.plugin.exchange()
        step_size = self.monitor.step_size
        self.assertMessages(self.mstore.get_pending_messages(),
                        [{"type": "network-activity",
                          "activities": {
                              "lo": [(step_size, 0, 1000)],
                              "eth0": [(step_size, 0, 1000)]}}])

    def test_config(self):
        """The network activity plugin is enabled by default."""
        self.assertIn("NetworkActivity", self.config.plugin_factories)

    def test_limit_amount_of_items(self):
        """
        The network plugin doesn't send too many items at once in a single
        network message, to not crush the server.
        """
        def extra(data):
            result = ""
            for i in range(50):
                result += (
"""eth%d: %d   12539      0     62  %d   12579    0    0   0\n    """
                    % (i, data, data))
            return result
        for i in range(1, 10):
            data = i * 1000
            self.write_activity(lo_out=data, eth0_out=data, extra=extra(data))
            self.plugin.run()
            self.reactor.advance(self.monitor.step_size)
        # We have created 408 items. It should be sent in 3 messages.
        message = self.plugin.create_message()
        items = sum(len(i) for i in message["activities"].values())
        self.assertEqual(200, items)
        message = self.plugin.create_message()
        items = sum(len(i) for i in message["activities"].values())
        self.assertEqual(200, items)
        message = self.plugin.create_message()
        items = sum(len(i) for i in message["activities"].values())
        self.assertEqual(8, items)
