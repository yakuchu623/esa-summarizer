import slack
import os
from dotenv import load_dotenv
import aiohttp

load_dotenv()

timestamp = "1763396932.126999"
channel_id = "C09P74YTJDD"

client = slack.WebClient(token=os.getenv('SLACK_BOT_TOKEN'))
response = client.chat_delete(
    channel=channel_id,
    ts=timestamp
)
