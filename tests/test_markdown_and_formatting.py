import os
import re
import pytest

from bot.app.slack_handler import SlackBot
from bot.app.esa_client import EsaClient


@pytest.fixture(scope="module")
def bot():
    # Minimal env tokens to allow App construction; won't start network.
    os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
    os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
    return SlackBot()


def test_convert_markdown_headings(bot):
    md = """# Title\n## Subtitle\nNormal text\n"""
    out = bot._convert_markdown_to_mrkdwn(md)
    assert "*Title*" in out
    assert "*Subtitle*" in out
    assert "Normal text" in out


def test_convert_markdown_lists_and_bold(bot):
    md = """- Item A\n* Item B\n+ Item C\n**Bold** text and __italic__ mid\n"""
    out = bot._convert_markdown_to_mrkdwn(md)
    lines = out.splitlines()
    assert lines[0].startswith("• Item A")
    assert lines[1].startswith("• Item B")
    assert lines[2].startswith("• Item C")
    assert "*Bold*" in out  # bold converted
    assert "_italic_" in out  # italic converted


def test_convert_markdown_code_block(bot):
    md = """```\nprint('hello')\n```\n"""
    out = bot._convert_markdown_to_mrkdwn(md)
    assert "print('hello')" in out
    # Ensure code fence markers appear twice (open/close)
    assert out.count("```") == 2


def test_chunk_text(bot):
    long_text = "\n".join([f"Line {i}" for i in range(200)])
    chunks = bot._chunk_text(long_text, chunk_size=200)
    # Should split into multiple chunks
    assert len(chunks) > 1
    # Each chunk within limit
    assert all(len(c) <= 200 for c in chunks)
    # Reconstruction contains last line
    reconstructed = "".join(chunks)
    assert "Line 199" in reconstructed


def test_build_summary_sections(bot):
    text = "Section line 1\nSection line 2"
    sections = bot._build_summary_sections(text)
    assert sections
    assert sections[0]["type"] == "section"
    assert sections[0]["text"]["type"] == "mrkdwn"


def test_format_summary_message_structure(bot, monkeypatch):
    title = "Sample Title"
    category = "Cat"
    updated_at = "2025-11-18"
    summary = "# H1\n- A\n- B\n**Bold**"
    url = "https://example.esa.io/posts/123"
    payload = bot._format_summary_message(title, category, updated_at, summary, url, "medium", "bullet", 123, 456)
    assert "blocks" in payload
    blocks = payload["blocks"]
    # Header block present
    header = blocks[0]
    assert header["type"] == "header"
    # Metadata section exists
    assert any(b.get("type") == "section" for b in blocks)
    # Context with article link
    assert any(b.get("type") == "context" for b in blocks)
    # Fallback text truncated properly
    assert len(payload["text"]) <= 3000


def test_esa_extract_post_number():
    client = EsaClient()
    url = "https://team.esa.io/posts/98765"
    assert client.extract_post_number_from_url(url) == 98765
    assert client.extract_post_number_from_url("https://team.esa.io/posts/notnumber") is None


def test_gemini_summarize_mock(bot, monkeypatch):
    # Stub GeminiClient.summarize so formatting path can be exercised without API call
    def fake_summarize(title, body, category, length, style):
        return f"# {title}\n- point1\n- point2\n**end**"
    monkeypatch.setattr(bot.gemini_client, "summarize", fake_summarize)
    post_body = "Lorem ipsum" * 10
    payload = bot._format_summary_message(
        "MockTitle", "MockCat", "2025-11-18", bot.gemini_client.summarize("MockTitle", post_body, "MockCat", "short", "bullet"),
        "https://example.esa.io/posts/321", "short", "bullet", 321, len(post_body)
    )
    assert any(b.get("type") == "header" for b in payload["blocks"])
    # Ensure bold converted
    mrkdwn_texts = [b["text"]["text"] for b in payload["blocks"] if b.get("type") == "section" and "text" in b]
    assert any("*end*" in t for t in mrkdwn_texts)
