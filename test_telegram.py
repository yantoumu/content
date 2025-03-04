#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram消息发送测试
"""

import os
import logging
import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('telegram_test')

def test_telegram_message():
    """测试发送Telegram消息"""
    # 从环境变量获取配置
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not telegram_token or not telegram_chat_id:
        logger.error("未设置TELEGRAM_BOT_TOKEN或TELEGRAM_CHAT_ID环境变量")
        return False
    
    # 测试消息
    message = """
🔔 <b>测试消息</b>

这是一条测试消息，用于验证Telegram通知功能是否正常工作。

📊 测试数据:
• 项目: 网站监控系统
• 状态: 运行中
• 时间: 测试时间

如果收到这条消息，说明Telegram通知功能正常工作。
"""
    
    try:
        # 发送消息
        api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        logger.info(f"正在发送消息到聊天ID: {telegram_chat_id}")
        response = requests.post(api_url, json=payload, timeout=10)
        
        # 输出详细的响应信息
        if response.status_code != 200:
            logger.error(f"发送失败，状态码: {response.status_code}")
            logger.error(f"错误响应: {response.text}")
            return False
            
        logger.info("✅ Telegram消息发送成功！")
        return True
        
    except requests.RequestException as e:
        logger.error(f"❌ 发送Telegram消息时出错: {e}")
        if hasattr(e.response, 'text'):
            logger.error(f"错误详情: {e.response.text}")
        return False

if __name__ == "__main__":
    test_telegram_message() 