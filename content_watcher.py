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
import time

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
    
    def __init__(self, test_mode=False, max_first_run_updates=50):
        """初始化监控器
        
        Args:
            test_mode: 是否在测试模式下运行
            max_first_run_updates: 首次运行时最多报告的更新数量
        """
        # 是否在测试模式下运行
        self.test_mode = test_mode
        
        # 首次运行时最多报告的更新数量
        self.max_first_run_updates = max_first_run_updates
        
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
    
    def _encrypt_url(self, url: str) -> str:
        """加密URL，返回加密后的URL（包含IV）"""
        iv = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        padded_data = pad(url.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        # 将IV和加密数据组合在一起
        combined = iv + encrypted_data
        # 转为Base64编码便于存储
        return base64.b64encode(combined).decode('utf-8')
    
    def _decrypt_url(self, encrypted_data: str) -> str:
        """解密URL"""
        try:
            # 解码Base64数据
            combined = base64.b64decode(encrypted_data)
            
            # 提取IV和加密数据
            iv = combined[:16]
            encrypted = combined[16:]
            
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(encrypted)
            decrypted_data = unpad(decrypted_padded, AES.block_size)
            
            return decrypted_data.decode('utf-8')
        except Exception as e:
            logger.error(f"解密URL时出错: {e}")
            return ""
    
    def _get_site_identifier(self, url: str) -> str:
        """获取网站标识符"""
        try:
            parsed = urlparse(url)
            # 使用主机名前8个字符作为站点ID
            return hashlib.md5(parsed.netloc.encode()).hexdigest()[:8]
        except Exception:
            # 如果解析失败，使用MD5哈希值的前8个字符
            return hashlib.md5(url.encode()).hexdigest()[:8]
    
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
            # 构建API请求URL
            api_request_url = f"{self.api_url}{keywords}"
            logger.info(f"调用关键词API: {api_request_url}")
            
            response = requests.get(api_request_url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"API请求失败，状态码: {response.status_code}")
                return {}
                
            data = response.json()
            # 只记录API状态和结果数量，不记录完整响应内容
            status = data.get('status', 'unknown')
            total_results = len(data.get('data', []))
            logger.info(f"API响应状态: {status}, 结果数量: {total_results}")
            return data
            
        except requests.RequestException as e:
            logger.error(f"请求关键词API时出错: {e}")
            return {}
        except ValueError as e:
            logger.error(f"解析API响应时出错: {e}")
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
                if 'encrypted_url' in item:
                    decrypted_url = self._decrypt_url(item['encrypted_url'])
                    if decrypted_url:
                        previous_urls[decrypted_url] = item.get('lastmod')
        
        # 检查是否是首次运行（没有历史数据）
        is_first_run = len(previous_urls) == 0
        
        # 查找今天更新的URL
        updated_urls = []
        new_encrypted_data = []
        
        for url, lastmod in sitemap_data.items():
            # 检查URL是否为新URL或今天更新的URL
            is_new = url not in previous_urls
            
            # 对于已存在的URL，检查lastmod是否更新
            is_updated = False
            if not is_new and lastmod:
                previous_lastmod = previous_urls.get(url)
                is_updated = previous_lastmod != lastmod and self._is_updated_today(lastmod)
            
            # 新URL或今天更新的URL都被视为"今天的更新"
            if is_new or is_updated:
                # 首次运行时，可能有大量URL被认为是"新的"
                # 为了避免发送过多通知，限制首次运行时报告的更新数量
                if not is_first_run or len(updated_urls) < self.max_first_run_updates:
                    updated_urls.append(url)
                    # 记录检测到更新的原因，帮助调试
                    if is_new:
                        logger.info(f"检测到新URL: {url}")
                    else:
                        logger.info(f"检测到URL更新: {url}, 前一个lastmod: {previous_urls.get(url)}, 新lastmod: {lastmod}")
            
            # 加密和保存所有URL
            encrypted_url = self._encrypt_url(url)
            new_encrypted_data.append({
                'encrypted_url': encrypted_url,
                'lastmod': lastmod
            })
        
        # 更新数据存储
        self.previous_data[site_id] = new_encrypted_data
        
        # 如果是首次运行并且有大量更新，记录日志
        if is_first_run and len(sitemap_data) > self.max_first_run_updates:
            logger.info(f"首次运行，网站 {site_id} 共有 {len(sitemap_data)} 个URL，但只报告了前 {len(updated_urls)} 个")
            
        logger.info(f"网站 {site_id} 有 {len(updated_urls)} 个URL今天更新")
        return updated_urls
    
    def _batch_query_keywords(self, url_keywords_map: Dict[str, str], is_first_run: bool = False) -> Dict[str, Dict[str, Any]]:
        """批量查询多个URL的关键词信息
        
        Args:
            url_keywords_map: URL到关键词的映射
            is_first_run: 是否是首次运行，首次运行时不查询API
            
        Returns:
            URL到API响应结果的映射
        """
        # 首次运行时不查询关键词API
        if is_first_run:
            logger.info("首次运行，跳过关键词API查询")
            return {}
            
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
            
        # 批次处理，每批处理5个关键词
        batch_size = 5
        for i in range(0, len(all_keywords), batch_size):
            batch_keywords = all_keywords[i:i+batch_size]
            
            # 合并关键词为逗号分隔的字符串
            combined_keywords = "，".join(batch_keywords)
            
            # 最大重试次数
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                # 获取批量关键词数据
                batch_data = self._get_keyword_info(combined_keywords)
                
                # 检查是否成功
                if batch_data and 'status' in batch_data and batch_data.get('status') == 'success':
                    success = True
                    
                    # 为每个关键词找到对应的URL
                    for keyword_data in batch_data.get('data', []):
                        keyword = keyword_data.get('keyword', '')
                        
                        # 查找这个关键词对应的URL
                        for url, kw in url_to_keyword.items():
                            if keyword.lower() in kw.lower() or kw.lower() in keyword.lower():
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
                else:
                    # 如果API返回错误，尝试减少批次大小再次请求
                    retry_count += 1
                    if retry_count < max_retries:
                        # 如果批次大小大于1，减半后重试
                        if len(batch_keywords) > 1:
                            logger.warning(f"API请求失败，减少批次大小并重试 ({retry_count}/{max_retries})")
                            # 处理当前批次的一半
                            half_size = max(1, len(batch_keywords) // 2)
                            first_half = batch_keywords[:half_size]
                            second_half = batch_keywords[half_size:]
                            
                            # 处理第一半
                            first_combined = "，".join(first_half)
                            first_data = self._get_keyword_info(first_combined)
                            if first_data and 'status' in first_data and first_data.get('status') == 'success':
                                self._process_batch_results(first_data, url_to_keyword, results)
                            
                            # 处理第二半
                            if second_half:
                                second_combined = "，".join(second_half)
                                second_data = self._get_keyword_info(second_combined)
                                if second_data and 'status' in second_data and second_data.get('status') == 'success':
                                    self._process_batch_results(second_data, url_to_keyword, results)
                            
                            success = True  # 已手动处理，不需要继续重试
                        else:
                            # 如果只有一个关键词，可能是关键词本身问题，等待一段时间后重试
                            logger.warning(f"单个关键词查询失败，等待后重试: {batch_keywords[0]}")
                            time.sleep(1.5)  # 等待1.5秒后重试
                    else:
                        logger.error(f"达到最大重试次数，放弃处理批次: {combined_keywords}")
            
            # 请求之间添加短暂延迟，避免API速率限制
            if i + batch_size < len(all_keywords):
                time.sleep(1)  # 增加延迟到1秒，减少并发压力
        
        return results
    
    def _process_batch_results(self, batch_data: Dict[str, Any], url_to_keyword: Dict[str, str], 
                              results: Dict[str, Dict[str, Any]]) -> None:
        """处理批量查询结果
        
        Args:
            batch_data: API返回的数据
            url_to_keyword: URL到关键词的映射
            results: 结果字典，会被此函数修改
        """
        if not batch_data or 'data' not in batch_data:
            return
            
        for keyword_data in batch_data.get('data', []):
            keyword = keyword_data.get('keyword', '')
            
            # 查找这个关键词对应的URL
            for url, kw in url_to_keyword.items():
                if keyword.lower() in kw.lower() or kw.lower() in keyword.lower():
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

    def send_telegram_notification(self, updates_by_site: Dict[str, List[str]]) -> bool:
        """发送Telegram通知"""
        if not any(updates_by_site.values()):
            logger.info("没有更新，不发送通知")
            return True
        
        # 计算总更新数量
        total_updates = sum(len(urls) for urls in updates_by_site.values())
        logger.info(f"准备发送通知，共有 {total_updates} 个更新")
        
        # 检查是否是首次运行
        is_first_run = self._is_first_run()
        if is_first_run:
            logger.info("首次运行，通知中将不包含关键词API信息")
        
        # 构建消息
        message_parts = []
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        message_parts.append(f"🔔 <b>网站内容更新通知</b> ({current_date})")
        message_parts.append(f"")
        message_parts.append(f"共发现 {total_updates} 个更新")
        message_parts.append(f"")
        
        for site_index, (site_id, urls) in enumerate(updates_by_site.items()):
            if not urls:
                continue
                
            site_name = self._format_site_name(site_id, site_index)
            message_parts.append(f"<b>{site_name}</b> 更新了 {len(urls)} 个URL:")
            
            # 收集所有URL和它们的关键词
            url_keywords_map = {}
            for url in urls:
                # 提取URL中的关键词
                keywords = self._extract_keywords_from_url(url)
                if keywords:
                    url_keywords_map[url] = keywords
            
            # 批量查询关键词信息，传入首次运行标志
            keyword_results = self._batch_query_keywords(url_keywords_map, is_first_run)
            
            # 根据URL数量选择不同的显示模式
            if len(urls) <= 10:
                # 少量URL时使用详细模式
                self._format_detailed_updates(message_parts, urls, url_keywords_map, keyword_results)
            elif len(urls) <= 30:
                # 中等数量URL时使用紧凑模式
                self._format_compact_updates(message_parts, urls, url_keywords_map, keyword_results)
            else:
                # 大量URL时使用分类汇总模式
                self._format_summary_updates(message_parts, urls, url_keywords_map, keyword_results)
            
            message_parts.append("")  # 添加空行分隔
        
        message = "\n".join(message_parts).strip()
        
        # 检查消息长度，避免超过Telegram消息长度限制
        if len(message) > 4000:
            logger.warning(f"消息长度 ({len(message)}) 超过Telegram限制，将进一步截断")
            message = message[:3900] + "...\n\n(消息已截断，更多信息请查看日志)"
        
        # 发送消息
        try:
            api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True  # 禁用网页预览，避免消息太长
            }
            
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info("已成功发送Telegram通知")
            return True
            
        except requests.RequestException as e:
            logger.error(f"发送Telegram通知时出错: {e}")
            return False
    
    def _format_detailed_updates(self, message_parts: List[str], urls: List[str], 
                                url_keywords_map: Dict[str, str], 
                                keyword_results: Dict[str, Dict[str, Any]]) -> None:
        """格式化详细的更新信息，适用于少量URL
        
        Args:
            message_parts: 消息部分列表，会被此函数修改
            urls: URL列表
            url_keywords_map: URL到关键词的映射
            keyword_results: URL到API响应结果的映射
        """
        # 显示每个URL的详细信息
        for i, url in enumerate(urls, 1):
            message_parts.append(f"{i}. <a href='{url}'>{url.split('/')[-1].replace('-', ' ')}</a>")
            
            # 提取URL中的关键词
            keywords = url_keywords_map.get(url, "")
            if keywords:
                message_parts.append(f"   关键词: {keywords}")
                
                # 添加关键词信息到消息中
                if url in keyword_results:
                    api_data = keyword_results[url]
                    data_items = api_data.get('data', [])
                    
                    if data_items:
                        # 显示关键词和总结果数
                        total_results = api_data.get('total_results', 0)
                        
                        # 收集前两个关键词及其数据
                        keyword_info = []
                        for kw_data in data_items[:2]:  # 只显示前2个关键词
                            keyword = kw_data.get('keyword', '')
                            metrics = kw_data.get('metrics', {})
                            
                            avg_searches = metrics.get('avg_monthly_searches', 0)
                            competition = metrics.get('competition', 'N/A')
                            
                            # 根据竞争度选择图标
                            icon = "🟢" if competition == "LOW" else "🟡" if competition == "MEDIUM" else "🔴" if competition == "HIGH" else "⚪"
                            
                            # 添加关键词信息
                            keyword_info.append(f"{icon}{keyword}({avg_searches})")
                            
                            # 获取月度搜索数据
                            monthly_searches = metrics.get("monthly_searches", [])
                            if monthly_searches:
                                # 按时间顺序排序月度数据
                                monthly_searches = sorted(
                                    monthly_searches,
                                    key=lambda x: (x.get("year", ""), x.get("month", ""))
                                )
                                
                                # 创建月度趋势字符串
                                month_trends = []
                                for month_info in monthly_searches[-6:]:  # 只显示最近6个月
                                    year = month_info.get("year", "")
                                    month = month_info.get("month", "")
                                    searches = month_info.get("searches", 0)
                                    
                                    # 将月份名称转换为短格式
                                    month_short = month[:3] if month else ""
                                    month_trends.append(f"{year}/{month_short}:{searches}")
                                
                                # 添加月度趋势到关键词信息
                                message_parts.append(f"   📊 {keyword}月度趋势: {', '.join(month_trends)}")
                        
                        # 显示总结果数和关键词搜索量
                        message_parts.append(f"   总结果数: {total_results} | {' '.join(keyword_info)}")
    
    def _format_compact_updates(self, message_parts: List[str], urls: List[str], 
                               url_keywords_map: Dict[str, str], 
                               keyword_results: Dict[str, Dict[str, Any]]) -> None:
        """格式化紧凑的更新信息，适用于中等数量URL
        
        Args:
            message_parts: 消息部分列表，会被此函数修改
            urls: URL列表
            url_keywords_map: URL到关键词的映射
            keyword_results: URL到API响应结果的映射
        """
        # 创建更紧凑的格式
        compact_urls = []
        for i, url in enumerate(urls[:20], 1):  # 最多显示20个URL
            # 提取URL名称
            url_name = url.split('/')[-1].replace('-', ' ')
            
            # 提取关键词信息
            keywords = url_keywords_map.get(url, "")
            search_volume = "N/A"
            
            if url in keyword_results:
                # 提取搜索量信息
                try:
                    data = keyword_results[url].get('data', [])
                    if data:
                        # 获取第一个关键词的月均搜索量
                        metrics = data[0].get('metrics', {})
                        avg_searches = metrics.get('avg_monthly_searches', 0)
                        competition = metrics.get('competition', 'N/A')
                        
                        # 根据竞争度选择不同的图标
                        icon = "🟢" if competition == "LOW" else "🟡" if competition == "MEDIUM" else "🔴" if competition == "HIGH" else "⚪"
                        search_volume = f"{icon}{avg_searches}"
                except Exception:
                    pass
            
            # 创建紧凑格式的URL条目
            compact_url = f"{i}. <a href='{url}'>{url_name}</a>"
            if search_volume != "N/A":
                compact_url += f" [{search_volume}]"
            
            compact_urls.append(compact_url)
        
        # 添加URL到消息中
        message_parts.extend(compact_urls)
        
        # 如果URL数量超过20个，添加提示信息
        if len(urls) > 20:
            message_parts.append(f"...以及其他 {len(urls) - 20} 个更新 (仅显示前20个)")
    
    def _format_summary_updates(self, message_parts: List[str], urls: List[str], 
                               url_keywords_map: Dict[str, str], 
                               keyword_results: Dict[str, Dict[str, Any]]) -> None:
        """格式化汇总更新信息，适用于大量URL
        
        Args:
            message_parts: 消息部分列表，会被此函数修改
            urls: URL列表
            url_keywords_map: URL到关键词的映射
            keyword_results: URL到API响应结果的映射
        """
        # 按搜索量对URL进行分组
        high_volume = []  # >1000
        medium_volume = []  # 100-1000
        low_volume = []  # <100
        no_data = []  # 没有数据
        
        for url in urls:
            search_volume = 0
            has_data = False
            
            if url in keyword_results:
                try:
                    data = keyword_results[url].get('data', [])
                    if data:
                        metrics = data[0].get('metrics', {})
                        search_volume = metrics.get('avg_monthly_searches', 0)
                        has_data = True
                except Exception:
                    pass
            
            # 根据搜索量分组
            url_name = url.split('/')[-1].replace('-', ' ')
            url_link = f"<a href='{url}'>{url_name}</a>"
            
            if not has_data:
                no_data.append(url_link)
            elif search_volume > 1000:
                high_volume.append((url_link, search_volume))
            elif search_volume >= 100:
                medium_volume.append((url_link, search_volume))
            else:
                low_volume.append((url_link, search_volume))
        
        # 排序各组内的URL
        high_volume.sort(key=lambda x: x[1], reverse=True)
        medium_volume.sort(key=lambda x: x[1], reverse=True)
        low_volume.sort(key=lambda x: x[1], reverse=True)
        
        # 添加高搜索量组
        if high_volume:
            message_parts.append("<b>🔴 高搜索量 (>1000):</b>")
            for i, (url_link, volume) in enumerate(high_volume[:10], 1):
                message_parts.append(f"{i}. {url_link} [{volume}]")
            if len(high_volume) > 10:
                message_parts.append(f"...以及其他 {len(high_volume) - 10} 个高搜索量更新")
        
        # 添加中搜索量组
        if medium_volume:
            message_parts.append("<b>🟡 中搜索量 (100-1000):</b>")
            for i, (url_link, volume) in enumerate(medium_volume[:8], 1):
                message_parts.append(f"{i}. {url_link} [{volume}]")
            if len(medium_volume) > 8:
                message_parts.append(f"...以及其他 {len(medium_volume) - 8} 个中搜索量更新")
        
        # 添加低搜索量组
        if low_volume:
            message_parts.append("<b>🟢 低搜索量 (<100):</b>")
            for i, (url_link, volume) in enumerate(low_volume[:5], 1):
                message_parts.append(f"{i}. {url_link} [{volume}]")
            if len(low_volume) > 5:
                message_parts.append(f"...以及其他 {len(low_volume) - 5} 个低搜索量更新")
        
        # 添加无数据组
        if no_data:
            message_parts.append("<b>⚪ 无搜索数据:</b>")
            no_data_count = min(5, len(no_data))
            message_parts.append(", ".join(no_data[:no_data_count]))
            if len(no_data) > 5:
                message_parts.append(f"...以及其他 {len(no_data) - 5} 个无数据更新")

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

    def _is_first_run(self) -> bool:
        """判断是否是首次运行
        
        通过检查历史数据来判断是否是首次运行。如果没有历史数据，
        或者所有网站的历史URL数量为0，则认为是首次运行。
        
        Returns:
            是否是首次运行
        """
        # 如果历史数据文件不存在，肯定是首次运行
        if not os.path.exists(DATA_FILE):
            return True
            
        # 如果历史数据为空，也是首次运行
        if not self.previous_data:
            return True
            
        # 检查每个网站的历史URL数量
        for site_id, site_data in self.previous_data.items():
            if site_data and len(site_data) > 0:
                # 有至少一个网站有历史数据，不是首次运行
                return False
                
        # 所有网站都没有历史数据，是首次运行
        return True


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='多站点内容监控工具')
    parser.add_argument('--max-updates', type=int, default=50, 
                        help='首次运行时最多报告的更新数量，默认为50')
    args = parser.parse_args()
    
    try:
        watcher = ContentWatcher(max_first_run_updates=args.max_updates)
        watcher.run()
    except Exception as e:
        logger.critical(f"执行过程中出现错误: {e}")
        exit(1) 