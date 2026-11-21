import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.app = create_app(self.service)
        self.client = self.app.test_client()
        self.headers = {'X-Splitflap-Request': '1'}
        self.settings = {
            'display_count': 10, 'alignment': 'left', 'flip_all': False,
            'default_prop_clock_time': '22:00'}
        self.service.get_settings.return_value = self.settings
        self.service.update_settings.return_value = self.settings
        self.clock_state = {'start_time': '22:00', 'current_time': '22:00'}
        self.service.get_clock_state.return_value = self.clock_state

    def test_blocks_untrusted_host_and_origin(self):
        self.assertEqual(self.client.get('/api/status', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/clear', json={}, headers={**self.headers, 'Origin': 'http://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/clear', json={}).status_code, 403)

    def test_connect_accepts_only_enumerated_port(self):
        with patch('app.list_ports.comports', return_value=[Mock(device='COM3', description='Device')]):
            self.assertEqual(self.client.post('/api/connect', json={'port': 'COM9'}, headers=self.headers).status_code, 400)
            self.assertEqual(self.client.post('/api/connect', json={'port': 'COM3'}, headers=self.headers).status_code, 200)
        self.service.connect.assert_called_once_with('COM3')

    def test_network_connect_validates_endpoint(self):
        for host, port in [('http://example.com', 23040), ('', 23040), ('localhost', 0), ('localhost', True)]:
            response = self.client.post('/api/connect', json={'transport': 'network', 'host': host,
                                                               'network_port': port}, headers=self.headers)
            self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/connect', json={'transport': 'network', 'host': 'splitflap.local',
                                                           'network_port': 23040}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.service.connect_network.assert_called_once_with('splitflap.local', 23040)

    def test_clear_is_blank_text(self):
        self.service.display.return_value = 1
        response = self.client.post('/api/clear', json={}, headers=self.headers)
        self.assertEqual(response.get_json()['operation'], 1)
        self.service.display.assert_called_once_with('')

    def test_rejects_non_object_request(self):
        self.assertEqual(self.client.post('/api/display', json=['invalid'], headers=self.headers).status_code, 400)

    def test_settings_routes(self):
        self.assertEqual(self.client.get('/api/settings').get_json()['display_count'], 10)
        response = self.client.post('/api/settings', json={'flip_all': True}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.service.update_settings.assert_called_once_with({'flip_all': True})

    def test_default_clock_time_can_be_configured_through_settings_api(self):
        response = self.client.post(
            '/api/settings', json={'default_prop_clock_time': '23:45'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.service.update_settings.assert_called_once_with({'default_prop_clock_time': '23:45'})

    def test_clock_get_and_actions(self):
        self.service.set_clock_start.return_value = {
            'start_time': '21:46', 'current_time': '21:46', 'operation': 12}
        self.service.add_clock_minutes.return_value = {
            'start_time': '21:46', 'current_time': '21:51', 'operation': 13}
        self.service.add_clock_hours.return_value = {
            'start_time': '21:46', 'current_time': '22:51', 'operation': 14}
        self.service.reset_clock.return_value = {
            'start_time': '21:46', 'current_time': '21:46', 'operation': 15}

        self.assertEqual(self.client.get('/api/clock').get_json(), self.clock_state)
        response = self.client.post('/api/clock/set-start', json={'time': '21:46'}, headers=self.headers)
        self.assertEqual(response.get_json()['operation'], 12)
        self.service.set_clock_start.assert_called_once_with('21:46')

        response = self.client.post('/api/clock/add-minutes', json={'minutes': 55}, headers=self.headers)
        self.assertEqual(response.get_json()['current_time'], '21:51')
        self.service.add_clock_minutes.assert_called_once_with(55)

        response = self.client.post('/api/clock/add-hours', json={'hours': 2}, headers=self.headers)
        self.assertEqual(response.get_json()['operation'], 14)
        self.service.add_clock_hours.assert_called_once_with(2)

        response = self.client.post('/api/clock/reset', json={}, headers=self.headers)
        self.assertEqual(response.get_json()['operation'], 15)
        self.service.reset_clock.assert_called_once_with()

    def test_clock_rejects_invalid_actions(self):
        invalid_requests = (
            ('/api/clock/set-start', {'time': '24:00'}),
            ('/api/clock/add-minutes', {'minutes': 4}),
            ('/api/clock/add-minutes', {'minutes': '5'}),
            ('/api/clock/add-hours', {'hours': 3}),
        )
        for path, payload in invalid_requests:
            with self.subTest(path=path, payload=payload):
                response = self.client.post(path, json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.get_json())


if __name__ == '__main__':
    unittest.main()