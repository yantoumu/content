#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试网站更新通知
该脚本模拟网站更新并发送Telegram通知
"""

import os
import json
import logging
import datetime
import requests
from typing import List, Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_update')

def send_telegram_notification(updates: List[Dict[str, Any]]) -> bool:
    """发送Telegram通知"""
    # 从环境变量获取配置
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not telegram_token or not telegram_chat_id:
        logger.error("未设置TELEGRAM_BOT_TOKEN或TELEGRAM_CHAT_ID环境变量")
        return False
    
    # 构建通知消息
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    message = f"""
🔔 <b>网站内容更新通知</b> ({current_date})

<b>模拟网站更新测试</b>有新内容发布：

"""
    
    # 添加每个更新的信息
    for i, update in enumerate(updates, 1):
        title = update.get('title', '未知标题')
        url = update.get('url', '#')
        keywords = update.get('keywords', [])
        keywords_str = ", ".join(keywords) if keywords else "无关键词"
        
        message += f"{i}. <a href='{url}'>{title}</a>\n"
        message += f"   关键词: {keywords_str}\n\n"
    
    message += "这是一条测试消息，用于验证通知功能。"
    
    try:
        # 发送消息
        api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        logger.info(f"正在发送通知到聊天ID: {telegram_chat_id}")
        response = requests.post(api_url, json=payload, timeout=10)
        
        # 检查响应
        if response.status_code != 200:
            logger.error(f"发送失败，状态码: {response.status_code}")
            logger.error(f"错误响应: {response.text}")
            return False
            
        logger.info("✅ Telegram通知发送成功！")
        return True
        
    except Exception as e:
        logger.error(f"❌ 发送Telegram通知时出错: {e}")
        return False

def main():
    """主函数"""
    logger.info("开始测试网站更新通知...")
    
    # 模拟网站更新数据
    mock_updates = [
        {
            "title": "新游戏：超级冒险",
            "url": "https://www.crazygames.com/game/super-adventure",
            "keywords": ["冒险", "动作", "3D"]
        },
        {
            "title": "更新：我的世界最新版本",
            "url": "https://www.crazygames.com/game/minecraft-latest",
            "keywords": ["沙盒", "建造", "多人游戏"]
        },
        {
            "title": "热门推荐：赛车大师",
            "url": "https://www.crazygames.com/game/racing-master",
            "keywords": ["赛车", "竞速", "3D"]
        }
    ]
    
    # 发送通知
    success = send_telegram_notification(mock_updates)
    
    if success:
        logger.info("测试完成：通知发送成功")
    else:
        logger.error("测试失败：通知发送失败")

if __name__ == "__main__":
    main() 