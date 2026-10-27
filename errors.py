# Error types (house pattern).
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai


class Refusal(Exception):
    """A named refusal: the surface refuses by name, nothing executes."""

    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class ToolError(Exception):
    """A plain tool error (validation, bad arguments)."""
