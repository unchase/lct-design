import asyncio
import httpx
import pytest
from lct_design.deadline import Deadline,BudgetExpired
from lct_design import provider

def test_shared_remaining_budget():
    now=[5.0];d=Deadline(300,clock=lambda:now[0]);now[0]+=280
    assert d.remaining(75)==20
    now[0]+=21
    with pytest.raises(BudgetExpired):d.remaining()

def test_http_trickling_cannot_extend_total_deadline(monkeypatch):
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(.01);yield b' '
    monkeypatch.setattr(provider,'TRANSPORT',httpx.MockTransport(lambda r:httpx.Response(200,stream=Slow())))
    with pytest.raises(BudgetExpired):provider.request(provider.ProviderConfig(base_url='https://example.org'),'/models',deadline=Deadline(.05))
