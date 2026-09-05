VOICE_TOOLS = [
    {
        "type": "function",
        "name": "send_payment_link",
        "description": "Send the existing secure payment link.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "record_promise",
        "description": "Record a promised payment date.",
        "parameters": {
            "type": "object",
            "properties": {"due_date": {"type": "string"}},
            "required": ["due_date"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "schedule_callback",
        "description": "Schedule a later call.",
        "parameters": {
            "type": "object",
            "properties": {"when": {"type": "string"}},
            "required": ["when"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "open_dispute",
        "description": "Pause and escalate a dispute.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "opt_out",
        "description": "Stop recovery communication.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "human_transfer",
        "description": "Escalate to a human.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]
