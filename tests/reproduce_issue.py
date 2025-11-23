import logging
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.slack_handler import SlackBot

# Mock logging to see output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.slack_handler")
logger.setLevel(logging.INFO)

def test_duplicate_processing():
    # Mock dependencies
    with patch("app.slack_handler.App"), \
         patch("app.slack_handler.EsaClient"), \
         patch("app.slack_handler.GeminiClient"), \
         patch("app.slack_handler.SocketModeHandler"), \
         patch("app.slack_handler.ESA_WATCH_CHANNEL_ID", "C_WATCHED"):
        
        bot = SlackBot()
        # Mock bot_user_id to be different from the sender
        bot.bot_user_id = "U_MY_BOT"
        
        # Mock _process_auto_summary to track calls
        bot._process_auto_summary = MagicMock()
        
        # 1. Simulate original message event from esa bot
        event_original = {
            "type": "message",
            "subtype": "bot_message",
            "text": "Created post: https://docs.esa.io/posts/123",
            "bot_id": "B_ESA_BOT",
            "channel": "C_WATCHED",
            "ts": "1000.000"
        }
        
        # Mock context
        say = MagicMock()
        client = MagicMock()
        
        # We need to access the handle_message function. 
        # Since it's a decorator, we can't access it directly from bot instance easily 
        # without inspecting the app.event calls.
        # However, for this reproduction, we can just instantiate the logic or 
        # manually invoke the wrapper if we can find it.
        # A easier way is to copy the logic or extract it, but let's try to find it in app.event.
        
        # Actually, since we mocked App, bot.app.event is a mock.
        # We can't easily run the decorated function.
        # Let's modify SlackBot to make the handler accessible or just copy the logic for this test.
        # Or better, let's look at how SlackBot registers handlers.
        
        # In SlackBot.setup_handlers:
        # @self.app.event("message")
        # def handle_message(event, say, client):
        
        # We can capture the handler when it's registered.
        
        handler_ref = None
        def capture_handler(event_type):
            def decorator(func):
                nonlocal handler_ref
                if event_type == "message":
                    handler_ref = func
                return func
            return decorator
        
        bot.app.event = capture_handler
        bot.setup_handlers()
        
        if not handler_ref:
            print("FAILED to capture handler")
            return

        print("--- Sending Original Message ---")
        handler_ref(event_original, say, client)
        
        # 2. Simulate message_changed event (unfurl)
        event_changed = {
            "type": "message",
            "subtype": "message_changed",
            "message": {
                "text": "Created post: https://docs.esa.io/posts/123",
                "bot_id": "B_ESA_BOT",
                "attachments": [{"title": "Unfurled Title"}]
            },
            "channel": "C_WATCHED",
            "hidden": True,
            "ts": "1000.000"
        }
        
        print("\n--- Sending Message Changed Event ---")
        handler_ref(event_changed, say, client)
        
        print(f"\n_process_auto_summary call count: {bot._process_auto_summary.call_count}")
        if bot._process_auto_summary.call_count > 1:
            print("ISSUE REPRODUCED: _process_auto_summary called multiple times for the same content.")
        else:
            print("Issue NOT reproduced.")

if __name__ == "__main__":
    test_duplicate_processing()
