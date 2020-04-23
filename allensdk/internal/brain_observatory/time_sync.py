from collections import deque
from typing import Optional, Callable, Any

import numpy as np
import h5py
from allensdk.brain_observatory.sync_dataset import Dataset
import pandas as pd
import logging
try:
    import cv2
except ImportError:
    cv2 = None

TRANSITION_FRAME_INTERVAL = 60
REG_PHOTODIODE_INTERVAL = 1.0     # seconds
REG_PHOTODIODE_STD = 0.05    # seconds
PHOTODIODE_ANOMALY_THRESHOLD = 0.5     # seconds
LONG_STIM_THRESHOLD = 0.2     # seconds
MAX_MONITOR_DELAY = 0.07     # seconds

VERSION_1_KEYS = {
    "photodiode": "stim_photodiode",
    "2p": "2p_vsync",
    "stimulus": "stim_vsync",
    "eye_camera": "cam2_exposure",
    "behavior_camera": "cam1_exposure",
    "acquiring": "2p_acquiring",
    "lick_sensor": "lick_1"
    }

# MPE is changing keys. This isn't versioned in the file.
VERSION_2_KEYS = {
    "photodiode": "stim_photodiode",
    "2p": "2p_vsync",
    "stimulus": "stim_vsync",
    "eye_camera": "eye_tracking",
    "behavior_camera": "behavior_monitoring",
    "acquiring": "2p_acquiring",
    "lick_sensor": "lick_sensor"
    }


def get_keys(sync_dset):
    """Get the correct lookup for line labels.

    This method is fragile, but not all old data contains the full list
    of keys.
    """
    if "cam2_exposure" in sync_dset.line_labels:
        return VERSION_1_KEYS
    return VERSION_2_KEYS


def monitor_delay(sync_dset, stim_times, photodiode_key,
                  transition_frame_interval=TRANSITION_FRAME_INTERVAL,
                  max_monitor_delay=MAX_MONITOR_DELAY):
    """Calculate monitor delay."""
    transitions = stim_times[::transition_frame_interval]
    photodiode_events = get_real_photodiode_events(sync_dset, photodiode_key)
    transition_events = photodiode_events[0:len(transitions)]

    delays = transition_events - transitions
    delay = np.mean(delays)
    logging.info(f"Calculated monitor delay: {delay}. \n "
                 f"Max monitor delay: {np.max(delays)}. \n "
                 f"Min monitor delay: {np.min(delays)}.\n "
                 f"Std monitor delay: {np.std(delays)}.")

    if delay < 0 or delay > max_monitor_delay:
        raise ValueError(f"Delay ({delay}s) falls outside expected value "
                         f"range (0-{MAX_MONITOR_DELAY}s).")
    return delay


def _find_last_n(arr: np.ndarray, n: int,
                 cond: Callable[[Any], bool]) -> Optional[int]:
    """
    Find the final index where the prior `n` values in an array meet
    the condition `cond` (inclusive).
    Parameters
    ==========
    arr: numpy.1darray
    n: int
    cond: Callable that returns True if condition is met, False
    otherwise. Should be able to be applied to the array elements
    without any additional arguments.
    """
    reversed_ix = _find_n(arr[::-1], n, cond)
    if reversed_ix is not None:
        reversed_ix = len(arr) - reversed_ix - 1
    return reversed_ix


def _find_n(arr: np.ndarray, n: int,
            cond: Callable[[Any], bool]) -> Optional[int]:
    """
    Find the index where the next `n` values in an array meet the
    condition `cond` (inclusive).
    Parameters
    ==========
    arr: numpy.1darray
    n: int
    cond: Callable that returns True if condition is met, False
    otherwise. Should be able to be applied to the array elements
    without any additional arguments.
    """
    if len(arr) < n:
        return None
    queue = deque(np.apply_along_axis(cond, 0, arr[:n]), maxlen=n)
    i = 0
    while queue.count(True) < n:
        try:
            i += 1
            queue.append(cond(arr[i+n-1]))
        except IndexError:
            return None
    return i


def get_photodiode_events(sync_dset, photodiode_key):
    """Returns the photodiode events with the start/stop indicators and
    the window init flash stripped off. These transitions occur roughly
    ~1.0s apart, since the sync square changes state every N frames
    (where N = 60, and frame rate is 60 Hz). Because there are no
    markers for when the first transition of this type started, we
    estimate based on the event intervals. For the first valid event,
    find the first two events that both meet the following criteria:
        The next event occurs ~1.0s later
    First the last valid event, find the first two events that both meet
    the following criteria:
        The last valid event occured ~1.0s before
    """
    all_events = sync_dset.get_events_by_line(photodiode_key, units="seconds")
    all_events_diff = np.ediff1d(all_events, to_begin=0, to_end=0)
    all_events_diff_prev = all_events_diff[:-1]
    all_events_diff_next = all_events_diff[1:]
    min_interval = REG_PHOTODIODE_INTERVAL - REG_PHOTODIODE_STD
    max_interval = REG_PHOTODIODE_INTERVAL + REG_PHOTODIODE_STD
    if not len(all_events):
        raise ValueError("No photodiode events found. Please check "
                         "the input data for errors. ")
    first_valid_index = _find_n(
        all_events_diff_next, 2,
        lambda x: (x >= min_interval) & (x <= max_interval))
    last_valid_index = _find_last_n(
        all_events_diff_prev, 2,
        lambda x: (x >= min_interval) & (x <= max_interval))
    if first_valid_index is None:
        raise ValueError("Can't find valid start event")
    if last_valid_index is None:
        raise ValueError("Can't find valid end event")
    pd_events = all_events[first_valid_index:last_valid_index+1]
    return pd_events


def get_real_photodiode_events(sync_dset, photodiode_key,
                               anomaly_threshold=PHOTODIODE_ANOMALY_THRESHOLD):
    """Gets the photodiode events with the anomalies removed."""
    events = get_photodiode_events(sync_dset, photodiode_key)
    anomalies = np.where(np.diff(events) < anomaly_threshold)
    return np.delete(events, anomalies)


def get_alignment_array(ref, other, int_method=np.floor):
    """Generate an alignment array """
    return int_method(np.interp(other, ref, np.arange(len(ref)), left=np.nan,
                      right=np.nan))


def get_video_length(filename):
    if cv2 is not None:
        try:
            capture = cv2.VideoCapture(filename)
            return int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        except AttributeError:
            logging.warning("Could not get length for %s, opencv out of date",
                            filename)
    else:
        logging.warning("Could not get length for %s", filename)


def get_ophys_data_length(filename):
    with h5py.File(filename, "r") as f:
        return f["data"].shape[1]


def get_stim_data_length(filename: str) -> int:
    """Get stimulus data length from .pkl file.

    Parameters
    ----------
    filename : str
        Path of stimulus data .pkl file.

    Returns
    -------
    int
        Stimulus data length.
    """
    stim_data = pd.read_pickle(filename)

    # A subset of stimulus .pkl files do not have the "vsynccount" field.
    # MPE *won't* be backfilling the "vsynccount" field for these .pkl files.
    # So the least worst option is to recalculate the vsync_count.
    try:
        vsync_count = stim_data["vsynccount"]
    except KeyError:
        vsync_count = len(stim_data["items"]["behavior"]["intervalsms"]) + 1

    return vsync_count


def corrected_video_timestamps(video_name, timestamps, data_length):
    delta = 0
    if data_length is not None:
        delta = len(timestamps) - data_length
        if delta != 0:
            logging.info("%s data of length %s has timestamps of length "
                         "%s", video_name, data_length, len(timestamps))
    else:
        logging.info("No data length provided for %s", video_name)

    return timestamps, delta


class OphysTimeAligner(object):
    def __init__(self, sync_file, scanner=None, dff_file=None,
                 stimulus_pkl=None, eye_video=None, behavior_video=None,
                 long_stim_threshold=LONG_STIM_THRESHOLD):
        self.scanner = scanner if scanner is not None else "SCIVIVO"
        self._dataset = Dataset(sync_file)
        self._keys = get_keys(self._dataset)
        self.long_stim_threshold = long_stim_threshold
        if dff_file is not None:
            self.ophys_data_length = get_ophys_data_length(dff_file)
        else:
            self.ophys_data_length = None
        if stimulus_pkl is not None:
            self.stim_data_length = get_stim_data_length(stimulus_pkl)
        else:
            self.stim_data_length = None
        if eye_video is not None:
            self.eye_data_length = get_video_length(eye_video)
        else:
            self.eye_data_length = None
        if behavior_video is not None:
            self.behavior_data_length = get_video_length(behavior_video)
        else:
            self.behavior_data_length = None

    @property
    def dataset(self):
        return self._dataset


    @property
    def ophys_timestamps(self):
        """Get the timestamps for the ophys data."""
        ophys_key = self._keys["2p"]
        if self.scanner == "SCIVIVO":
            # Scientifica data looks different than Nikon.
            # http://confluence.corp.alleninstitute.org/display/IT/Ophys+Time+Sync
            times = self.dataset.get_rising_edges(ophys_key, units="seconds")
        elif self.scanner == "NIKONA1RMP":
            # Nikon has a signal that indicates when it started writing to disk
            acquiring_key = self._keys["acquiring"]
            acquisition_start = self._dataset.get_rising_edges(
                acquiring_key, units="seconds")[0]
            ophys_times = self._dataset.get_falling_edges(
                ophys_key, units="seconds")
            times = ophys_times[ophys_times >= acquisition_start]
        else:
            raise ValueError("Invalid scanner: {}".format(self.scanner))

        return times

    @property
    def corrected_ophys_timestamps(self):
        times = self.ophys_timestamps

        delta = 0
        if self.ophys_data_length is not None:
            if len(times) < self.ophys_data_length:
                raise ValueError(
                    "Got too few timestamps ({}) for ophys data length "
                    "({})".format(len(times), self.ophys_data_length))
            elif len(times) > self.ophys_data_length:
                logging.info("Ophys data of length %s has timestamps of "
                             "length %s, truncating timestamps",
                             self.ophys_data_length, len(times))
                delta = len(times) - self.ophys_data_length
                times = times[:-delta]
        else:
            logging.info("No data length provided for ophys stream")

        return times, delta

    @property
    def stim_timestamps(self):
        stim_key = self._keys["stimulus"]

        return self.dataset.get_falling_edges(stim_key, units="seconds")

    @property
    def corrected_stim_timestamps(self):
        timestamps = self.stim_timestamps

        delta = 0
        if self.stim_data_length is not None and \
           self.stim_data_length < len(timestamps):
            stim_key = self._keys["stimulus"]
            rising = self.dataset.get_rising_edges(stim_key, units="seconds")

            # Some versions of camstim caused a spike when the DAQ is first
            # initialized. Remove it.
            if rising[1] - rising[0] > self.long_stim_threshold:
                logging.info("Initial DAQ spike detected from stimulus, "
                             "removing it")
                timestamps = timestamps[1:]

            delta = len(timestamps) - self.stim_data_length
            if delta != 0:
                logging.info("Stim data of length %s has timestamps of "
                             "length %s",
                             self.stim_data_length, len(timestamps))
        elif self.stim_data_length is None:
            logging.info("No data length provided for stim stream")

        photodiode_key = self._keys["photodiode"]
        delay = monitor_delay(self.dataset, timestamps, photodiode_key)

        return timestamps + delay, delta, delay

    @property
    def behavior_video_timestamps(self):
        key = self._keys["behavior_camera"]

        return self.dataset.get_falling_edges(key, units="seconds")

    @property
    def corrected_behavior_video_timestamps(self):
        return corrected_video_timestamps("Behavior video",
                                          self.behavior_video_timestamps,
                                          self.behavior_data_length)

    @property
    def eye_video_timestamps(self):
        key = self._keys["eye_camera"]

        return self.dataset.get_falling_edges(key, units="seconds")

    @property
    def corrected_eye_video_timestamps(self):
        return corrected_video_timestamps("Eye video",
                                          self.eye_video_timestamps,
                                          self.eye_data_length)
