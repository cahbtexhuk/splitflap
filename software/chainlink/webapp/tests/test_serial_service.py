import sys
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import decode_frame, encode_frame
from serial_service import SerialService, ServiceError, SocketTransport, pb


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
            'display_count': 2, 'alignment': 'right', 'flip_all': False})

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

    def test_socket_timeout_and_eof_are_distinct(self):
        local_socket, remote_socket = socket.socketpair()
        transport = SocketTransport(local_socket, 0.01, 1)
        self.addCleanup(transport.close)
        self.addCleanup(remote_socket.close)
        self.assertEqual(transport.read(10), b'')
        remote_socket.sendall(b'hello')
        self.assertEqual(transport.read(10), b'hello')
        self.assertEqual(transport.write(b'world'), 5)
        self.assertEqual(remote_socket.recv(10), b'world')
        remote_socket.close()
        with self.assertRaises(ConnectionError):
            transport.read(10)

    def test_network_connection_reuses_protocol_and_handles_eof(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        accepted = Queue()
        received = Queue()

        def fake_network_device():
            buffer = bytearray()
            try:
                remote_socket, _ = listener.accept()
                accepted.put(remote_socket)
                while True:
                    data = remote_socket.recv(256)
                    if not data:
                        break
                    for byte in data:
                        if byte:
                            buffer.append(byte)
                        elif buffer:
                            message = pb.ToSplitflap()
                            message.ParseFromString(decode_frame(bytes(buffer)))
                            buffer.clear()
                            received.put(message)
                            ack = pb.FromSplitflap()
                            ack.ack.nonce = message.nonce
                            frame = encode_frame(ack.SerializeToString())
                            remote_socket.sendall(frame[:2])
                            remote_socket.sendall(frame[2:])
                            if (message.WhichOneof('payload') == 'splitflap_command'
                                    and message.splitflap_command.save_all_offsets):
                                log = pb.FromSplitflap()
                                log.log.msg = 'SUCCESS - saved calibration!'
                                remote_socket.sendall(encode_frame(log.SerializeToString()))
                            if message.WhichOneof('payload') == 'request_state':
                                status = pb.FromSplitflap()
                                status.splitflap_state.modules.add()
                                status.splitflap_state.modules.add()
                                status.splitflap_state.loopbacks_ok = True
                                general = pb.FromSplitflap()
                                general.general_state.serial_protocol_version = 1
                                general.general_state.flap_character_set = b' AB'
                                remote_socket.sendall(encode_frame(status.SerializeToString())
                                                      + encode_frame(general.SerializeToString()))
            except OSError:
                pass

        worker = threading.Thread(target=fake_network_device, daemon=True)
        worker.start()
        service = SerialService(settings_path=Path(self.settings_dir.name) / 'network.json')
        service.update_settings({'display_count': 2})
        self.addCleanup(service.disconnect)
        service.connect_network('localhost', listener.getsockname()[1])
        remote_socket = accepted.get(timeout=2)
        self.addCleanup(remote_socket.close)
        self.wait_for(lambda: service.snapshot()['connection'] == 'ready')
        self.assertEqual(service.snapshot()['transport'], 'network')
        service.display('B')
        self.wait_for(lambda: received.qsize() >= 2)
        request = received.get_nowait()
        command = received.get_nowait()
        self.assertEqual(request.WhichOneof('payload'), 'request_state')
        self.assertEqual(command.splitflap_command.modules[0].param, 2)
        self.wait_for(lambda: not service.snapshot()['busy'])
        service.home([1])
        service.offset([0], 'half')
        self.wait_for(lambda: not service.snapshot()['busy'])
        home = received.get(timeout=2)
        offset = received.get(timeout=2)
        self.assertEqual(home.splitflap_command.modules[1].action,
                 pb.SplitflapCommand.ModuleCommand.RESET_AND_HOME)
        self.assertEqual(offset.splitflap_command.modules[0].action,
                 pb.SplitflapCommand.ModuleCommand.INCREASE_OFFSET_HALF)
        service.save_offsets()
        self.wait_for(lambda: service.snapshot()['operations'][-1]['status'] == 'completed')
        self.assertTrue(received.get(timeout=2).splitflap_command.save_all_offsets)
        remote_socket.shutdown(socket.SHUT_RDWR)
        remote_socket.close()
        self.wait_for(lambda: service.snapshot()['connection'] == 'error')
        self.assertIn('closed', service.snapshot()['error'])

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