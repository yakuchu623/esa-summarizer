import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ログ設定
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ロガーの設定
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT
)

# Slack設定
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

# 自動要約設定
ESA_WATCH_CHANNEL_ID = os.getenv("ESA_WATCH_CHANNEL_ID")  # esa更新通知を監視するチャンネルID
# 要約結果を投稿するチャンネルID（カンマ区切りで複数指定可）
ESA_SUMMARY_CHANNEL_IDS = [
    ch.strip() for ch in os.getenv("ESA_SUMMARY_CHANNEL_ID", "").split(",") if ch.strip()
]

# esa設定
ESA_ACCESS_TOKEN = os.getenv("ESA_ACCESS_TOKEN")
ESA_TEAM_NAME = os.getenv("ESA_TEAM_NAME")
ESA_API_BASE = "https://api.esa.io/v1"

# Gemini設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite-preview-09-2025"

# 要約設定
SUMMARY_LENGTHS = {
    "short": "3-5文で簡潔に（全体で20字程度）",
    "medium": "10文程度で要点を押さえて（全体で50字程度）",
    "long": "20文以上で詳細に（全体で100字程度）"
}

SUMMARY_STYLES = {
    "bullet": "箇条書き",
    "paragraph": "段落形式"
}