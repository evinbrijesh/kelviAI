from typing import Any

from kelvi import tool


@tool(
    name="track_order",
    description="Check the current live delivery status and estimated arrival time of an order.",
    requires_confirmation=False,
)
async def track_order(order_id: str = "OD-9821") -> dict[str, Any]:
    """Fetch real-time delivery status."""
    return {
        "order_id": order_id,
        "status": "out_for_delivery",
        "eta_minutes": 12,
        "partner_name": "സുരേഷ് (Suresh)",
        "items": "Fresh Milk, Whole Wheat Bread, Eggs",
    }


@tool(
    name="cancel_order",
    description="Cancel an active order before dispatch or delivery.",
    requires_confirmation=True,
    confirmation_prompt={
        "ml-IN": "ഓർഡർ റദ്ദാക്കണമെന്ന് ഉറപ്പാണോ?",
        "hi-IN": "क्या आप वाकई अपना आर्डर रद्द करना चाहते हैं?",
        "en-IN": "Are you sure you want to cancel your order?",
    },
)
async def cancel_order(order_id: str = "OD-9821") -> dict[str, Any]:
    """Cancel order and initiate instant refund."""
    return {
        "order_id": order_id,
        "status": "cancelled",
        "refund_status": "initiated",
        "refund_amount": "₹340",
    }


@tool(
    name="call_delivery_partner",
    description="Bridge a direct phone call between customer and the assigned delivery partner.",
    requires_confirmation=False,
)
async def call_delivery_partner(order_id: str = "OD-9821") -> dict[str, Any]:
    """Trigger partner voice bridge."""
    return {
        "order_id": order_id,
        "partner_name": "Suresh",
        "status": "call_initiated",
        "masked_number": "+91-9840XXXXXX",
    }
