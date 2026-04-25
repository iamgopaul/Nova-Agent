from __future__ import annotations

import subprocess

from gaaia.tools.base import BaseTool, ToolResult


def _esc(text: str) -> str:
    """Escape a string for safe embedding inside an AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


class DraftEmailTool(BaseTool):
    name = "draft_email"
    description = (
        "Open a new email draft in macOS Mail with the given recipient, "
        "subject, and body. The draft is NOT sent — the user must review "
        "and send it manually."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text.",
                    },
                },
                "required": ["to", "subject", "body"],
            }
        )

    async def run(self, to: str, subject: str, body: str) -> ToolResult:
        script = f"""
tell application "Mail"
    set newMsg to make new outgoing message with properties ¬
        {{subject:"{_esc(subject)}", content:"{_esc(body)}", visible:true}}
    tell newMsg
        make new to recipient at end of to recipients ¬
            with properties {{address:"{_esc(to)}"}}
    end tell
    activate
end tell
"""
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            return ToolResult(
                content=f"Could not open Mail draft: {err}", error=err
            )
        return ToolResult(
            content=f"Draft opened in Mail — To: {to} | Subject: {subject}",
            metadata={"to": to, "subject": subject},
        )


class DraftMessageTool(BaseTool):
    name = "draft_message"
    description = (
        "Compose a short message or text suitable for sending via iMessage, "
        "WhatsApp, Slack, or similar. Returns the composed text for the user "
        "to copy and send themselves. Does not send anything."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Name or handle of the intended recipient.",
                    },
                    "context": {
                        "type": "string",
                        "description": "What the message should say or convey.",
                    },
                    "tone": {
                        "type": "string",
                        "description": "Tone: formal, casual, professional, friendly.",
                        "enum": ["formal", "casual", "professional", "friendly"],
                    },
                },
                "required": ["recipient", "context"],
            }
        )

    async def run(
        self, recipient: str, context: str, tone: str = "professional"
    ) -> ToolResult:
        # GAIA composes the message text directly — no external call needed.
        # This tool's value is that it signals to the orchestrator to produce
        # a properly formatted standalone message rather than a conversational reply.
        return ToolResult(
            content=(
                f"[Compose a {tone} message to {recipient}. "
                f"Content goal: {context}. "
                f"Return only the message text, ready to copy and send.]"
            ),
            metadata={"recipient": recipient, "tone": tone},
        )
