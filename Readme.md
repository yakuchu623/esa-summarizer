# esa-summarizer

esaの記事を自動要約するSlack Botです。

## 機能

### 1. 手動要約（メンション）
Botにメンションして記事URLを指定すると要約を生成します。

```
@esa-summarizer https://your-team.esa.io/posts/123
@esa-summarizer https://your-team.esa.io/posts/456 --length long --style paragraph
```

**オプション:**
- `--length short|medium|long`: 要約の長さ（デフォルト: medium）
- `--style bullet|paragraph`: 要約の形式（デフォルト: bullet）

### 2. 自動要約
指定したチャンネル（デフォルト: `04_esa`）でesa更新通知を監視し、自動的に要約を生成して別チャンネル（デフォルト: `04_esa_深掘り`）に投稿します。

- esaアプリからの更新通知を検出
- 記事URLを自動抽出
- 要約を生成して専用チャンネルに投稿
- デフォルト設定: `medium` + `bullet`

## セットアップ

### 1. 環境変数の設定

`.env`ファイルを作成し、以下を設定：

```bash
cp .env.example .env
```

必要な環境変数:
- `SLACK_BOT_TOKEN`: BotのOAuthトークン
- `SLACK_APP_TOKEN`: Socket ModeのApp-Levelトークン
- `ESA_ACCESS_TOKEN`: esaのアクセストークン
- `ESA_TEAM_NAME`: esaのチーム名
- `GEMINI_API_KEY`: Google Gemini APIキー
- `LOG_LEVEL`: ログレベル（省略可、デフォルト: `INFO`）
  - `DEBUG`: 詳細なデバッグ情報
  - `INFO`: 一般的な情報（推奨）
  - `WARNING`: 警告のみ
  - `ERROR`: エラーのみ
- `ESA_WATCH_CHANNEL`: 監視するチャンネル名（省略可、デフォルト: `04_esa`）
- `ESA_SUMMARY_CHANNEL`: 要約投稿先チャンネル名（省略可、デフォルト: `04_esa_深掘り`）

### 2. Slack Appの設定

#### 必要なOAuth Scopes (Bot Token Scopes)
- `app_mentions:read` - メンション検出
- `chat:write` - メッセージ投稿
- `channels:history` - パブリックチャンネルのメッセージ読み取り
- `channels:read` - チャンネル情報取得
- `groups:history` - プライベートチャンネルのメッセージ読み取り（必要な場合）
- `groups:read` - プライベートチャンネル情報取得（必要な場合）

#### Event Subscriptions
Socket Modeを有効にし、以下のイベントをサブスクライブ：
- `app_mention` - メンション時の手動要約用
- `message.channels` - パブリックチャンネルのメッセージ監視用
- `message.groups` - プライベートチャンネルのメッセージ監視用（必要な場合）

#### Botの招待
以下のチャンネルにBotを招待してください：
1. 監視対象チャンネル（例: `04_esa`）
2. 要約投稿先チャンネル（例: `04_esa_深掘り`）
3. その他、手動要約を使いたいチャンネル

### 3. 依存パッケージのインストール

```bash
cd bot
pip install slack-bolt python-dotenv requests google-generativeai
```

### 4. 起動

```bash
cd bot
python main.py
```

## 動作フロー

### 自動要約
1. `04_esa`チャンネルでesaアプリが記事更新を通知
2. Botがメッセージ内のesa URLを検出
3. esa APIで記事本文を取得
4. Gemini APIで要約を生成
5. `04_esa_深掘り`チャンネルに要約を投稿

### 手動要約
1. ユーザーがBotにメンション + URL + オプション
2. esa APIで記事本文を取得
3. Gemini APIで要約を生成（指定されたオプションで）
4. メンションされたチャンネルに返信

## トラブルシューティング

### ログの確認
起動時やエラー時にターミナルにログが出力されます：
```
2025-11-17 10:30:45 [INFO] slack_handler: ⚡️ Bolt app is running!
2025-11-17 10:30:45 [INFO] slack_handler: 📡 監視チャンネル: 04_esa
2025-11-17 10:30:45 [INFO] slack_handler: 📝 要約投稿先: 04_esa_深掘り
2025-11-17 10:31:20 [INFO] slack_handler: 自動要約処理を開始: https://team.esa.io/posts/123
2025-11-17 10:31:21 [INFO] esa_client: 記事取得成功: #123
2025-11-17 10:31:22 [INFO] gemini_client: 要約生成完了: 記事タイトル
2025-11-17 10:31:23 [INFO] slack_handler: ✅ 自動要約完了: 記事タイトル - https://...
```

詳細なデバッグ情報が必要な場合は、`.env`で`LOG_LEVEL=DEBUG`に設定してください。

### Botが反応しない場合
- Botがチャンネルに招待されているか確認
- OAuth Scopesが正しく設定されているか確認
- Event Subscriptionsが有効になっているか確認
- Socket Modeが有効になっているか確認

### チャンネルが見つからないエラー
- `.env`のチャンネル名が正しいか確認（`#`は不要）
- Botがそのチャンネルに招待されているか確認
- プライベートチャンネルの場合は`groups:read`スコープが必要

## 技術スタック

- **Slack**: `slack-bolt` (Socket Mode)
- **esa**: REST API
- **AI**: Google Gemini API
- **Python**: 3.8+
