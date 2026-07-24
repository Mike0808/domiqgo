import billing.messengers.telegram as tg
from billing.messengers.telegram import TelegramAdapter

def test_parse_photo_picks_largest_size():
    update = {"message": {"chat": {"id": 42}, "photo": [
        {"file_id": "small"}, {"file_id": "big"}]}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.chat_id == "42"
    assert msg.file_id == "big"

def test_parse_document_keeps_filename():
    update = {"message": {"chat": {"id": 7},
              "document": {"file_id": "doc1", "file_name": "check.pdf"}}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.file_id == "doc1"
    assert msg.file_name == "check.pdf"

def test_parse_text_message():
    update = {"message": {"chat": {"id": 7}, "text": "/start abc"}}
    msg = TelegramAdapter(token="T").parse_update(update)
    assert msg.text == "/start abc"
    assert msg.file_id == ""

def test_parse_non_message_update_returns_none():
    assert TelegramAdapter(token="T").parse_update({"channel_post": {}}) is None

def test_send_message_posts_to_api(monkeypatch):
    calls = {}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {}
    def fake_post(url, json=None, timeout=None):
        calls["url"] = url; calls["json"] = json
        return Resp()
    monkeypatch.setattr(tg.requests, "post", fake_post)
    TelegramAdapter(token="T").send_message("42", "привет")
    assert calls["url"].endswith("/botT/sendMessage")
    assert calls["json"] == {"chat_id": "42", "text": "привет"}

def test_download_file_two_step(monkeypatch):
    class Resp:
        def __init__(self, js=None, content=b""): self._js = js; self.content = content
        def raise_for_status(self): pass
        def json(self): return self._js
    def fake_get(url, params=None, timeout=None):
        if "getFile" in url:
            return Resp(js={"result": {"file_path": "photos/x.jpg"}})
        return Resp(content=b"IMG")
    monkeypatch.setattr(tg.requests, "get", fake_get)
    data = TelegramAdapter(token="T").download_file("fid")
    assert data == b"IMG"
