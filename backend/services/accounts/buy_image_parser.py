"""
从券商成交截图识别买入记录
使用智谱 GLM-4.6V 解析图片中的股票代码、买入价、数量等
"""

import base64
import json
import re
import logging
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)



def parse_buy_image(image_bytes: bytes, config_manager=None) -> Dict[str, Any]:
    """
    从成交截图图片中识别买入记录
    
    Args:
        image_bytes: 图片二进制数据
        config_manager: 配置管理器，用于获取智谱 GLM-4.6V 配置
    
    Returns:
        {
            "success": bool,
            "records": [{"code": "002165", "name": "红宝丽", "buy_price": 12.89, "quantity": 500, "buy_time": "13:55:59"}, ...],
            "message": str
        }
    """
    try:
        if config_manager is None:
            from utils.config_manager import ConfigManager
            config_manager = ConfigManager()
        
        zhipu_config = config_manager.get_ai_config("zhipu")
        if not zhipu_config or not config_manager.is_ai_enabled("zhipu"):
            return {"success": False, "records": [], "message": "智谱服务未启用，请在 config.json 中配置 ai_services.zhipu"}
        
        api_key = zhipu_config.get("api_key", "").strip()
        if not api_key or api_key == "your-zhipu-api-key-here":
            return {"success": False, "records": [], "message": "智谱 API Key 未配置"}
        
        api_url = (zhipu_config.get("api_url") or "https://open.bigmodel.cn/api/paas/v4/chat/completions").rstrip("/")
        model = zhipu_config.get("model", "glm-4.6v")
        timeout = zhipu_config.get("timeout", 120)  # 视觉模型较慢，默认 120 秒
        max_retries = zhipu_config.get("max_retries", 2)  # 除首次外最多重试 2 次
        
        # 检测图片格式
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            media_type = "image/jpeg"
        else:
            media_type = "image/png"
        
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{media_type};base64,{b64}"
        
        prompt = """这是一张证券买入成交记录截图。请识别图片中的每一笔「证券买入」成交记录，提取以下字段：
- code: 股票代码（6位数字）
- name: 股票名称
- buy_price: 成交价格（使用成交价，非委托价）
- quantity: 成交数量（股）

请严格以 JSON 数组格式返回，不要其他文字。例如：
[{"code":"002165","name":"红宝丽","buy_price":12.89,"quantity":500},{"code":"000021","name":"深科技","buy_price":34.33,"quantity":100}]

若无法识别或图片中无买入记录，返回空数组 []。"""
        
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    ]
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.1
        }

        resp = None
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < max_retries:
                    wait_sec = (2 ** attempt) * 3  # 3s, 6s, 12s...
                    logger.warning(f"智谱 API 请求超时/连接失败，{wait_sec} 秒后重试 ({attempt + 1}/{max_retries + 1}): {e}")
                    time.sleep(wait_sec)
                else:
                    if isinstance(e, (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout)):
                        raise Exception("智谱接口响应超时，请稍后重试或换一张清晰的截图") from e
                    if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                        raise Exception("智谱接口连接异常，请检查网络后重试") from e
                    raise
        if resp.status_code != 200:
            logger.warning(f"智谱 GLM-4.6V API 返回 {resp.status_code}: {resp.text[:300]}")
            return {"success": False, "records": [], "message": f"AI 识别失败: HTTP {resp.status_code}"}
        
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = (choice.get("message") or {}).get("content", "")
        if not content or not content.strip():
            return {"success": False, "records": [], "message": "AI 未返回识别结果"}
        
        # 解析 JSON：可能被 markdown 包裹
        content = content.strip()
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            content = json_match.group(0)
        
        records = json.loads(content)
        if not isinstance(records, list):
            records = []
        
        # 校验并规范化
        valid = []
        for r in records:
            if not isinstance(r, dict):
                continue
            code = str(r.get("code") or r.get("股票代码") or "").strip()
            name = str(r.get("name") or r.get("股票名称") or "").strip()
            buy_price = _safe_float(r.get("buy_price") or r.get("成交价") or r.get("买入价"))
            quantity = _safe_int(r.get("quantity") or r.get("数量") or r.get("成交数量"))
            if code and len(code) >= 6:
                code = code[-6:] if len(code) > 6 else code
                valid.append({
                    "code": code,
                    "name": name or code,
                    "buy_price": buy_price,
                    "quantity": quantity or 0
                })
        
        return {"success": True, "records": valid, "message": f"识别到 {len(valid)} 笔买入记录"}
    
    except json.JSONDecodeError as e:
        logger.warning(f"解析 AI 返回 JSON 失败: {e}")
        return {"success": False, "records": [], "message": "识别结果解析失败，请重试"}
    except Exception as e:
        logger.error(f"图片识别失败: {e}", exc_info=True)
        return {"success": False, "records": [], "message": "图片识别失败，请稍后重试"}


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None
