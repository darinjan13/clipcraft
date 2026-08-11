"""Simple HTTP server that wraps render_video.py for n8n workflow."""
import http.server
import json
import subprocess
import sys
import os
import re
import signal
import traceback
from urllib.parse import urlparse, parse_qs
from datetime import datetime

RENDER_SCRIPT = '/opt/video-tools/render_video.py'
JOB_DIR = '/data/jobs'

class RenderHandler(http.server.BaseHTTPRequestHandler):
    def _log(self, msg):
        ts = datetime.now().isoformat()
        with open('/tmp/render_server_debug.log', 'a') as f:
            f.write(f'[{ts}] {msg}\n')
            f.flush() # Ensure buffer is flushed

    def _parse_body(self, body_bytes, content_type):
        ct = (content_type or '').lower()
        if 'application/json' in ct or not ct:
            return json.loads(body_bytes) if body_bytes else {}
        if 'application/x-www-form-urlencoded' in ct:
            parsed = parse_qs(body_bytes.decode('utf-8', errors='replace'))
            return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return {}

    def do_POST(self):
        path = urlparse(self.path).path
        self._log(f'POST {path} from {self.client_address}')
        self._log(f'Headers: {dict(self.headers)}')

        if path != '/render':
            self._log(f'404 - path mismatch: {path}')
            self.send_error(404, 'Not Found')
            return

        length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(length) if length > 0 else b'{}'
        self._log(f'Body ({length} bytes): {body_bytes[:500]}')

        try:
            data = self._parse_body(body_bytes, self.headers.get('Content-Type', ''))
        except Exception as e:
            self._log(f'JSON parse error: {e}')
            self._respond(400, {'success': False, 'error': f'Invalid JSON: {e}'})
            return

        job_id = data.get('jobId', '')
        self._log(f'Parsed data: {json.dumps(data)[:200]}')

        if not job_id or not re.match(r'^[0-9a-f-]{36}$', job_id, re.I):
            self._log(f'Invalid jobId: {job_id}')
            self._respond(400, {'success': False, 'error': f'Invalid jobId: {job_id}'})
            return

        try:
            result = subprocess.run(
                ['python3', RENDER_SCRIPT, job_id],
                capture_output=True, text=True, timeout=600, cwd=JOB_DIR
            )

            output_path = os.path.join(JOB_DIR, job_id, 'final.mp4')
            thumb_path = os.path.join(JOB_DIR, job_id, 'thumbnail.jpg')

            if result.returncode != 0:
                self._respond(500, {
                    'success': False,
                    'error': result.stderr[:1000],
                    'stdout': result.stdout[:1000]
                })
                return

            video_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            thumb_size = os.path.getsize(thumb_path) if os.path.exists(thumb_path) else 0

            self._respond(200, {
                'success': True,
                'jobId': job_id,
                'videoUrl': output_path,
                'thumbnailUrl': thumb_path if os.path.exists(thumb_path) else '',
                'videoSize': video_size,
                'thumbSize': thumb_size
            })
        except subprocess.TimeoutExpired:
            self._respond(504, {'success': False, 'error': 'Render timed out'})
        except Exception as e:
            self._respond(500, {'success': False, 'error': str(e)[:1000]})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self._respond(200, {'status': 'ok'})
        else:
            self.send_error(404, 'Not Found')

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        print(f"[render-server] {args[0]}" if args else fmt)


if __name__ == '__main__':
    port = int(os.environ.get('RENDER_SERVER_PORT', '8088'))
    server = http.server.HTTPServer(('0.0.0.0', port), RenderHandler)
    print(f'Render server listening on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down...')
        server.shutdown()
