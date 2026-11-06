import argparse
import atexit
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory
from serial.tools import list_ports
from waitress import serve

from serial_service import SerialService, ServiceError


def create_app(service=None, allowed_hosts=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = 4096
    app.config['ALLOWED_HOSTS'] = {'localhost', '127.0.0.1', '::1'} | set(allowed_hosts or [])
    controller = service or SerialService()
    app.extensions['splitflap'] = controller

    @app.before_request
    def protect_requests():
        try:
            hostname = urlsplit('//' + request.host).hostname
        except ValueError:
            hostname = None
        if hostname not in app.config['ALLOWED_HOSTS']:
            return jsonify(error='Host is not allowed'), 403
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
                return jsonify(error='Origin is not allowed'), 403
            if not request.is_json or request.headers.get('X-Splitflap-Request') != '1':
                return jsonify(error='JSON and request header required'), 403

    @app.errorhandler(ServiceError)
    def service_error(error):
        return jsonify(error=str(error)), 400

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ServiceError('Expected a JSON object')
        return data

    @app.get('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.get('/api/ports')
    def ports():
        return jsonify([{'device': port.device, 'description': port.description}
                        for port in list_ports.comports()])

    @app.get('/api/status')
    def status():
        return jsonify(controller.snapshot())

    @app.post('/api/connect')
    def connect():
        data = body()
        port = data.get('port')
        if not isinstance(port, str) or port not in {item.device for item in list_ports.comports()}:
            raise ServiceError('Select an available serial port')
        controller.connect(port)
        return jsonify(ok=True)

    @app.post('/api/disconnect')
    def disconnect():
        controller.disconnect()
        return jsonify(ok=True)

    @app.post('/api/state/request')
    def refresh():
        return jsonify(operation=controller.request_state())

    @app.post('/api/display')
    def display():
        data = body()
        return jsonify(operation=controller.display(data.get('text')))

    @app.post('/api/clear')
    def clear():
        return jsonify(operation=controller.display(''))

    @app.post('/api/home')
    def home():
        data = body()
        return jsonify(operation=controller.home(data.get('modules')))

    @app.post('/api/offset')
    def offset():
        data = body()
        return jsonify(operation=controller.offset(data.get('modules'), data.get('adjustment')))

    @app.post('/api/offset/save')
    def save_offsets():
        return jsonify(operation=controller.save_offsets())

    return app


def main():
    parser = argparse.ArgumentParser(description='Splitflap web controller')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--allowed-host', action='append', default=[],
                        help='Host name or IP used by browsers; repeat for multiple hosts')
    args = parser.parse_args()
    hosts = args.allowed_host + ([args.host] if args.host not in ('0.0.0.0', '::') else [])
    app = create_app(allowed_hosts=hosts)
    atexit.register(app.extensions['splitflap'].disconnect)
    print(f'Splitflap controller listening on http://{args.host}:{args.port}', flush=True)
    serve(app, host=args.host, port=args.port, threads=4)


if __name__ == '__main__':
    main()