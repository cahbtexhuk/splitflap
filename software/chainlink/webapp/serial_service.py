import copy
import secrets
import sys
import threading
import time
from collections import deque
from pathlib import Path
from queue import Empty, Full, Queue

import serial
from google.protobuf.message import DecodeError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'proto_gen'))
import splitflap_pb2 as pb

from protocol import decode_frame, encode_frame


class ServiceError(Exception):
    pass


def open_serial(port, baudrate, timeout, write_timeout):
    connection = serial.Serial(port=None, baudrate=baudrate, timeout=timeout, write_timeout=write_timeout)
    connection.dtr = False
    connection.rts = False
    connection.port = port
    connection.open()
    return connection


class SerialService:
    BAUD = 230400
    RETRY_INTERVAL = 0.25
    ACK_TIMEOUT = 8.0
    STATE_TIMEOUT = 10.0
    SAVE_TIMEOUT = 10.0
    MAX_FRAME = 16384

    def __init__(self, serial_factory=open_serial):
        self._serial_factory = serial_factory
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._port = None
        self._queue = Queue(maxsize=10)
        self._nonce = secrets.randbelow(0xFFFFFFFF) + 1
        self._operation_id = 0
        self._pending = None
        self._save_id = None
        self._save_deadline = None
        self._state_time = None
        self._snapshot = self._empty_snapshot()

    @staticmethod
    def _empty_snapshot():
        return {'connection': 'disconnected', 'port': None, 'error': None,
                'modules': [], 'loopbacks_ok': None, 'alphabet': None,
                'protocol_version': None, 'build': None, 'uptime_millis': None,
                'updated_at': None, 'logs': [], 'operations': []}

    def connect(self, port):
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise ServiceError('Already connected or connecting')
            try:
                connection = self._serial_factory(port, self.BAUD, timeout=0.05, write_timeout=1)
            except (serial.SerialException, OSError) as error:
                raise ServiceError(str(error)) from error
            self._port = connection
            self._queue = Queue(maxsize=10)
            self._pending = None
            self._save_id = None
            self._save_deadline = None
            self._state_time = None
            self._stop = threading.Event()
            self._snapshot = self._empty_snapshot()
            self._snapshot.update(connection='connecting', port=port)
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def disconnect(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
            if thread.is_alive():
                raise ServiceError('Serial worker did not stop')
        with self._lock:
            self._snapshot['connection'] = 'disconnected'

    def snapshot(self):
        with self._lock:
            result = copy.deepcopy(self._snapshot)
            result['stale'] = self._state_time is None or time.monotonic() - self._state_time > self.STATE_TIMEOUT
            result['busy'] = self._pending is not None or not self._queue.empty() or self._save_id is not None
            return result

    def _operation(self, label):
        self._operation_id += 1
        operation = {'id': self._operation_id, 'label': label, 'status': 'queued', 'detail': None}
        self._snapshot['operations'].append(operation)
        self._snapshot['operations'] = self._snapshot['operations'][-50:]
        return operation

    def _set_operation(self, operation_id, status, detail=None):
        for operation in self._snapshot['operations']:
            if operation['id'] == operation_id:
                operation.update(status=status, detail=detail)
                break

    def _enqueue(self, message, label, internal=False):
        with self._lock:
            if not internal:
                self._require_ready()
                if self._save_id is not None:
                    raise ServiceError('Waiting for offset save result')
            operation = self._operation(label)
            try:
                self._queue.put_nowait((message, operation['id']))
            except Full as error:
                self._set_operation(operation['id'], 'failed', 'Command queue is full')
                raise ServiceError('Command queue is full') from error
            return operation['id']

    def _require_ready(self):
        if self._snapshot['connection'] != 'ready':
            raise ServiceError('Device is not ready')
        if self._state_time is None or time.monotonic() - self._state_time > self.STATE_TIMEOUT:
            raise ServiceError('Device status is stale')

    def request_state(self):
        message = pb.ToSplitflap()
        message.request_state.SetInParent()
        return self._enqueue(message, 'Request status')

    def display(self, text):
        with self._lock:
            self._require_ready()
            if not isinstance(text, str):
                raise ServiceError('Text must be a string')
            alphabet = self._snapshot['alphabet']
            count = len(self._snapshot['modules'])
            if len(text) > count:
                raise ServiceError('Text is longer than the display')
            unsupported = sorted(set(text) - set(alphabet))
            if unsupported:
                raise ServiceError('Unsupported characters: ' + ', '.join(unsupported))
            positions = [alphabet.index(character) for character in text.ljust(count)]
            return self._module_commands(range(count), pb.SplitflapCommand.ModuleCommand.GO_TO_FLAP,
                                         positions, 'Display text')

    def home(self, modules):
        return self._module_commands(modules, pb.SplitflapCommand.ModuleCommand.RESET_AND_HOME, label='Re-home')

    def offset(self, modules, adjustment):
        actions = {'tenth': pb.SplitflapCommand.ModuleCommand.INCREASE_OFFSET_TENTH,
                   'half': pb.SplitflapCommand.ModuleCommand.INCREASE_OFFSET_HALF,
                   'set': pb.SplitflapCommand.ModuleCommand.SET_OFFSET}
        if not isinstance(adjustment, str) or adjustment not in actions:
            raise ServiceError('Invalid offset adjustment')
        return self._module_commands(modules, actions[adjustment], label='Adjust offset')

    def _module_commands(self, modules, action, positions=None, label='Command'):
        with self._lock:
            self._require_ready()
            count = len(self._snapshot['modules'])
            if not isinstance(modules, (list, tuple, range)) or not modules:
                raise ServiceError('Select at least one module')
            if any(type(index) is not int or index < 0 or index >= count for index in modules):
                raise ServiceError('Invalid module index')
            message = pb.ToSplitflap()
            selected = set(modules)
            for index in range(count):
                command = message.splitflap_command.modules.add()
                if index in selected:
                    command.action = action
                    if positions is not None:
                        command.param = positions[index]
            return self._enqueue(message, label)

    def save_offsets(self):
        with self._lock:
            self._require_ready()
            if self._pending is not None or not self._queue.empty() or self._save_id is not None:
                raise ServiceError('Wait for pending commands before saving')
            if any(module['moving'] or module['state'] == 'LOOK_FOR_HOME' for module in self._snapshot['modules']):
                raise ServiceError('All modules must be stopped and out of homing before saving')
            message = pb.ToSplitflap()
            message.splitflap_command.save_all_offsets = True
            operation_id = self._enqueue(message, 'Save offsets')
            self._save_id = operation_id
            self._save_deadline = time.monotonic() + self.SAVE_TIMEOUT
            return operation_id

    def _run(self):
        buffer = bytearray()
        try:
            self._port.write(b'\0')
            message = pb.ToSplitflap()
            message.request_state.SetInParent()
            self._enqueue(message, 'Initial status', internal=True)
            started = time.monotonic()
            while not self._stop.is_set():
                now = time.monotonic()
                with self._lock:
                    if self._snapshot['connection'] == 'connecting' and now - started > self.ACK_TIMEOUT + 3:
                        raise ServiceError('Timed out waiting for compatible device status')
                    if self._save_id is not None and now > self._save_deadline:
                        self._set_operation(self._save_id, 'unknown', 'No save confirmation received')
                        self._save_id = None
                    if self._pending is None:
                        try:
                            message, operation_id = self._queue.get_nowait()
                        except Empty:
                            pass
                        else:
                            message.nonce = self._nonce
                            self._nonce = (self._nonce + 1) & 0xFFFFFFFF
                            self._pending = {'id': operation_id, 'nonce': message.nonce,
                                             'frame': encode_frame(message.SerializeToString()),
                                             'started': now, 'last_sent': 0}
                    if self._pending:
                        if now - self._pending['started'] > self.ACK_TIMEOUT:
                            raise ServiceError('Device did not acknowledge command')
                        if now - self._pending['last_sent'] >= self.RETRY_INTERVAL:
                            self._port.write(self._pending['frame'])
                            self._pending['last_sent'] = now
                            self._set_operation(self._pending['id'], 'sent')
                data = self._port.read(256)
                for byte in data:
                    if byte == 0:
                        if buffer:
                            self._process_frame(bytes(buffer))
                        buffer.clear()
                    elif len(buffer) < self.MAX_FRAME:
                        buffer.append(byte)
                    else:
                        buffer.clear()
        except (serial.SerialException, OSError, ServiceError) as error:
            with self._lock:
                self._snapshot['error'] = str(error)
                self._snapshot['connection'] = 'error'
        finally:
            with self._lock:
                if self._pending:
                    self._set_operation(self._pending['id'], 'unknown', 'Connection closed before acknowledgement')
                    self._pending = None
                while not self._queue.empty():
                    _, operation_id = self._queue.get_nowait()
                    self._set_operation(operation_id, 'failed', 'Connection closed')
                if self._save_id is not None:
                    self._set_operation(self._save_id, 'unknown', 'Connection closed before save confirmation')
                    self._save_id = None
                if self._snapshot['connection'] != 'error':
                    self._snapshot['connection'] = 'disconnected'
            if self._port:
                self._port.close()

    def _process_frame(self, frame):
        try:
            message = pb.FromSplitflap()
            message.ParseFromString(decode_frame(frame))
        except (ValueError, DecodeError):
            return
        kind = message.WhichOneof('payload')
        with self._lock:
            if kind == 'ack' and self._pending and message.ack.nonce == self._pending['nonce']:
                operation_id = self._pending['id']
                if operation_id != self._save_id:
                    self._set_operation(operation_id, 'acknowledged', 'Received by device; execution is not confirmed')
                else:
                    self._set_operation(operation_id, 'waiting', 'Waiting for firmware save result')
                self._pending = None
            elif kind == 'splitflap_state':
                states = pb.SplitflapState.ModuleState.State
                self._snapshot['modules'] = [
                    {'index': index, 'state': states.Name(module.state), 'flap_index': module.flap_index,
                     'moving': module.moving, 'home_state': module.home_state,
                     'count_missed_home': module.count_missed_home,
                     'count_unexpected_home': module.count_unexpected_home}
                    for index, module in enumerate(message.splitflap_state.modules)]
                self._snapshot['loopbacks_ok'] = message.splitflap_state.loopbacks_ok
                self._state_time = time.monotonic()
                self._snapshot['updated_at'] = time.time()
            elif kind == 'general_state':
                state = message.general_state
                try:
                    alphabet = state.flap_character_set.decode('utf-8')
                except UnicodeDecodeError:
                    alphabet = ''
                self._snapshot.update(protocol_version=state.serial_protocol_version,
                                      alphabet=alphabet, uptime_millis=state.uptime_millis,
                                      build={'git_hash': state.build_info.git_hash,
                                             'date': state.build_info.build_date,
                                             'os': state.build_info.build_os})
                if state.serial_protocol_version != 1 or ' ' not in alphabet or not alphabet.isascii():
                    self._snapshot['error'] = 'Unsupported protocol version or missing blank flap'
                    self._snapshot['connection'] = 'error'
                    self._stop.set()
            elif kind == 'log':
                text = message.log.msg
                self._snapshot['logs'].append({'time': time.time(), 'message': text})
                self._snapshot['logs'] = self._snapshot['logs'][-100:]
                if self._save_id is not None:
                    if 'SUCCESS - saved calibration!' in text:
                        self._set_operation(self._save_id, 'completed', text)
                        self._save_id = None
                    elif 'failed to save calibration' in text or "Can't save offsets" in text:
                        self._set_operation(self._save_id, 'failed', text)
                        self._save_id = None
            if (self._snapshot['connection'] == 'connecting' and self._snapshot['modules']
                    and self._snapshot['protocol_version'] == 1 and self._snapshot['alphabet']):
                self._snapshot['connection'] = 'ready'