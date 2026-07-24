import pytest
from billing.messengers.base import MessengerAdapter, IncomingMessage
from billing.messengers.max import MaxAdapter

def test_incoming_message_defaults():
    m = IncomingMessage(platform="telegram", chat_id="1")
    assert m.text == "" and m.file_id == "" and m.file_name == ""

def test_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MessengerAdapter()

def test_max_adapter_conforms_but_is_deferred():
    a = MaxAdapter()
    assert a.platform == "max"
    with pytest.raises(NotImplementedError):
        a.send_message("1", "hi")
