"""
Socket.IO remote-control client for the InVesalius relay server.

Connects to a relay server and buffers incoming messages on the
``to_robot`` channel. Provides thread-safe buffer access.
"""
import time
import threading

import socketio


class RemoteControl:
    """Socket.IO client for a single neuronavigation relay connection.

    Parameters
    ----------
    remote_host : str
        Full URL of the relay server (e.g. ``"http://127.0.0.1:5000"``).
    """

    def __init__(self, remote_host):
        self._buffer = []
        self._remote_host = remote_host
        self._connected = False
        self._sio = socketio.Client()
        self._lock = threading.Lock()

        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)
        self._sio.on("to_robot", self._on_message_receive)

    # ── Socket.IO callbacks ───────────────────────────────────────────
    def _on_connect(self):
        print(f"Connected to {self._remote_host}")
        self._connected = True

    def _on_disconnect(self):
        print("Disconnected")
        self._connected = False

    def _on_message_receive(self, msg):
        with self._lock:
            self._buffer.append(msg)

    # ── public API ────────────────────────────────────────────────────
    def get_buffer(self):
        """Return all buffered messages and clear the buffer (thread-safe).

        Returns
        -------
        list[dict]
            List of message dicts received since the last call.
        """
        with self._lock:
            messages = self._buffer.copy()
            self._buffer.clear()
        return messages

    def try_connect(self):
        """Attempt to connect and block until connected."""
        self._sio.connect(self._remote_host, wait_timeout=1)

        while not self._connected:
            print("Connecting...")
            time.sleep(1.0)

    def send_message(self, topic, data=None):
        """Emit a message to the relay server.

        Parameters
        ----------
        topic : str
            Message topic.
        data : dict, optional
            Payload data. Defaults to empty dict.
        """
        if data is None:
            data = {}
        self._sio.emit("from_robot", {"topic": topic, "data": data})
