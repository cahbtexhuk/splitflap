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
        self.settings = {'display_count': 10, 'alignment': 'left', 'flip_all': False}
        self.service.get_settings.return_value = self.settings
        self.service.update_settings.return_value = self.settings

    def test_blocks_untrusted_host_and_origin(self):
        self.assertEqual(self.client.get('/api/status', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/clear', json={}, headers={**self.headers, 'Origin': 'http://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/clear', json={}).status_code, 403)

    def test_connect_accepts_only_enumerated_port(self):
        with patch('app.list_ports.comports', return_value=[Mock(device='COM3', description='Device')]):
            self.assertEqual(self.client.post('/api/connect', json={'port': 'COM9'}, headers=self.headers).status_code, 400)
            self.assertEqual(self.client.post('/api/connect', json={'port': 'COM3'}, headers=self.headers).status_code, 200)
        self.service.connect.assert_called_once_with('COM3')

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


if __name__ == '__main__':
    unittest.main()