import sys
import time
import unittest
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import decode_frame, encode_frame
from serial_service import SerialService, ServiceError, pb


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.incoming = Queue()
        self.commands = []
        self.closed = False
        self.drop_acks = 0

    def emit(self, message):
        for byte in encode_frame(message.SerializeToString()):
            self.incoming.put(byte)

    def write(self, data):
        if data == b'\0':
            return len(data)
        message = pb.ToSplitflap()
        message.ParseFromString(decode_frame(data[:-1]))
        self.commands.append(message)
        response = pb.FromSplitflap()
        response.ack.nonce = message.nonce
        if self.drop_acks:
            self.drop_acks -= 1
        else:
            self.emit(response)
        if message.WhichOneof('payload') == 'request_state':
            state = pb.FromSplitflap()
            state.splitflap_state.modules.add()
            state.splitflap_state.modules.add()
            state.splitflap_state.loopbacks_ok = True
            self.emit(state)
            general = pb.FromSplitflap()
            general.general_state.serial_protocol_version = 1
            general.general_state.flap_character_set = b' AB'
            self.emit(general)
        return len(data)

    def read(self, size):
        try:
            first = self.incoming.get(timeout=0.01)
        except Empty:
            return b''
        result = bytearray([first])
        while len(result) < size:
            try:
                result.append(self.incoming.get_nowait())
            except Empty:
                break
        return bytes(result)

    def close(self):
        self.closed = True


class SerialServiceTests(unittest.TestCase):
    def setUp(self):
        self.device = FakeSerial()
        self.service = SerialService(lambda *args, **kwargs: self.device)
        self.service.connect('fake')
        self.wait_for(lambda: self.service.snapshot()['connection'] == 'ready')

    def tearDown(self):
        self.service.disconnect()

    def wait_for(self, condition):
        deadline = time.monotonic() + 2
        while not condition():
            if time.monotonic() > deadline:
                self.fail('Timed out waiting for simulated device')
            time.sleep(0.01)

    def test_text_pads_and_rejects_unsupported_characters(self):
        self.service.display('B')
        self.wait_for(lambda: len(self.device.commands) >= 2)
        commands = self.device.commands[-1].splitflap_command.modules
        self.assertEqual([command.param for command in commands], [2, 0])
        self.assertEqual([command.action for command in commands], [1, 1])
        with self.assertRaises(ServiceError):
            self.service.display('Z')
        with self.assertRaises(ServiceError):
            self.service.display('ABA')

    def test_selected_home_uses_noop_for_other_modules(self):
        self.service.home([1])
        self.wait_for(lambda: len(self.device.commands) >= 2)
        actions = [item.action for item in self.device.commands[-1].splitflap_command.modules]
        self.assertEqual(actions, [0, pb.SplitflapCommand.ModuleCommand.RESET_AND_HOME])

    def test_selected_offset_and_invalid_indices(self):
        self.service.offset([0], 'half')
        self.wait_for(lambda: len(self.device.commands) >= 2)
        actions = [item.action for item in self.device.commands[-1].splitflap_command.modules]
        self.assertEqual(actions, [pb.SplitflapCommand.ModuleCommand.INCREASE_OFFSET_HALF, 0])
        with self.assertRaises(ServiceError):
            self.service.home([2])

    def test_offsets_are_optional_and_full_flap_is_rejected(self):
        self.assertIsNone(self.service.snapshot()['modules'][0]['offset_steps'])
        with self.assertRaises(ServiceError):
            self.service.offset([0], 'full')
        general = pb.FromSplitflap()
        general.general_state.serial_protocol_version = 2
        general.general_state.flap_character_set = b' AB'
        self.device.emit(general)
        state = pb.FromSplitflap()
        state.splitflap_state.modules.add().offset.steps = 0
        state.splitflap_state.modules.add().offset.steps = 123
        self.device.emit(state)
        self.wait_for(lambda: self.service.snapshot()['protocol_version'] == 2
                      and self.service.snapshot()['modules'][1]['offset_steps'] == 123)
        self.assertEqual(self.service.snapshot()['modules'][0]['offset_steps'], 0)
        with self.assertRaises(ServiceError):
            self.service.offset([1], 'full')

    def test_retry_uses_the_same_nonce(self):
        self.wait_for(lambda: not self.service.snapshot()['busy'])
        self.service.RETRY_INTERVAL = 0.02
        self.device.drop_acks = 1
        self.service.display('A')
        self.wait_for(lambda: len(self.device.commands) >= 3)
        self.wait_for(lambda: not self.service.snapshot()['busy'])
        self.assertEqual(self.device.commands[-2].nonce, self.device.commands[-1].nonce)

    def test_timeout_marks_connection_error(self):
        self.wait_for(lambda: not self.service.snapshot()['busy'])
        self.service.RETRY_INTERVAL = 0.02
        self.service.ACK_TIMEOUT = 0.12
        self.device.drop_acks = 100
        self.service.display('A')
        self.wait_for(lambda: self.service.snapshot()['connection'] == 'error')
        self.assertEqual(self.service.snapshot()['operations'][-1]['status'], 'unknown')

    def test_save_requires_log_confirmation(self):
        self.wait_for(lambda: not self.service.snapshot()['busy'])
        with self.service._lock:
            self.service._snapshot['modules'][1]['state'] = 'SENSOR_ERROR'
        operation_id = self.service.save_offsets()
        self.wait_for(lambda: self.service.snapshot()['operations'][-1]['status'] == 'waiting')
        response = pb.FromSplitflap()
        response.log.msg = 'SUCCESS - saved calibration!'
        self.device.emit(response)
        self.wait_for(lambda: self.service.snapshot()['operations'][-1]['status'] == 'completed')
        self.assertTrue(self.device.commands[-1].splitflap_command.save_all_offsets)
        self.assertEqual(len(self.device.commands[-1].splitflap_command.modules), 0)
        self.assertEqual(self.service.snapshot()['operations'][-1]['id'], operation_id)


if __name__ == '__main__':
    unittest.main()