import pytest

from examples.delivery_agent.app import create_delivery_engine
from kelvi import Session


@pytest.mark.asyncio
async def test_delivery_agent_track_order_malayalam():
    engine = create_delivery_engine()
    session = Session(session_id="s1", language="ml-IN")

    result = await engine.process_turn(session, "എന്റെ ഓർഡർ എവിടെ എത്തി?")
    assert result.tool_executed == "track_order"
    assert "സുരേഷ്" in result.reply_text or "പുറപ്പെട്ടു" in result.reply_text
    assert result.xray["turn_id"] is not None
    assert result.xray["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_delivery_agent_cancellation_confirmation_flow():
    engine = create_delivery_engine()
    session = Session(session_id="s2", language="ml-IN")

    # Step 1: User asks to cancel order
    res_1 = await engine.process_turn(session, "ഓർഡർ ക്യാൻസൽ ചെയ്യണം")
    assert res_1.pending_confirmation is True
    assert "ഓർഡർ റദ്ദാക്കണമെന്ന് ഉറപ്പാണോ?" in res_1.reply_text

    # Step 2: User confirms in Malayalam
    res_2 = await engine.process_turn(session, "അതെ, റദ്ദാക്കിക്കോളൂ")
    assert res_2.tool_executed == "cancel_order"
    assert "റദ്ദാക്കി" in res_2.reply_text
    assert "₹340" in res_2.reply_text or "റീഫണ്ട്" in res_2.reply_text


@pytest.mark.asyncio
async def test_delivery_agent_cancellation_declined_flow():
    engine = create_delivery_engine()
    session = Session(session_id="s3", language="ml-IN")

    # Step 1: User asks to cancel order
    res_1 = await engine.process_turn(session, "ഓർഡർ ക്യാൻസൽ ചെയ്യണം")
    assert res_1.pending_confirmation is True

    # Step 2: User changes mind in Malayalam
    res_2 = await engine.process_turn(session, "വേണ്ട, റദ്ദാക്കണ്ട")
    assert res_2.tool_executed is None
    reply = res_2.reply_text
    assert any(term in reply for term in ["റദ്ദാക്കിയിട്ടില്ല", "റദ്ദാക്കിയിട്ടുണ്ട്", "റദ്ദാക്കണ്ട"])


@pytest.mark.asyncio
async def test_delivery_agent_call_partner():
    engine = create_delivery_engine()
    session = Session(session_id="s4", language="ml-IN")

    res = await engine.process_turn(session, "ഡെലിവറി പാർട്ണറെ വിളിക്കാമോ?")
    assert res.tool_executed == "call_delivery_partner"
    assert "കണക്ട് ചെയ്യുന്നു" in res.reply_text
