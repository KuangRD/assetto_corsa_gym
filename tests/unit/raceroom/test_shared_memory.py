import ctypes
import unittest

from assetto_corsa_gym.RaceRoom.shared_memory import RaceRoomSharedMemory
from assetto_corsa_gym.RaceRoom.structures import R3EDriverData, R3EShared
from assetto_corsa_gym.RacingEnv.errors import SharedMemoryVersionError


def make_payload(sequence, major=3, minor=5):
    data = R3EShared()
    data.version_major = major
    data.version_minor = minor
    data.all_drivers_offset = R3EShared.num_cars.offset
    data.driver_data_size = ctypes.sizeof(R3EDriverData)
    data.player.game_simulation_ticks = sequence
    return bytes(data)


class ScriptedSource:
    def __init__(self, int_reads, payload):
        self.int_reads = list(int_reads)
        self.payload = payload
        self.opened = False

    def open(self, size):
        self.opened = True

    def close(self):
        self.opened = False

    def read_int32(self, offset):
        return self.int_reads.pop(0)

    def read_bytes(self, size):
        return self.payload


class SequenceSource:
    def __init__(self, sequences):
        self.sequences = list(sequences)
        self.index = 0
        self.after_read = False

    def open(self, size):
        pass

    def close(self):
        pass

    def read_int32(self, offset):
        value = self.sequences[self.index]
        if self.after_read:
            self.index = min(self.index + 1, len(self.sequences) - 1)
        self.after_read = not self.after_read
        return value

    def read_bytes(self, size):
        return make_payload(self.sequences[self.index])


class SharedMemoryReaderTests(unittest.TestCase):
    def test_torn_read_is_retried(self):
        source = ScriptedSource([1, 2, 2, 2], make_payload(2))
        reader = RaceRoomSharedMemory(source=source)
        snapshot = reader.open()
        self.assertEqual(snapshot.sequence, 2)
        self.assertEqual(reader.stats.torn_read_retries, 1)

    def test_duplicate_is_not_returned_as_new(self):
        reader = RaceRoomSharedMemory(
            source=SequenceSource([1, 1, 2]), poll_interval_s=0.0
        )
        first = reader.open()
        second = reader.wait_for_snapshot(first.sequence, timeout_s=0.1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(reader.stats.duplicate_sequences, 1)

    def test_backward_tick_marks_session_reset(self):
        reader = RaceRoomSharedMemory(
            source=SequenceSource([10, 3]), poll_interval_s=0.0
        )
        first = reader.open()
        second = reader.wait_for_snapshot(first.sequence, timeout_s=0.1)
        self.assertEqual(second.sequence, 3)
        self.assertTrue(second.sequence_reset)
        self.assertEqual(reader.stats.sequence_resets, 1)

    def test_incompatible_major_is_rejected_and_closed(self):
        source = ScriptedSource([1, 1], make_payload(1, major=4))
        reader = RaceRoomSharedMemory(source=source)
        with self.assertRaises(SharedMemoryVersionError):
            reader.open()
        self.assertFalse(reader.connected)
        self.assertFalse(source.opened)


if __name__ == "__main__":
    unittest.main()
