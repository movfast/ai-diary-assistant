"""
Diary Updater
-------------
A conversational AI diary assistant that chats with the user,
summarizes conversations, and saves structured entries to Notion.
"""

import os
from datetime import date
from dotenv import load_dotenv
from openai import OpenAI
from notion_client import Client
import gradio as gr

load_dotenv()


class DiaryUpdater:
    """Manages AI-powered diary conversations and saves entries to Notion."""

    MODEL = "claude-sonnet-4-5-20250929"
    RECENT_ENTRIES_LIMIT = 3

    def __init__(self):
        self.notion = Client(auth=os.environ["DIARY_UPDATER_TOKEN"])
        self.page_id = os.environ["NOTION_PAGE_ID"]
        self.llm = OpenAI(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url="https://api.anthropic.com/v1/"
        )
        self.system_prompt = self._build_system_prompt()

    # ──────────────────────────────────────────────
    # Notion
    # ──────────────────────────────────────────────

    def get_recent_entries(self) -> list[str]:
        """Fetch the most recent diary summaries from Notion."""
        response = self.notion.blocks.children.list(block_id=self.page_id)
        entries = [
            "".join(t["text"]["content"] for t in block["paragraph"]["rich_text"])
            for block in response["results"]
            if block["type"] == "paragraph"
        ]
        return [e for e in entries if e][-self.RECENT_ENTRIES_LIMIT:]

    def write_diary_entry(self, theme: str, summary: str) -> None:
        """Append a formatted diary entry to the Notion page."""
        today = date.today().strftime("%B %d, %Y")
        self.notion.blocks.children.append(
            block_id=self.page_id,
            children=[
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": today}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": theme}}],
                        "color": "pink_background",
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary}}]
                    },
                },
            ],
        )

    # ──────────────────────────────────────────────
    # LLM
    # ──────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the system prompt enriched with recent diary context."""
        recent_entries = self.get_recent_entries()
        context = "\n\n".join(recent_entries) if recent_entries else "No previous entries."
        return f"""You are a warm diary assistant. Do not use emojis.
Ask what theme the user would like to explore today.

Recent diary entries for context:
{context}

Use this context to notice patterns and personalize your responses,
but do not repeat it back unless relevant."""

    def _complete(self, messages: list[dict]) -> str:
        """Send a list of messages to the LLM and return the response text."""
        response = self.llm.chat.completions.create(
            model=self.MODEL,
            messages=messages
        )
        return response.choices[0].message.content

    def chat(self, message: str, history: list[dict]) -> str:
        """Handle a single chat turn, maintaining conversation history."""
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + [{"role": h["role"], "content": h["content"]} for h in history]
            + [{"role": "user", "content": message}]
        )
        return self._complete(messages)

    def summarize_and_save(self, history: list) -> str:
        """Summarize the conversation and save the entry to Notion."""
        if not history:
            return "Nothing to save yet!"

        conversation = self._format_history(history)
        summary_prompt = f"""Based on this conversation, write the following:

Line 1: A single one-liner theme of the conversation.
Then write: ---
Then write a structured diary summary:

Mood: What emotional themes came up?
Highlight: What was the most significant moment?
Summary: A clean, first-person diary entry.
Patterns: Any recurring themes worth noting?

Conversation:
{conversation}

Write it warmly, like a personal diary entry. Do not use emojis."""

        result = self._complete([{"role": "user", "content": summary_prompt}])

        parts = result.split("---", 1)
        theme = parts[0].strip()
        summary = parts[1].strip() if len(parts) > 1 else result

        self.write_diary_entry(theme, summary)
        return f"Saved to Notion!\n\nTheme: {theme}"

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _format_history(history: list) -> str:
        """Convert Gradio history (dicts or tuples) to a readable string."""
        lines = []
        for msg in history:
            if isinstance(msg, dict):
                role = "You" if msg["role"] == "user" else "Claude"
                lines.append(f"{role}: {msg['content']}")
            else:
                user_msg, bot_msg = msg
                lines.append(f"You: {user_msg}\nClaude: {bot_msg}")
        return "\n\n".join(lines)

    # ──────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────

    def launch(self) -> None:
        """Build and launch the Gradio interface."""
        with gr.Blocks(title="Diary Updater") as demo:
            gr.Markdown("## Diary Updater")
            chatbot = gr.ChatInterface(fn=self.chat)
            save_btn = gr.Button("Save to Notion")
            status = gr.Textbox(label="Status", interactive=False)
            save_btn.click(
                fn=self.summarize_and_save,
                inputs=chatbot.chatbot,
                outputs=status
            )
        demo.launch()


if __name__ == "__main__":
    DiaryUpdater().launch()
