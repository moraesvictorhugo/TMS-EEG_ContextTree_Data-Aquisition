"""
Neuronavigation coil tracker.

Connects to one or more InVesalius relay servers to monitor whether the
TMS coil is on-target.  Runs a background thread that continuously polls
the message buffer and updates ``target_status`` for each connection.
"""
import time
import threading

from tms_eeg.navigation.remote_control import RemoteControl
from tms_eeg import config
from tms_eeg.logger import log
import traceback


class NavigationTracker:
    """Tracks coil-on-target status from InVesalius neuronavigation.

    Parameters
    ----------
    number_of_rc : int
        Number of remote-control connections (relay servers).
    """

    def __init__(self):
        self.rc = []
        self.target_status = []
        self.marker_label = []
        self.all_target_status = None

        self.status_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    # ── connection ────────────────────────────────────────────────────
    def connect(self, address, ports):
        """Connect to all relay servers and start the polling thread.

        Parameters
        ----------
        address : str
            IP address of the relay server (e.g. ``"127.0.0.1"``).
        ports : list[int]
            List of port numbers, one per remote-control connection.
        """
        number_of_rc = len(ports)
        self.rc = [None] * number_of_rc
        self.target_status = [None] * number_of_rc
        self.marker_label = [None] * number_of_rc

        for i, port in enumerate(ports):
            self.rc[i] = RemoteControl(f"http://{address}:{port}")
            self.rc[i].try_connect()
        self._start_thread()

    # ── background polling ────────────────────────────────────────────
    def _poll_loop(self):
        """Continuously read buffers and update target status."""
        while not self._stop_event.is_set():
            for i, rc in enumerate(self.rc):
                if rc is None:
                    continue
                new_target, new_marker = self._process_buffer(
                    rc, self.target_status[i], self.marker_label[i]
                )
                log(f"Processed buffer for RC {i}. New Target: {new_target}, New Marker: {new_marker}", "DEBUG")
                with self.status_lock:
                    self.target_status[i] = new_target
                    self.marker_label[i] = new_marker
            with self.status_lock:
                self.all_target_status = all(self.target_status)

    def _process_buffer(self, rc, target, marker):
        """Parse buffered messages and return updated target/marker state.

        Parameters
        ----------
        rc : RemoteControl
            The remote-control connection to read from.
        target : bool or None
            Current target status.
        marker : str or None
            Current marker label.

        Returns
        -------
        tuple[bool | None, str | None]
            Updated (target_status, marker_label).
        """
        buffer = rc.get_buffer()

        for msg in buffer:
            try:
                if msg["topic"] == config.PUB_MESSAGES[0]:
                    target = msg["data"]["state"]
                elif msg["topic"] == config.PUB_MESSAGES[1]:
                    marker = msg["data"]["name"]
            except Exception as e:
                error_details = traceback.format_exc()
                log(f"Exception processing buffer message '{msg}':\n{error_details}", "ERROR")

        time.sleep(0.1)
        return target, marker

    # ── navigation markers ────────────────────────────────────────────
    def send_trigger_to_navigation(self):
        """Send a 'Create marker' message to all connected relay servers."""
        if config.CREATE_NAVIGATION_MARKER:
            for rc in self.rc:
                if rc is not None:
                    rc.send_message("Create marker")

    # ── thread management ─────────────────────────────────────────────
    def _start_thread(self):
        """Start the background polling thread as a daemon."""
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
