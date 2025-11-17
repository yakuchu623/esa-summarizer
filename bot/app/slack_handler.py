from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from app.esa_client import EsaClient
from app.gemini_client import GeminiClient
from config.settings import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ESA_WATCH_CHANNEL_ID, ESA_SUMMARY_CHANNEL_IDS
import logging
import re

logger = logging.getLogger(__name__)


class SlackBot:
    def __init__(self):
        self.app = App(token=SLACK_BOT_TOKEN)
        self.esa_client = EsaClient()
        self.gemini_client = GeminiClient()
        self.setup_handlers()
    
    def setup_handlers(self):
        """イベントハンドラのセットアップ"""
        
        @self.app.event("message")
        def handle_message(event, say, client):
            """メッセージイベントを処理（自動要約）"""
            logger.info(f"メッセージイベント受信: {event}")
            
            # 削除のサブタイプは無視（bot_message, message_changedは処理する）
            subtype = event.get('subtype')
            if subtype and subtype not in ['bot_message', 'message_changed']:
                logger.debug(f"サブタイプ '{subtype}' のため無視")
                return
            
            # message_changedの場合は、メッセージ内容を取得
            if subtype == 'message_changed':
                message = event.get('message', {})
                text = message.get('text', '')
                bot_id = message.get('bot_id')
                bot_profile = message.get('bot_profile')
                logger.debug(f"メッセージ更新を検出: bot_id={bot_id}")
            else:
                text = event.get('text', '')
                bot_id = event.get('bot_id')
                bot_profile = event.get('bot_profile')
            
            # チャンネルIDを取得
            channel_id = event.get('channel')
            logger.debug(f"チャンネルID: {channel_id}, 監視対象: {ESA_WATCH_CHANNEL_ID}")
            
            # 監視対象チャンネル以外は無視
            if not ESA_WATCH_CHANNEL_ID or channel_id != ESA_WATCH_CHANNEL_ID:
                logger.debug(f"監視対象外のチャンネル '{channel_id}' のため無視")
                return
            
            # esaアプリ（または他のBot）からのメッセージか確認
            # bot_idまたはbot_profileがあればBotからのメッセージ
            bot_id = event.get('bot_id')
            bot_profile = event.get('bot_profile')
            
            logger.info(f"チャンネル '{channel_id}' でメッセージ検出: bot_id={bot_id}, bot_profile={bool(bot_profile)}")
            
            if not bot_id and not bot_profile:
                logger.debug(f"人間からのメッセージのため無視: {text[:50] if text else ''}")
                return  # 人間のメッセージは無視
            
            logger.info(f"Botメッセージを検出: bot_id={bot_id}, チャンネルID={channel_id}")
            
            # esa URLを抽出（https://team.esa.io/posts/123 形式）
            url_pattern = r'https?://[^\s]+\.esa\.io/posts/\d+'
            urls = re.findall(url_pattern, text)
            
            if not urls:
                return  # esa URLが含まれていなければ無視
            
            # 各URLについて要約を生成（重複を除く）
            processed_urls = set()
            for url in urls:
                # URLのクリーンアップ（末尾の記号を除去）
                url = re.sub(r'[)>]$', '', url)
                
                if url in processed_urls:
                    continue
                processed_urls.add(url)
                
                # 要約を非同期的に処理（投稿元チャンネルIDを渡す）
                self._process_auto_summary(url, client, channel_id)
        
        @self.app.event("app_mention")
        def handle_mention(event, say):
            """Botへのメンションを処理"""
            text = event['text']
            user_id = event['user']
            
            # Botのメンション部分を除去
            # <@U12345678> https://... -> https://...
            text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            
            # ヘルプメッセージ
            if not text or 'help' in text.lower() or 'ヘルプ' in text:
                help_message = self._get_help_message()
                say(f"<@{user_id}>\n{help_message}")
                return
            
            # パラメータ解析
            length = "medium"
            style = "bullet"
            
            # --length short などのオプション解析
            length_match = re.search(r'--length\s+(short|medium|long)', text)
            if length_match:
                length = length_match.group(1)
                text = re.sub(r'--length\s+(short|medium|long)', '', text).strip()
            
            style_match = re.search(r'--style\s+(bullet|paragraph)', text)
            if style_match:
                style = style_match.group(1)
                text = re.sub(r'--style\s+(bullet|paragraph)', '', text).strip()
            
            # URL抽出
            url_match = re.search(r'https?://[^\s]+', text)
            if not url_match:
                say(f"<@{user_id}> ❌ エラー: esaのURLを指定してください\n\n{self._get_help_message()}")
                return
            
            url = url_match.group(0)
            
            # 処理中メッセージ
            say(f"<@{user_id}> 📝 要約を生成中です... (長さ: {length}, 形式: {style})")
            
            # esa記事取得
            post = self.esa_client.get_post_from_url(url)
            if not post:
                say(f"<@{user_id}> ❌ 記事の取得に失敗しました。URLを確認してください。")
                return
            
            # 記事データ取得
            post_data = post.get('post', post)
            title = post_data.get('name', 'タイトルなし')
            body = post_data.get('body_md', '')
            category = post_data.get('category', '')
            updated_at = post_data.get('updated_at', '')
            post_number = post_data.get('number', '')
            
            if not body:
                say(f"<@{user_id}> ❌ 記事の本文が空です。")
                return
            
            # 要約生成
            try:
                summary = self.gemini_client.summarize(title, body, category, length, style)
                
                # 結果を整形して投稿
                message = self._format_summary_message(
                    title, category, updated_at, summary, url, length, style, post_number, len(body)
                )
                say(message)
                
            except Exception as e:
                say(f"<@{user_id}> ❌ 要約生成中にエラーが発生しました: {str(e)}")
    
    def _process_auto_summary(self, url: str, client, source_channel_id: str):
        """自動要約を処理"""
        try:
            logger.info(f"自動要約処理を開始: {url}")
            # 要約投稿先チャンネルIDリストを決定
            if ESA_SUMMARY_CHANNEL_IDS:
                summary_channel_ids = ESA_SUMMARY_CHANNEL_IDS
                logger.info(f"投稿先チャンネル: {len(summary_channel_ids)}件")
            else:
                summary_channel_ids = [source_channel_id]
                logger.warning(f"ESA_SUMMARY_CHANNEL_IDが設定されていません。フォールバックとして投稿元チャンネルに投稿します")
            
            # esa記事取得
            post = self.esa_client.get_post_from_url(url)
            if not post:
                logger.warning(f"記事の取得に失敗: {url}")
                return
            
            # 記事データ取得
            post_data = post.get('post', post)
            title = post_data.get('name', 'タイトルなし')
            body = post_data.get('body_md', '')
            category = post_data.get('category', '')
            updated_at = post_data.get('updated_at', '')
            post_number = post_data.get('number', '')
            
            if not body:
                logger.warning(f"記事の本文が空: {url}")
                return
            
            logger.info(f"要約を生成中: {title} (文字数: {len(body)}字)")
            # 要約生成（デフォルト: medium + bullet）
            length = "medium"
            style = "bullet"
            
            summary = self.gemini_client.summarize(title, body, category, length, style)
            
            # 結果を整形して投稿
            message = self._format_summary_message(
                title, category, updated_at, summary, url, length, style, post_number, len(body)
            )
            
            # 各チャンネルに投稿
            for channel_id in summary_channel_ids:
                try:
                    client.chat_postMessage(
                        channel=channel_id,
                        text=message,
                        unfurl_links=False,
                        unfurl_media=False
                    )
                    logger.info(f"✅ チャンネル {channel_id} へ投稿完了")
                except Exception as e:
                    logger.error(f"チャンネル {channel_id} への投稿失敗: {e}")
            
            logger.info(f"✅ 自動要約完了: {title} - {url}")
            
        except Exception as e:
            logger.error(f"自動要約エラー ({url}): {str(e)}", exc_info=True)
    
    def _format_summary_message(self, title, category, updated_at, summary, url, length, style, post_number, body_length):
        """要約結果のメッセージを整形"""
        return summary
    
    def _get_help_message(self):
        """ヘルプメッセージ"""
        return """
*esa Document Summarizer の使い方* 📚

**基本的な使い方:**
```
@esa-summarizer https://your-team.esa.io/posts/123
```

**オプション付き:**
```
@esa-summarizer https://your-team.esa.io/posts/123 --length short --style paragraph
```

**オプション一覧:**
- `--length short` : 短い要約（3-5文）
- `--length medium` : 標準の要約（10文程度）※デフォルト
- `--length long` : 詳細な要約（20文以上）

- `--style bullet` : 箇条書き形式 ※デフォルト
- `--style paragraph` : 段落形式

**例:**
```
@esa-summarizer https://your-team.esa.io/posts/456 --length long --style bullet
```
"""
    
    def start(self):
        """Botを起動"""
        handler = SocketModeHandler(self.app, SLACK_APP_TOKEN)
        logger.info("⚡️ Bolt app is running!")
        logger.info(f"📡 監視チャンネルID: {ESA_WATCH_CHANNEL_ID or '未設定'}")
        if ESA_SUMMARY_CHANNEL_IDS:
            logger.info(f"📝 要約投稿先ID: {', '.join(ESA_SUMMARY_CHANNEL_IDS)} ({len(ESA_SUMMARY_CHANNEL_IDS)}件)")
        else:
            logger.info("📝 要約投稿先ID: 未設定（元チャンネルにフォールバック）")
        logger.info("💡 Botにメンションして要約を開始してください")
        logger.info("   例: @esa-summarizer https://your-team.esa.io/posts/123")
        handler.start()