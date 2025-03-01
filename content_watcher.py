#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多站点内容监控器
该脚本定期检查多个网站的更新，并通过Telegram发送通知
"""

import os
import json
import base64
import logging
import datetime
from typing import Dict, List, Tuple, Optional, Any
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import hashlib
import binascii
import argparse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('content_watcher')

# 文件路径
DATA_FILE = 'previous_data.json'

class ContentWatcher:
    """监控多个网站内容更新并发送通知"""
    
    def __init__(self, test_mode=False):
        """初始化监控器"""
        # 是否在测试模式下运行
        self.test_mode = test_mode
        
        # 获取密钥并处理格式
        encryption_key = os.environ.get('ENCRYPTION_KEY', '')
        self.encryption_key = self._process_encryption_key(encryption_key)
        
        self.telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        
        # 解析网站URL列表
        urls_json = os.environ.get('SITEMAP_URLS', '[]')
        self.website_urls = json.loads(urls_json)
        
        # 验证必要的环境变量
        self._validate_config()
        
        # 先前的数据
        self.previous_data = self._load_previous_data()
    
    def _process_encryption_key(self, key: str) -> bytes:
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
    
    def _validate_config(self) -> None:
        """验证配置是否有效"""
        if not self.encryption_key or len(self.encryption_key) != 32:
            logger.error("加密密钥无效或不是32字节")
            raise ValueError(f"ENCRYPTION_KEY必须是32字节，当前是{len(self.encryption_key)}字节")
            
        if not self.telegram_token and not self.test_mode:
            logger.error("未设置Telegram Bot Token")
            raise ValueError("未设置TELEGRAM_BOT_TOKEN")
            
        if not self.telegram_chat_id and not self.test_mode:
            logger.error("未设置Telegram Chat ID")
            raise ValueError("未设置TELEGRAM_CHAT_ID")
            
        if not self.website_urls and not self.test_mode:
            logger.error("未提供网站URL列表")
            raise ValueError("SITEMAP_URLS必须是有效的JSON数组")
    
    def _load_previous_data(self) -> Dict[str, List[Dict[str, str]]]:
        """加载先前保存的数据"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('sites', {})
            else:
                logger.info("先前的数据文件不存在，将创建新文件")
                return {}
        except Exception as e:
            logger.error(f"加载先前数据时出错: {e}")
            return {}
    
    def _save_data(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """保存数据到文件"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({'sites': data}, f, ensure_ascii=False, indent=2)
            logger.info("数据已保存到文件")
        except Exception as e:
            logger.error(f"保存数据时出错: {e}")
    
    def _encrypt_url(self, url: str) -> Tuple[str, str]:
        """加密URL，返回加密后的URL和IV"""
        iv = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        padded_data = pad(url.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        # 转为Base64编码便于存储
        encrypted_b64 = base64.b64encode(encrypted_data).decode('utf-8')
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        
        return encrypted_b64, iv_b64
    
    def _decrypt_url(self, encrypted_b64: str, iv_b64: str) -> str:
        """解密URL"""
        try:
            encrypted_data = base64.b64decode(encrypted_b64)
            iv = base64.b64decode(iv_b64)
            
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(encrypted_data)
            decrypted_data = unpad(decrypted_padded, AES.block_size)
            
            return decrypted_data.decode('utf-8')
        except Exception as e:
            logger.error(f"解密URL时出错: {e}")
            return ""
    
    def _get_site_identifier(self, url: str) -> str:
        """生成网站标识符，不暴露原始URL"""
        # 使用URL的哈希值作为标识符
        return hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
    
    def _format_site_name(self, site_id: str, index: int) -> str:
        """格式化网站名称用于通知"""
        return f"网站 {index+1} ({site_id})"
    
    def _is_updated_today(self, lastmod: Optional[str]) -> bool:
        """检查lastmod是否是今天的日期"""
        if not lastmod:
            return False
            
        try:
            # 解析ISO格式的日期
            lastmod_date = datetime.datetime.fromisoformat(lastmod.replace('Z', '+00:00'))
            today = datetime.datetime.now(datetime.timezone.utc).date()
            return lastmod_date.date() == today
        except Exception as e:
            logger.error(f"解析日期时出错: {lastmod}, {e}")
            return False
    
    def download_and_parse_sitemap(self, url: str) -> Dict[str, Optional[str]]:
        """下载并解析网站地图，返回URL和最后修改日期的映射"""
        sitemap_data = {}
        
        # 测试模式下使用模拟数据
        if self.test_mode:
            logger.info(f"测试模式：生成模拟站点地图数据 {self._get_site_identifier(url)}")
            # 创建一些测试数据
            base_url = url.split('/sitemap.xml')[0]
            today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
            
            # 模拟一些URL，其中一些是今天更新的
            test_paths = ['/page1', '/page2', '/page3', '/blog/post1', '/blog/post2']
            for i, path in enumerate(test_paths):
                full_url = f"{base_url}{path}"
                # 让部分URL显示为今天更新
                lastmod = today if i % 2 == 0 else '2025-01-01'
                sitemap_data[full_url] = lastmod
                
            logger.info(f"已生成模拟数据，{len(sitemap_data)} 个URL")
            return sitemap_data
            
        try:
            logger.info(f"正在下载网站地图: {self._get_site_identifier(url)}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # 解析XML
            root = ET.fromstring(response.content)
            
            # XML命名空间
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
            }
            
            # 查找所有URL条目
            for url_elem in root.findall('.//sm:url', namespaces):
                loc_elem = url_elem.find('./sm:loc', namespaces)
                lastmod_elem = url_elem.find('./sm:lastmod', namespaces)
                
                if loc_elem is not None and loc_elem.text:
                    url_text = loc_elem.text.strip()
                    lastmod_text = lastmod_elem.text.strip() if lastmod_elem is not None and lastmod_elem.text else None
                    sitemap_data[url_text] = lastmod_text
            
            logger.info(f"已解析网站地图，找到 {len(sitemap_data)} 个URL")
            return sitemap_data
            
        except requests.RequestException as e:
            logger.error(f"下载网站地图时出错: {e}")
            return {}
        except ET.ParseError as e:
            logger.error(f"解析XML时出错: {e}")
            return {}
        except Exception as e:
            logger.error(f"处理网站地图时出现未知错误: {e}")
            return {}
    
    def process_site(self, site_url: str, site_index: int) -> List[str]:
        """处理单个网站，返回今日更新的URL列表"""
        site_id = self._get_site_identifier(site_url)
        logger.info(f"正在处理网站 {site_index+1} ({site_id})")
        
        # 下载和解析网站地图
        sitemap_data = self.download_and_parse_sitemap(site_url)
        if not sitemap_data:
            logger.warning(f"网站 {site_id} 未返回有效数据")
            return []
        
        # 解密上一次的数据用于对比
        previous_urls = {}
        if site_id in self.previous_data:
            for item in self.previous_data[site_id]:
                if 'encrypted_url' in item and 'iv' in item:
                    decrypted_url = self._decrypt_url(item['encrypted_url'], item['iv'])
                    if decrypted_url:
                        previous_urls[decrypted_url] = item.get('lastmod')
        
        # 查找今天更新的URL
        updated_urls = []
        new_encrypted_data = []
        
        for url, lastmod in sitemap_data.items():
            # 检查URL是否今天更新
            is_new_or_updated = (
                url not in previous_urls or 
                (lastmod and previous_urls.get(url) != lastmod and self._is_updated_today(lastmod))
            )
            
            if is_new_or_updated and self._is_updated_today(lastmod):
                updated_urls.append(url)
            
            # 加密和保存所有URL
            encrypted_url, iv = self._encrypt_url(url)
            new_encrypted_data.append({
                'encrypted_url': encrypted_url,
                'iv': iv,
                'lastmod': lastmod
            })
        
        # 更新数据存储
        self.previous_data[site_id] = new_encrypted_data
        
        logger.info(f"网站 {site_id} 有 {len(updated_urls)} 个URL今天更新")
        return updated_urls
    
    def send_telegram_notification(self, updates_by_site: Dict[str, List[str]]) -> bool:
        """发送Telegram通知"""
        if not any(updates_by_site.values()):
            logger.info("没有更新，不发送通知")
            return True
        
        # 构建消息
        message_parts = []
        for site_index, (site_id, urls) in enumerate(updates_by_site.items()):
            if not urls:
                continue
                
            site_name = self._format_site_name(site_id, site_index)
            message_parts.append(f"{site_name} 今日更新:")
            
            # 限制每个网站最多显示10个URL
            for url in urls[:10]:
                message_parts.append(f"- {url}")
                
            if len(urls) > 10:
                message_parts.append(f"... 还有 {len(urls) - 10} 个更新未显示")
            
            message_parts.append("")  # 添加空行分隔
        
        message = "\n".join(message_parts).strip()
        
        # 测试模式下只打印消息
        if self.test_mode:
            logger.info("测试模式：模拟发送Telegram通知")
            logger.info(f"消息内容:\n{message}")
            return True
            
        # 发送消息
        try:
            api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info("已成功发送Telegram通知")
            return True
            
        except requests.RequestException as e:
            logger.error(f"发送Telegram通知时出错: {e}")
            return False
    
    def run(self) -> None:
        """执行监控流程"""
        logger.info("开始执行内容监控...")
        
        updates_by_site = {}
        
        # 处理每个网站
        for index, site_url in enumerate(self.website_urls):
            site_id = self._get_site_identifier(site_url)
            updated_urls = self.process_site(site_url, index)
            updates_by_site[site_id] = updated_urls
        
        # 发送通知
        self.send_telegram_notification(updates_by_site)
        
        # 保存数据
        self._save_data(self.previous_data)
        
        logger.info("内容监控完成")


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='多站点内容监控工具')
    parser.add_argument('--test', action='store_true', help='在测试模式下运行，使用模拟数据')
    args = parser.parse_args()
    
    try:
        watcher = ContentWatcher(test_mode=args.test)
        watcher.run()
    except Exception as e:
        logger.critical(f"执行过程中出现错误: {e}")
        exit(1) 