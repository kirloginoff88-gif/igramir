"""Serve the Mini App and forward its requests to a Telegram manager chat."""
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "dist"
MAX_BODY = 15 * 1024 * 1024


def verify_init_data(raw, token, now=None):
    pairs = urllib.parse.parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Repeated Telegram fields")
    received = fields.pop("hash", "")
    payload = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    key = hmac.digest(b"WebAppData", token.encode(), "sha256")
    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError("Invalid Telegram signature")
    age = (time.time() if now is None else now) - int(fields["auth_date"])
    if not -60 <= age <= 3600:
        raise ValueError("Expired Telegram session")
    user = json.loads(fields["user"])
    if not isinstance(user.get("id"), int):
        raise ValueError("Missing Telegram user")
    return user


def read_request(content_type, body):
    if not content_type.startswith("multipart/form-data;"):
        raise ValueError("Expected a multipart form")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\n\r\n" + body
    )
    parts = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name not in {"details", "original", "preview"} or name in parts:
            raise ValueError("Unexpected form field")
        parts[name] = part.get_payload(decode=True)
    details = json.loads(parts.pop("details"))
    for name, data in parts.items():
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        elif name == "original" and data.startswith(b"\xff\xd8\xff"):
            extension = "jpg"
        elif name == "original" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            extension = "webp"
        else:
            raise ValueError("Invalid image")
        parts[name] = (f"{name}.{extension}", data)
    if "preview" not in parts:
        raise ValueError("Missing preview")
    return details, parts


def clean(value, maximum):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Required value")
    return " ".join(value.split())[:maximum]


def caption(payload, user):
    details, concept = payload["details"], payload["concept"]
    quantity, size = int(details["quantity"]), int(concept["size"])
    if not 150 <= quantity <= 10_000_000 or not 1 <= size <= 300:
        raise ValueError("Quantity or size outside range")
    email = clean(details["email"], 150)
    if "@" not in email:
        raise ValueError("Invalid email")
    return "\n".join([
        "Заявка на расчёт · Играмир",
        f"Компания: {clean(details['company'], 120)}",
        f"Тираж: {quantity} шт. · Размер: {size} см",
        f"Фактура: {clean(concept['fabric'], 60)}",
        f"Email: {email}",
        f"Telegram ID: {user['id']}",
    ])


class Telegram:
    def __init__(self, token):
        self.token = token

    def call(self, method, payload, files=None):
        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload).encode()
        if files:
            boundary = uuid.uuid4().hex
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            chunks = []
            for name, value in payload.items():
                if not isinstance(value, str):
                    value = json.dumps(value)
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
            for name, (filename, data) in files.items():
                chunks.extend([
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n'.encode(),
                    data,
                    b"\r\n",
                ])
            body = b"".join(chunks) + f"--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}", body, headers
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the request")
        return result["result"]

    def deliver(self, chat_id, text, files):
        if "original" in files:
            self.call("sendMediaGroup", {"chat_id": chat_id, "media": [
                {"type": "document", "media": "attach://preview", "caption": text},
                {"type": "document", "media": "attach://original"},
            ]}, files)
        else:
            self.call("sendDocument", {
                "chat_id": chat_id, "document": "attach://preview", "caption": text,
            }, files)

    def poll(self, app_url):
        offset = None
        while True:
            try:
                options = {"timeout": 25, "allowed_updates": ["message"]}
                if offset is not None:
                    options["offset"] = offset
                for update in self.call("getUpdates", options):
                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    command = message.get("text", "").split(maxsplit=1)
                    if command and command[0] == "/start" and chat.get("type") == "private":
                        self.call("sendMessage", {
                            "chat_id": chat["id"],
                            "text": "Загрузите эскиз, посмотрите концепт и запросите расчёт тиража.",
                            "reply_markup": {"inline_keyboard": [[{
                                "text": "Открыть визуализатор", "web_app": {"url": app_url},
                            }]]},
                        })
                    offset = update["update_id"] + 1
            except (OSError, RuntimeError, ValueError):
                print("Telegram polling will retry.", file=sys.stderr)
                time.sleep(3)


def make_handler(bot, manager_chat_id, app_origin=None):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def end_headers(self):
            if app_origin and self.headers.get("Origin") == app_origin:
                self.send_header("Access-Control-Allow-Origin", app_origin)
                self.send_header("Vary", "Origin")
            super().end_headers()

        def do_OPTIONS(self):
            if (self.path != "/api/telegram/requests" or not app_origin
                    or self.headers.get("Origin") != app_origin):
                self.send_error(403)
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "X-Telegram-Init-Data, Content-Type")
            self.end_headers()

        def send(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                     "/config.js": ("config.js", "text/javascript")}
            if path not in files:
                self.send_error(404)
                return
            name, mime = files[path]
            self.send(200, mime + "; charset=utf-8", (STATIC / name).read_bytes())

        def do_POST(self):
            if self.path != "/api/telegram/requests":
                self.send_error(404)
                return
            try:
                user = verify_init_data(self.headers.get("X-Telegram-Init-Data", ""), bot.token)
            except (AttributeError, KeyError, TypeError, ValueError):
                self.send_error(401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.send_error(413)
                    return
                payload, files = read_request(self.headers.get("Content-Type", ""), self.rfile.read(length))
                text = caption(payload, user)
            except (AttributeError, KeyError, TypeError, ValueError, OSError):
                self.send_error(400)
                return
            try:
                bot.deliver(manager_chat_id, text, files)
            except (OSError, RuntimeError, ValueError):
                self.send_error(502)
                return
            self.send(200, "application/json", b'{"ok":true}')

    return Handler


def main():
    token = os.environ["IGRAMIR_TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["IGRAMIR_TELEGRAM_MANAGER_CHAT"]
    app_url = os.environ["IGRAMIR_TELEGRAM_APP_URL"]
    parsed = urllib.parse.urlsplit(app_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        sys.exit("IGRAMIR_TELEGRAM_APP_URL must be the public HTTPS address of the Mini App.")
    bot = Telegram(token)
    try:
        bot.call("setChatMenuButton", {"menu_button": {
            "type": "web_app", "text": "Визуализатор", "web_app": {"url": app_url},
        }})
    except (OSError, RuntimeError, ValueError):
        sys.exit("Could not configure the Telegram menu. Check the bot token and HTTPS URL.")
    server = ThreadingHTTPServer(("127.0.0.1", int(os.getenv("IGRAMIR_PORT", "8080"))), make_handler(bot, chat_id, f"{parsed.scheme}://{parsed.netloc}"))
    threading.Thread(target=bot.poll, args=(app_url,), daemon=True).start()
    print(f"Играмир Mini App listens on {server.server_address[1]}.")
    server.serve_forever()


if __name__ == "__main__":
    main()
