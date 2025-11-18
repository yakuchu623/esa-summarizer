from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from app.esa_client import EsaClient
from app.gemini_client import GeminiClient
from config.settings import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ESA_WATCH_CHANNEL_ID, ESA_SUMMARY_CHANNEL_IDS, DEBUG_VERBOSE
from app.debug_utils import step, log_kv, truncate
import logging
import re

logger = logging.getLogger(__name__)


class SlackBot:
    def __init__(self):
        self.app = App(token=SLACK_BOT_TOKEN)
        self.esa_client = EsaClient()
        self.gemini_client = GeminiClient()
        if DEBUG_VERBOSE:
            @self.app.middleware  # 全イベント生ボディをログ
            def log_raw(logger_mw, body, next):
                try:
                    logger.debug(f"[RAW EVENT] keys={list(body.keys())} body_trunc={truncate(str(body), 500)}")
                except Exception:
                    logger.debug("[RAW EVENT] <unprintable>")
                return next()
        self.setup_handlers()
    
    def setup_handlers(self):
        """イベントハンドラのセットアップ"""
        
        @self.app.event("message")
        def handle_message(event, say, client):
            """メッセージイベントを処理（自動要約）"""
            if DEBUG_VERBOSE:
                logger.info(f"メッセージイベント受信: {truncate(str(event),800)}")
            with step("message_event"):
                log_kv("message.meta", subtype=event.get('subtype'), channel=event.get('channel'))
            
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
            
            # blocksのみの場合のフォールバック（esa通知でtextが空になるケース対応）
            if not text and 'blocks' in event:
                rebuilt = self._extract_text_from_blocks(event.get('blocks', []))
                if rebuilt:
                    text = rebuilt
                    logger.debug(f"blocksから再構築したテキスト: {text[:200]}")
            
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
            
            # esa URLを抽出（text/blocks/attachments すべてを見る）
            urls = self._collect_esa_urls(text, event.get('blocks'), event.get('attachments'))
            
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
                with step("auto_summary_one"):
                    self._process_auto_summary(url, client, channel_id)
        
        @self.app.event("app_mention")
        def handle_mention(event, say):
            """Botへのメンションを処理"""
            if DEBUG_VERBOSE:
                logger.info(f"メンションイベント受信: {truncate(str(event),800)}")
            with step("mention_event"):
                log_kv("mention.meta", user=event.get('user'), channel=event.get('channel'))
            # 安全にテキスト取得（blocksのみの場合のフォールバック）
            text = event.get('text', '') or ''
            if not text and 'blocks' in event:
                try:
                    text = self._extract_text_from_blocks(event.get('blocks', []))
                    logger.debug(f"blocksから再構築したテキスト: {text}")
                except Exception as e:
                    logger.warning(f"blocksからテキスト再構築失敗: {e}")
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
            urls = self._collect_esa_urls(text, event.get('blocks'), event.get('attachments'))
            if not urls:
                say(f"<@{user_id}> ❌ エラー: esaのURLを指定してください\n\n{self._get_help_message()}")
                return
            
            url = urls[0]
            
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
                with step("gemini_summarize"):
                    summary = self.gemini_client.summarize(title, body, category, length, style)
                    summary = self._normalize_numbering(summary)
                
                # 結果を整形して投稿
                with step("format_and_send"):
                    message_payload = self._format_summary_message(
                        title, category, updated_at, summary, url, length, style, post_number, len(body)
                    )
                    response = say(**message_payload)
                    if DEBUG_VERBOSE:
                        logger.debug(f"chat.postMessage response={truncate(str(response),400)}")
                
            except Exception as e:
                say(f"<@{user_id}> ❌ 要約生成中にエラーが発生しました: {str(e)}")
        
        @self.app.error
        def handle_errors(error):
            logger.exception(f"Slack Bolt エラー: {error}")
    
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
            
            with step("gemini_auto_summarize"):
                summary = self.gemini_client.summarize(title, body, category, length, style)
                summary = self._normalize_numbering(summary)
            
            # 結果を整形して投稿
            message_payload = self._format_summary_message(
                title, category, updated_at, summary, url, length, style, post_number, len(body)
            )
            
            # 各チャンネルに投稿
            for channel_id in summary_channel_ids:
                try:
                    with step(f"post_{channel_id}"):
                        resp = client.chat_postMessage(
                            channel=channel_id,
                            **message_payload
                        )
                        if DEBUG_VERBOSE:
                            logger.debug(f"post_result channel={channel_id} ok={getattr(resp,'get',lambda x:True)('ok') if hasattr(resp,'get') else 'n/a'} resp={truncate(str(resp),300)}")
                    logger.info(f"✅ チャンネル {channel_id} へ投稿完了")
                except Exception as e:
                    logger.error(f"チャンネル {channel_id} への投稿失敗: {e}")
            
            logger.info(f"✅ 自動要約完了: {title} - {url}")
            
        except Exception as e:
            logger.error(f"自動要約エラー ({url}): {str(e)}", exc_info=True)
    
    def _format_summary_message(self, title, category, updated_at, summary, url, length, style, post_number, body_length):
        """要約結果をSlack Block Kit形式で整形"""
        summary = self._normalize_numbering(summary)
        summary_mrkdwn = self._convert_markdown_to_mrkdwn(summary)
        summary_sections = self._build_summary_sections(summary_mrkdwn)
        fallback_lines = [
            f"{title}",
            f"カテゴリ: {category or 'なし'} / 更新: {updated_at or '不明'}",
            f"esa: {url}",
            summary_mrkdwn
        ]
        fallback_text = "\n".join(line for line in fallback_lines if line).strip()
        metadata_elements = [
            {"type": "mrkdwn", "text": f"*カテゴリ*\n{category or 'なし'}"},
            {"type": "mrkdwn", "text": f"*更新日時*\n{updated_at or '不明'}"},
            {"type": "mrkdwn", "text": f"*文字数*\n{body_length:,}字"},
            {"type": "mrkdwn", "text": f"*指定*\n長さ: {length} / 形式: {style}"}
        ]
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"要約: {title[:140]}",
                    "emoji": True
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{url}|esa #{post_number or '?'}>"
                    }
                ]
            },
            {"type": "section", "fields": metadata_elements},
            {"type": "divider"},
            *summary_sections,
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📄 <{url}|記事を開く>"
                    }
                ]
            }
        ]
        return {
            "text": fallback_text[:3000],
            "blocks": blocks,
            "unfurl_links": False,
            "unfurl_media": False
        }

    def _convert_markdown_to_mrkdwn(self, markdown_text: str) -> str:
        """簡易的にMarkdownをSlack mrkdwnに変換"""
        if not markdown_text:
            return ""
        lines = markdown_text.strip().splitlines()
        converted = []
        in_code_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                converted.append("```")
                continue
            if in_code_block:
                converted.append(line)
                continue
            if not stripped:
                converted.append("")
                continue
            heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
            if heading_match:
                content = heading_match.group(2).strip()
                converted.append(f"*{content}*")
                continue
            if stripped.startswith(('- ', '* ', '+ ')):
                converted.append(f"• {stripped[2:].strip()}")
                continue
            converted.append(stripped)
        mrkdwn = "\n".join(converted)
        mrkdwn = re.sub(r"\*\*(.*?)\*\*", r"*\1*", mrkdwn)
        mrkdwn = re.sub(r"__(.*?)__", r"_\1_", mrkdwn)
        return mrkdwn

    def _build_summary_sections(self, summary_text: str):
        """Slackのsectionブロックに収まるよう要約を分割"""
        if not summary_text:
            return [{"type": "section", "text": {"type": "mrkdwn", "text": "要約が空です。"}}]
        sections = []
        for chunk in self._chunk_text(summary_text):
            sections.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": chunk}
            })
        return sections

    def _chunk_text(self, text: str, chunk_size: int = 2800):
        """セクションの文字数制限に沿ってテキストを分割"""
        chunks = []
        remaining = text.strip()
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break
            split_index = remaining.rfind('\n', 0, chunk_size)
            if split_index == -1 or split_index < chunk_size * 0.6:
                split_index = chunk_size
            chunks.append(remaining[:split_index].rstrip())
            remaining = remaining[split_index:].lstrip()
        return chunks

    def _normalize_numbering(self, summary: str) -> str:
        """\\1, \\2... のようなプレースホルダを 1,2,3... に置換し直す"""
        if not summary or "\\" not in summary:
            return summary
        lines = []
        counter = 1
        for line in summary.splitlines():
            had_placeholder = bool(re.search(r"\\+\d+", line))
            if had_placeholder:
                line = re.sub(r"\\+(?=\d)", "", line)
                line = re.sub(r"\d+", lambda _m: str(counter), line, count=1)
                counter += 1
            lines.append(line)
        return "\n".join(lines)

    def _extract_text_from_blocks(self, blocks):
        """blocksからテキストを復元する簡易ヘルパー"""
        block_texts = []
        for block in blocks or []:
            if block.get('type') == 'rich_text':
                for el in block.get('elements', []):
                    if el.get('type') == 'rich_text_section':
                        for sub in el.get('elements', []):
                            if sub.get('type') == 'text':
                                block_texts.append(sub.get('text',''))
                            elif sub.get('type') == 'link' and sub.get('url'):
                                block_texts.append(sub.get('url',''))
            elif block.get('type') == 'section' and 'text' in block:
                block_texts.append(block['text'].get('text',''))
        return ' '.join(block_texts).strip()

    def _collect_esa_urls(self, text: str, blocks=None, attachments=None):
        """text/blocks/attachments から esa の投稿URLを集める"""
        urls = set()
        # text から
        for raw in re.findall(r'https?://[^\s>]+', text or ""):
            clean = self._clean_slack_url(raw)
            if self._is_esa_post_url(clean):
                urls.add(clean)
        # blocks から (リンク要素も拾う)
        for block in blocks or []:
            if block.get('type') == 'rich_text':
                for el in block.get('elements', []):
                    if el.get('type') == 'rich_text_section':
                        for sub in el.get('elements', []):
                            if sub.get('type') == 'link' and sub.get('url'):
                                clean = self._clean_slack_url(sub.get('url',''))
                                if self._is_esa_post_url(clean):
                                    urls.add(clean)
                            elif sub.get('type') == 'text':
                                for raw in re.findall(r'https?://[^\s>]+', sub.get('text','')):
                                    clean = self._clean_slack_url(raw)
                                    if self._is_esa_post_url(clean):
                                        urls.add(clean)
            elif block.get('type') == 'section' and 'text' in block:
                for raw in re.findall(r'https?://[^\s>]+', block['text'].get('text','')):
                    clean = self._clean_slack_url(raw)
                    if self._is_esa_post_url(clean):
                        urls.add(clean)
        # attachments から
        for att in attachments or []:
            for key in ["original_url", "title_link", "from_url", "fallback", "text"]:
                val = att.get(key)
                if isinstance(val, str):
                    for raw in re.findall(r'https?://[^\s>]+', val):
                        clean = self._clean_slack_url(raw)
                        if self._is_esa_post_url(clean):
                            urls.add(clean)
        return list(urls)

    def _clean_slack_url(self, url: str) -> str:
        """<https://...|title> 形式の余分な記号を除去"""
        url = url.split('|', 1)[0]
        return url.strip('<>').rstrip(')')

    def _is_esa_post_url(self, url: str) -> bool:
        """esaの投稿URLか簡易判定"""
        return bool(re.search(r'https?://[^/\s]+\.esa\.io/posts/\d+', url))

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
        # トークン/ユーザー確認
        try:
            auth = self.app.client.auth_test()
            logger.info(f"🤖 Bot User ID: {auth.get('user_id')} / Team: {auth.get('team')}")
        except Exception as e:
            logger.error(f"auth_test に失敗しました。トークンや権限を確認してください: {e}")
        # チャンネル存在/参加状況確認
        try:
            target_ids = [cid for cid in [ESA_WATCH_CHANNEL_ID, *ESA_SUMMARY_CHANNEL_IDS] if cid]
            for cid in target_ids:
                try:
                    info = self.app.client.conversations_info(channel=cid)
                    ch = info.get('channel', {})
                    logger.info(f"🔍 channel={cid} name={ch.get('name')} is_member={ch.get('is_member')} private={ch.get('is_private')}")
                    if not ch.get('is_member'):
                        logger.warning(f"Botはチャンネル {cid} に未参加です。/invite で追加してください。")
                except Exception as ce:
                    logger.warning(f"conversations.info 取得失敗 channel={cid}: {ce}")
        except Exception as e:
            logger.warning(f"チャンネル検査中にエラー: {e}")
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
