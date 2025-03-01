#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置测试工具，用于验证环境变量和Telegram Bot设置是否正确
"""

import os
import json
import base64
import logging
from datetime import datetime
import sys
import binascii

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('config_tester')

def process_encryption_key(key: str) -> bytes:
    """处理加密密钥，支持多种格式"""
    if not key:
        return b''
        
    # 尝试将密钥当作十六进制字符串处理
    try:
        if len(key) == 64:  # 32字节的十六进制表示为64个字符
            return binascii.unhexlify(key)
    except binascii.Error:
        pass
        
    # 尝试将密钥当作Base64编码处理
    try:
        decoded = base64.b64decode(key)
        if len(decoded) == 32:  # 期望32字节的密钥
            return decoded
    except Exception:
        pass
        
    # 如果上述方法都失败，直接编码字符串
    return key.encode('utf-8')

def test_environment_variables():
    """测试环境变量是否正确设置"""
    logger.info("开始测试环境变量...")
    
    # 测试ENCRYPTION_KEY
    encryption_key_str = os.environ.get('ENCRYPTION_KEY', '')
    if not encryption_key_str:
        logger.error("❌ ENCRYPTION_KEY 未设置")
        return False
    
    try:
        key_bytes = process_encryption_key(encryption_key_str)
        if len(key_bytes) != 32:
            logger.error(f"❌ ENCRYPTION_KEY 长度不正确: {len(key_bytes)}字节，应为32字节")
            return False
        logger.info("✅ ENCRYPTION_KEY 格式正确")
    except Exception as e:
        logger.error(f"❌ ENCRYPTION_KEY 格式错误: {e}")
        return False
    
    # 测试TELEGRAM_BOT_TOKEN
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not telegram_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN 未设置")
        return False
    
    if ':' not in telegram_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN 格式可能不正确，应包含':'")
        return False
    logger.info("✅ TELEGRAM_BOT_TOKEN 格式正确")
    
    # 测试TELEGRAM_CHAT_ID
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not chat_id:
        logger.error("❌ TELEGRAM_CHAT_ID 未设置")
        return False
    logger.info("✅ TELEGRAM_CHAT_ID 已设置")
    
    # 测试SITEMAP_URLS
    urls_json = os.environ.get('SITEMAP_URLS', '')
    if not urls_json:
        logger.error("❌ SITEMAP_URLS 未设置")
        return False
    
    try:
        urls = json.loads(urls_json)
        if not isinstance(urls, list) or len(urls) == 0:
            logger.error("❌ SITEMAP_URLS 应为非空JSON数组")
            return False
        
        logger.info(f"✅ SITEMAP_URLS 包含 {len(urls)} 个URL")
        # 显示一些URL提示，但不完全展示
        for i, url in enumerate(urls):
            domain = url.split('//')[1].split('/')[0] if '//' in url else url.split('/')[0]
            logger.info(f"   URL {i+1}: 域名 {domain}")
    except json.JSONDecodeError:
        logger.error("❌ SITEMAP_URLS 不是有效的JSON格式")
        return False
    except Exception as e:
        logger.error(f"❌ 解析SITEMAP_URLS时出错: {e}")
        return False
    
    logger.info("✅ 所有环境变量格式正确")
    return True

def test_encryption():
    """测试加密和解密功能"""
    logger.info("开始测试加密功能...")
    
    try:
        # 获取加密密钥
        encryption_key_str = os.environ.get('ENCRYPTION_KEY', '')
        encryption_key = process_encryption_key(encryption_key_str)
        
        # 测试数据
        test_url = "https://example.com/test-page"
        
        # 加密
        iv = get_random_bytes(16)
        cipher = AES.new(encryption_key, AES.MODE_CBC, iv)
        padded_data = pad(test_url.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        # 使用Base64编码
        encrypted_b64 = base64.b64encode(encrypted_data).decode('utf-8')
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        
        logger.info(f"✅ 加密成功: {encrypted_b64[:10]}...")
        
        # 解密
        encrypted_data = base64.b64decode(encrypted_b64)
        iv = base64.b64decode(iv_b64)
        
        cipher = AES.new(encryption_key, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(encrypted_data)
        decrypted_data = unpad(decrypted_padded, AES.block_size)
        decrypted_url = decrypted_data.decode('utf-8')
        
        if decrypted_url == test_url:
            logger.info(f"✅ 解密成功: {test_url}")
            return True
        else:
            logger.error(f"❌ 解密结果与原始URL不匹配")
            return False
            
    except Exception as e:
        logger.error(f"❌ 加密测试失败: {e}")
        return False

def test_telegram():
    """测试Telegram Bot通知功能"""
    logger.info("开始测试Telegram通知...")
    
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    if not telegram_token or not chat_id:
        logger.error("❌ 缺少Telegram配置")
        return False
    
    try:
        # 构建测试消息
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"🧪 配置测试 - {timestamp}\n\n这是一条测试消息，验证Telegram通知功能是否正常。"
        
        # 发送消息
        api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        logger.info("正在发送Telegram测试消息...")
        response = requests.post(api_url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info("✅ Telegram测试消息发送成功")
            return True
        else:
            logger.error(f"❌ Telegram API返回错误: {response.status_code}, {response.text}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"❌ 发送Telegram消息失败: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Telegram测试出现未知错误: {e}")
        return False

def main():
    """执行所有测试"""
    logger.info("开始执行配置测试...")
    
    # 获取命令行参数
    args = sys.argv[1:]
    test_all = len(args) == 0 or "all" in args
    
    # 运行测试
    env_ok = test_environment_variables() if test_all or "env" in args else True
    encryption_ok = test_encryption() if test_all or "encryption" in args else True
    telegram_ok = test_telegram() if test_all or "telegram" in args else True
    
    # 汇总结果
    if env_ok and encryption_ok and telegram_ok:
        logger.info("🎉 所有测试通过！配置正确，可以开始使用。")
        return 0
    else:
        logger.error("❌ 部分测试失败，请检查上述错误并修复相关配置。")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 