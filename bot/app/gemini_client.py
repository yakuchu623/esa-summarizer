import google.generativeai as genai
import logging
from config.settings import GEMINI_API_KEY, GEMINI_MODEL, SUMMARY_LENGTHS, SUMMARY_STYLES

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
    
    def summarize(
        self, 
        title: str, 
        body: str, 
        category: str = "", 
        length: str = "medium",
        style: str = "bullet"
    ) -> str:
        """ドキュメントを要約"""
        
        length_instruction = SUMMARY_LENGTHS.get(length, SUMMARY_LENGTHS["medium"])
        style_instruction = SUMMARY_STYLES.get(style, SUMMARY_STYLES["bullet"])
        
        prompt = f"""
# ペルソナ設定
あなたは、AI分野の研究室にいる優秀なアシスタントです。

# タスク
教授が作成した技術文書や研究資料を、指定された対象読者が理解しやすいように、要点を押さえて要約してください。

# 1. 要約の対象読者 (Audience)
研究室に配属された学部生

# 2. 要約の目的 (Purpose)
長い文章を要約し、サクッと概要を把握できるようにするため

# 3. 要約のポイント (Instructions)
1. **技術的詳細の保持**: 提案手法の核心、実験設定、主要な結果（重要な数値データや傾向）など、技術的な理解に不可欠な詳細を省略しません。
2. **新規性/貢献の明示**: この文書の「最も重要な貢献(Contribution)」や「従来技術との違い」が明確になるようにします。
3. **専門用語・略語**: 専門用語はそのまま使用します。ただし、文脈上重要と判断される略語(Acronym)が初出の場合は、正式名称を（）で併記します。
4. **結論と行動項目**: 文書の結論、および「次に何をすべきか（行動項目）」や「今後の課題」を明確に抽出します。
5. **構造の意識**: 可能な限り、原文の論理構成（例：背景・目的、手法、結果、考察）に沿って整理します。

# 4. 出力形式 (Format)
* **長さ**: {length_instruction}
* **形式**: {style_instruction}

【タイトル】
{title}

【カテゴリ】
{category if category else "なし"}

【本文】
{body}

上記の内容を{style_instruction}で要約してください:
"""
        
        try:
            logger.debug(f"Gemini API呼び出し: {title} (長さ: {length}, スタイル: {style})")
            response = self.model.generate_content(prompt)
            logger.info(f"要約生成完了: {title}")
            return response.text
        except Exception as e:
            logger.error(f"要約生成エラー ({title}): {str(e)}", exc_info=True)
            return f"要約生成エラー: {str(e)}"