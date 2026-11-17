import sys
import tempfile
import time
import unittest
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import decode_frame, encode_frame
from serial_service import SerialService, ServiceError, pb


class FakeSerial:
    def __init__(self, *args, module_count=2, alphabet=b' AB', **kwargs):
        self.incoming = Queue()
        self.commands = []
        self.closed = False
        self.drop_acks = 0
        self.module_count = module_count
        self.alphabet = alphabet

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
            for _ in range(self.module_count):
                state.splitflap_state.modules.add()
            state.splitflap_state.loopbacks_ok = True
            self.emit(state)
            general = pb.FromSplitflap()
            general.general_state.serial_protocol_version = 1
            general.general_state.flap_character_set = self.alphabet
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
        self.settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.settings_dir.cleanup)
        self.settings_path = Path(self.settings_dir.name) / 'settings.json'
        self.service = SerialService(lambda *args, **kwargs: self.device, self.settings_path)
        self.service.update_settings({'display_count': 2})
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
        self.service.display('b')
        self.wait_for(lambda: len(self.device.commands) >= 2)
        commands = self.device.commands[-1].splitflap_command.modules
        self.assertEqual([command.param for command in commands], [2, 0])
        self.assertEqual([command.action for command in commands], [1, 0])
        with self.assertRaises(ServiceError):
            self.service.display('Z')
        with self.assertRaises(ServiceError):
            self.service.display('ABA')

    def test_selected_home_uses_noop_for_other_modules(self):
        self.service.home([1])
        self.wait_for(lambda: len(self.device.commands) >= 2)
        actions = [item.action for item in self.device.commands[-1].splitflap_command.modules]
        self.assertEqual(actions, [0, pb.SplitflapCommand.ModuleCommand.RESET_AND_HOME])

    def test_identical_message_does_not_send_again(self):
        self.service.display('B')
        self.wait_for(lambda: not self.service.snapshot()['busy'])
        command_count = len(self.device.commands)
        self.service.display('b')
        self.assertEqual(len(self.device.commands), command_count)
        self.assertEqual(self.service.snapshot()['operations'][-1]['status'], 'completed')

    def test_only_different_positions_move_for_sequential_messages(self):
        service_dir = Path(self.settings_dir.name)
        device = FakeSerial(module_count=10, alphabet=b' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        service = SerialService(lambda *args, **kwargs: device, service_dir / 'ten-drum.json')
        service.update_settings({'display_count': 10})
        service.connect('fake-10')
        self.addCleanup(service.disconnect)
        self.wait_for(lambda: service.snapshot()['connection'] == 'ready')

        service.display('0123456789')
        self.wait_for(lambda: not service.snapshot()['busy'])
        service.display('1113456789')
        self.wait_for(lambda: not service.snapshot()['busy'])

        actions = [item.action for item in device.commands[-1].splitflap_command.modules]
        params = [item.param for item in device.commands[-1].splitflap_command.modules]
        self.assertEqual(actions, [1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(params[0], 2)
        self.assertEqual(params[2], 2)

    def test_flip_all_forces_every_configured_drum(self):
        self.service.update_settings({'flip_all': True})
        self.service.display('')
        self.wait_for(lambda: len(self.device.commands) >= 2)
        actions = [item.action for item in self.device.commands[-1].splitflap_command.modules]
        self.assertEqual(actions, [pb.SplitflapCommand.ModuleCommand.GO_TO_FLAP] * 2)

    def test_alignment_and_host_settings_persist(self):
        self.service.update_settings({'alignment': 'right'})
        self.service.display('A')
        self.wait_for(lambda: len(self.device.commands) >= 2)
        commands = self.device.commands[-1].splitflap_command.modules
        self.assertEqual([item.action for item in commands], [0, 1])
        self.assertEqual([item.param for item in commands], [0, 1])
        restored = SerialService(settings_path=self.settings_path)
        self.assertEqual(restored.get_settings(), {
            'display_count': 2, 'alignment': 'right', 'flip_all': False,
            'default_prop_clock_time': '22:00'})

    def test_default_prop_clock_time_is_validated_and_persisted(self):
        self.service.update_settings({'default_prop_clock_time': '23:45'})
        restored = SerialService(settings_path=self.settings_path)
        self.assertEqual(restored.get_settings()['default_prop_clock_time'], '23:45')
        self.assertEqual(restored.get_clock_state(), {'start_time': '23:45', 'current_time': '23:45'})
        with self.assertRaises(ServiceError):
            self.service.update_settings({'default_prop_clock_time': '24:00'})
        with self.assertRaises(ServiceError):
            self.service.update_settings({'default_prop_clock_time': '8:05'})

    def make_clock_service(self):
        device = FakeSerial(module_count=10, alphabet=b' 0123456789:')
        settings_path = Path(self.settings_dir.name) / 'clock-settings.json'
        service = SerialService(lambda *args, **kwargs: device, settings_path)
        service.update_settings({'display_count': 10})
        service.connect('fake-clock')
        self.addCleanup(service.disconnect)
        self.wait_for(lambda: service.snapshot()['connection'] == 'ready')
        self.wait_for(lambda: not service.snapshot()['busy'])
        return service, device

    def test_prop_clock_override_reset_and_centered_output(self):
        service, device = self.make_clock_service()
        self.assertEqual(service.get_clock_state(), {'start_time': '22:00', 'current_time': '22:00'})

        result = service.set_clock_start('21:46')
        self.wait_for(lambda: not service.snapshot()['busy'])
        self.assertEqual(result['current_time'], '21:46')
        clock_command = device.commands[-1].splitflap_command.modules
        self.assertEqual([item.param for item in clock_command], [0, 0, 3, 2, 11, 5, 7, 0, 0, 0])

        result = service.add_clock_minutes(5)
        self.wait_for(lambda: not service.snapshot()['busy'])
        self.assertEqual(result['current_time'], '21:51')
        result = service.add_clock_hours(1)
        self.wait_for(lambda: not service.snapshot()['busy'])
        self.assertEqual(result['current_time'], '22:51')
        result = service.reset_clock()
        self.wait_for(lambda: not service.snapshot()['busy'])
        self.assertEqual(result['current_time'], '21:46')

    def test_prop_clock_minute_steps_and_midnight_wrap(self):
        service, _ = self.make_clock_service()
        result = service.set_clock_start('23:55')
        self.wait_for(lambda: not service.snapshot()['busy'])
        result = service.add_clock_minutes(10)
        self.wait_for(lambda: not service.snapshot()['busy'])
        self.assertEqual(result['current_time'], '00:05')

        for minutes in range(5, 60, 5):
            result = service.set_clock_start('22:00')
            self.wait_for(lambda: not service.snapshot()['busy'])
            result = service.add_clock_minutes(minutes)
            self.wait_for(lambda: not service.snapshot()['busy'])
            self.assertEqual(result['current_time'], f'22:{minutes:02d}')

        with self.assertRaises(ServiceError):
            service.add_clock_minutes(1)
        with self.assertRaises(ServiceError):
            service.add_clock_hours(3)

    def test_saved_default_change_does_not_replace_runtime_override(self):
        service, _ = self.make_clock_service()
        result = service.set_clock_start('21:46')
        self.wait_for(lambda: not service.snapshot()['busy'])
        service.update_settings({'default_prop_clock_time': '23:00'})
        self.assertEqual(service.get_clock_state(), {'start_time': '21:46', 'current_time': '21:46'})

    def test_prop_clock_requires_five_configured_drums(self):
        with self.assertRaisesRegex(ServiceError, 'at least 5'):
            self.service.set_clock_start('22:00')

    def test_configured_count_cannot_exceed_connected_hardware(self):
        with self.assertRaises(ServiceError):
            self.service.update_settings({'display_count': 3})

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