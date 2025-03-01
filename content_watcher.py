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
import re  # 添加正则表达式模块
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
        
        # 获取API URL
        self.api_url = os.environ.get('KEYWORDS_API_URL', '')
        
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
            
        if not self.telegram_token:
            logger.error("未设置Telegram Bot Token")
            raise ValueError("未设置TELEGRAM_BOT_TOKEN")
            
        if not self.telegram_chat_id:
            logger.error("未设置Telegram Chat ID")
            raise ValueError("未设置TELEGRAM_CHAT_ID")
            
        if not self.website_urls:
            logger.error("未提供网站URL列表")
            raise ValueError("SITEMAP_URLS必须是有效的JSON数组")
            
        if not self.api_url:
            logger.warning("未设置关键词API URL，将不会查询关键词信息")
    
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
    
    def _extract_keywords_from_url(self, url: str) -> str:
        """从URL中提取关键词
        
        例如：从 https://sprunkly.org/game/sprunki-retake-final-update 提取 'sprunki retake final update'
        """
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        # 如果路径至少有一部分，取最后一部分作为关键词
        if path_parts and path_parts[-1]:
            keywords = path_parts[-1]
            # 将连字符替换为空格，使关键词更可读
            keywords = keywords.replace('-', ' ')
            return keywords
        
        return ""
    
    def _get_keyword_info(self, keywords: str) -> Dict[str, Any]:
        """调用API获取关键词的相关信息
        
        Args:
            keywords: 从URL提取的关键词，可以是单个关键词或逗号分隔的多个关键词
            
        Returns:
            包含API返回信息的字典，如果调用失败则返回空字典
        """
        if not keywords or not self.api_url:
            return {}
            
        try:
            # 对关键词进行URL编码，确保空格和特殊字符被正确处理
            encoded_keywords = requests.utils.quote(keywords)
            
            # 构建完整URL，将编码后的关键词附加到查询参数中
            full_url = f"{self.api_url}{encoded_keywords}"
            logger.info(f"调用API获取关键词信息: {full_url}")
            
            # 发送GET请求
            response = requests.get(
                full_url,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            
            # 解析JSON响应
            data = response.json()
            logger.info(f"成功获取关键词 '{keywords}' 的信息")
            return data
            
        except requests.RequestException as e:
            logger.error(f"调用关键词API时出错: {e}")
            return {}
        except ValueError as e:
            logger.error(f"解析API响应JSON时出错: {e}")
            return {}
        except Exception as e:
            logger.error(f"处理关键词信息时出现未知错误: {e}")
            return {}
    
    def _format_keyword_info(self, info: Dict[str, Any]) -> str:
        """将API返回的信息格式化为用户可读的文本
        
        Args:
            info: API返回的信息字典
            
        Returns:
            格式化后的文本，包含关键词搜索量、竞争度和月度趋势数据
        """
        if not info or not isinstance(info, dict):
            return ""
        
        # 检查API状态    
        status = info.get("status", "")
        if status != "success" or "data" not in info:
            return "⚠️ 未找到关键词数据"
            
        data = info.get("data", [])
        if not data:
            return "📊 没有相关的关键词数据"
            
        # 构建格式化文本
        parts = []
        parts.append(f"📊 <b>关键词搜索数据</b> ({info.get('geo_target', '全球')})")
        parts.append(f"🔍 总结果数: {info.get('total_results', 0)}")
        
        # 对关键词数据进行排序，月均搜索量高的排在前面
        sorted_data = sorted(
            data, 
            key=lambda x: x.get('metrics', {}).get('avg_monthly_searches', 0),
            reverse=True
        )
        
        # 显示所有关键词的详细数据
        for i, keyword_data in enumerate(sorted_data):
            keyword = keyword_data.get("keyword", "未知关键词")
            metrics = keyword_data.get("metrics", {})
            
            avg_searches = metrics.get("avg_monthly_searches", 0)
            competition = metrics.get("competition", "N/A")
            competition_index = metrics.get("competition_index", "N/A")
            
            # 竞争度文字表示
            competition_text = "未知"
            if competition == "LOW":
                competition_text = "低"
            elif competition == "MEDIUM":
                competition_text = "中"
            elif competition == "HIGH":
                competition_text = "高"
            elif competition == "N/A":
                competition_text = "无数据"
                
            # 添加关键词信息
            parts.append(f"\n🔑 <b>{keyword}</b>")
            parts.append(f"  • 月均搜索量: <b>{avg_searches}</b> | 竞争度: <b>{competition_text}</b> ({competition_index})")
            
            # 获取月度搜索数据并显示趋势
            monthly_searches = metrics.get("monthly_searches", [])
            if monthly_searches:
                # 按时间顺序排序月度数据
                monthly_searches = sorted(
                    monthly_searches,
                    key=lambda x: (x.get("year", ""), x.get("month", ""))
                )
                
                # 显示月度趋势
                trend_parts = []
                trend_parts.append("  • 月度趋势:")
                
                for month_info in monthly_searches:
                    year = month_info.get("year", "")
                    month = month_info.get("month", "")
                    searches = month_info.get("searches", 0)
                    
                    # 将月份名称转换为短格式
                    month_short = month[:3] if month else ""
                    
                    # 根据搜索量显示不同的图标
                    icon = "📈" if searches > avg_searches else "📉" if searches < avg_searches else "➡️"
                    
                    trend_parts.append(f"    {icon} {year}/{month_short}: <b>{searches}</b>")
                
                parts.extend(trend_parts)
        
        return "\n".join(parts)
    
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
    
    def _batch_query_keywords(self, url_keywords_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """批量查询多个URL的关键词信息
        
        Args:
            url_keywords_map: URL到关键词的映射
            
        Returns:
            URL到API响应结果的映射
        """
        if not url_keywords_map or not self.api_url:
            return {}
            
        # 准备结果字典
        results = {}
        
        # 如果只有一个URL，直接查询
        if len(url_keywords_map) == 1:
            url = next(iter(url_keywords_map))
            keywords = url_keywords_map[url]
            if keywords:
                results[url] = self._get_keyword_info(keywords)
            return results
            
        # 将所有关键词合并为一个列表
        all_keywords = []
        url_to_keyword = {}
        
        for url, keywords in url_keywords_map.items():
            if keywords:
                all_keywords.append(keywords)
                url_to_keyword[url] = keywords
        
        # 如果没有有效的关键词，返回空结果
        if not all_keywords:
            return {}
            
        # 批次处理，每批最多10个关键词
        batch_size = 10
        for i in range(0, len(all_keywords), batch_size):
            batch_keywords = all_keywords[i:i+batch_size]
            
            # 合并关键词为逗号分隔的字符串
            combined_keywords = "，".join(batch_keywords)
            
            # 获取批量关键词数据
            batch_data = self._get_keyword_info(combined_keywords)
            
            # 如果请求成功，将结果分配给各个URL
            if batch_data and 'data' in batch_data and batch_data.get('status') == 'success':
                # 为每个关键词找到对应的URL
                for keyword_data in batch_data.get('data', []):
                    keyword = keyword_data.get('keyword', '')
                    
                    # 查找这个关键词对应的URL
                    for url, kw in url_to_keyword.items():
                        if keyword.lower() in kw.lower():
                            # 为该URL创建结果集合
                            if url not in results:
                                results[url] = {
                                    'status': 'success',
                                    'geo_target': batch_data.get('geo_target', '全球'),
                                    'total_results': 0,
                                    'data': []
                                }
                            
                            # 添加关键词数据
                            results[url]['data'].append(keyword_data)
                            results[url]['total_results'] = len(results[url]['data'])
        
        return results

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
            
            # 收集所有URL和它们的关键词
            url_keywords_map = {}
            for url in urls:
                # 提取URL中的关键词
                keywords = self._extract_keywords_from_url(url)
                if keywords:
                    url_keywords_map[url] = keywords
            
            # 批量查询关键词信息
            keyword_results = self._batch_query_keywords(url_keywords_map)
            
            # 显示所有更新的URL
            for url in urls:
                message_parts.append(f"- {url}")
                
                # 提取URL中的关键词
                keywords = self._extract_keywords_from_url(url)
                if keywords:
                    message_parts.append(f"  关键词: {keywords}")
                    
                    # 添加关键词信息到消息中
                    if url in keyword_results:
                        formatted_info = self._format_keyword_info(keyword_results[url])
                        if formatted_info:
                            message_parts.append(f"  详情:\n    {formatted_info}")
            
            message_parts.append("")  # 添加空行分隔
        
        message = "\n".join(message_parts).strip()
        
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
    args = parser.parse_args()
    
    try:
        watcher = ContentWatcher()
        watcher.run()
    except Exception as e:
        logger.critical(f"执行过程中出现错误: {e}")
        exit(1) 