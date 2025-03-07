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
import random  # 确保导入random模块

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
            
        # 记录API URL的设置情况
        logger.info(f"关键词API URL设置状态: 【{self.api_url}】, 长度: {len(self.api_url)}")
            
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
        """检查lastmod日期是否是今天"""
        if not lastmod:
            return False
            
        try:
            date_str = lastmod.split('T')[0]  # 提取日期部分
            lastmod_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            today = datetime.datetime.now().date()
            return lastmod_date == today
        except (ValueError, IndexError):
            return False

    def _should_exclude_url(self, url: str) -> bool:
        """检查URL是否应该被排除
        
        排除以下类型的URL:
        1. 以.games结尾的域名
        2. 包含/mahjong.games的路径
        3. 包含其他不需要的游戏相关路径
        4. 包含/tag/的路径（标签页面）
        
        Args:
            url: 要检查的URL
            
        Returns:
            如果URL应该被排除返回True，否则返回False
        """
        # 解析URL以获取域名和路径
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path
        
        # 检查域名是否以.games结尾
        if domain.endswith('.games'):
            logger.debug("排除以.games结尾的域名")
            return True
            
        # 检查路径中是否包含.games
        if '.games' in path:
            logger.debug("排除路径中包含.games的URL")
            return True
            
        # 检查路径中是否包含/tag/
        if '/tag/' in path:
            logger.debug("排除标签页面URL")
            return True
            
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
                    
                    # 检查URL是否应该被排除
                    if self._should_exclude_url(url_text):
                        continue
                        
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
        
        Args:
            url: 待提取关键词的URL
            
        Returns:
            提取出的关键词字符串，如果无法提取则返回空字符串
        """
        try:
            # 解析URL获取路径
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            # 如果路径为空则返回空字符串
            if not path_parts:
                return ""
            
            # 1. 检查是否为纯数字路径（如 /sitemap/games/33）
            if path_parts[-1].isdigit():
                logger.debug("URL路径以纯数字结尾，跳过关键词提取")
                return ""
                
            # 检查路径的最后部分是否以.games结尾
            if path_parts[-1].endswith('.games'):
                logger.debug("URL路径以.games结尾，跳过关键词提取")
                return ""
            
            # 2. 检查网站特定结构
            # 例如: /game/territory-war 中，提取 territory-war 作为关键词
            if len(path_parts) >= 2 and path_parts[-2] == "game":
                keywords = path_parts[-1].replace('-', ' ')
                logger.debug(f"从游戏URL提取关键词: {keywords}")
                return keywords
            
            # 3. 其他情况：一般页面提取最后一部分作为关键词
            # 如果最后部分看起来像是 ID 或太短（少于3个字符），则尝试使用前一部分
            last_part = path_parts[-1]
            if len(last_part) < 3 or last_part.isdigit() or re.match(r'^[a-f0-9]+$', last_part):
                # 如果路径只有一部分则返回空字符串
                if len(path_parts) < 2:
                    return ""
                # 否则使用倒数第二部分
                last_part = path_parts[-2]
            
            # 将连字符替换为空格
            keywords = last_part.replace('-', ' ')
            
            # 如果关键词看起来很不合理（例如太长或太短），记录日志但仍返回
            if len(keywords) < 3 or len(keywords) > 50:
                logger.debug(f"提取的关键词可能不合理: {keywords}")
            
            return keywords
            
        except Exception as e:
            logger.error(f"提取关键词时出错: {e}")
            return ""
    
    def _get_keyword_info(self, keywords: str) -> Dict[str, Any]:
        """调用API获取关键词的相关信息
        
        Args:
            keywords: 从URL提取的关键词，可以是单个关键词或逗号分隔的多个关键词
            
        Returns:
            包含API返回信息的字典，如果调用失败则返回空字典
        """
        # logger.info(f"当前的关键词: {keywords}")
        if not keywords or not self.api_url:
            return {}
            
        try:

            # 构建API请求URL
            api_request_url = f"{self.api_url}{keywords}"
            # logger.info(f"调用关键词API: {api_request_url}")
            
            response = requests.get(api_request_url, timeout=80)
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
        
        # 对关键词数据进行排序，月均搜索量高的排在前面
        sorted_data = sorted(
            data, 
            key=lambda x: x.get('metrics', {}).get('avg_monthly_searches', 0),
            reverse=True
        )
        
        # 只显示搜索量最大的关键词
        if sorted_data:
            keyword_data = sorted_data[0]
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
                    month_short = month[:3].title() if month else ""
                    
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
        
        # 计数器
        new_url_count = 0
        updated_url_count = 0
        
        for url, lastmod in sitemap_data.items():
            # 检查URL是否为新URL或今天更新的URL
            is_new = url not in previous_urls
            
            # 对于已存在的URL，检查lastmod是否更新
            is_updated = False
            if not is_new and lastmod:
                prev_lastmod = previous_urls.get(url)
                if prev_lastmod != lastmod and self._is_updated_today(lastmod):
                    is_updated = True
            
            # 添加新URL或更新的URL
            if is_new or is_updated:
                if is_new:
                    new_url_count += 1
                else:
                    updated_url_count += 1
                
                updated_urls.append(url)
            
            # 创建加密后的URL数据以保存
            encrypted_url = self._encrypt_url(url)
            new_encrypted_data.append({
                'encrypted_url': encrypted_url,
                'lastmod': lastmod
            })
        
        # 如果没有变化，直接返回空列表
        if not updated_urls:
            logger.info(f"网站 {site_id} 没有发现更新")
            
            # 更新储存的数据
            self.previous_data[site_id] = new_encrypted_data
            self._save_data(self.previous_data)
            
            return []
            
        # 提取更新URL的关键词
        url_keywords_map = {}
        for url in updated_urls:
            keyword = self._extract_keywords_from_url(url)
            url_keywords_map[url] = keyword
        
        # 如果是首次运行且URL数量很多，限制通知的URL数量
        if is_first_run and len(updated_urls) > self.max_first_run_updates:
            logger.info(f"首次运行，更新URL数量({len(updated_urls)})超过限制({self.max_first_run_updates})，将只发送部分更新")
            # 随机选择一些URL作为示例
            import random
            sample_urls = random.sample(updated_urls, self.max_first_run_updates)
            updated_urls = sample_urls
            # 更新关键词映射
            url_keywords_map = {url: url_keywords_map[url] for url in updated_urls if url in url_keywords_map}
        
        # 构建通知消息
        message_parts = []
        message_parts.append(f"🔔 <b>网站内容更新通知</b> ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        message_parts.append(f"\n共发现 {len(updated_urls)} 个更新")
        
        # 批量查询关键词信息
        keyword_results = {}
        if not is_first_run and url_keywords_map:
            try:
                # 获取所有关键词列表
                keywords_list = list(url_keywords_map.values())
                # 批量查询关键词
                raw_keyword_data = self._batch_query_keywords(keywords_list)
                
                # 将关键词数据转换为URL到API响应的映射
                for url, keyword in url_keywords_map.items():
                    if keyword in raw_keyword_data:
                        # 为每个URL创建一个包含完整API响应格式的结果
                        keyword_results[url] = {
                            'status': 'success',
                            'geo_target': '全球',
                            'total_results': 1,
                            'data': [raw_keyword_data[keyword]]  # 添加原始关键词数据
                        }
                        
                        # 查找关键词的相关关键词，最多添加3个高搜索量的相关词
                        related_keywords = []
                        for k, v in raw_keyword_data.items():
                            # 跳过与原始关键词完全相同的项
                            if k.lower() == keyword.lower():
                                continue
                                
                            # 检查是否与原始关键词有关联性（包含关系或相似性）
                            if (keyword.lower() in k.lower() or 
                                k.lower() in keyword.lower() or 
                                self._calculate_similarity(k.lower(), keyword.lower()) > 0.5):
                                related_keywords.append(v)
                        
                        # 按搜索量排序并添加最多3个相关关键词
                        if related_keywords:
                            related_keywords.sort(
                                key=lambda x: x.get('metrics', {}).get('avg_monthly_searches', 0),
                                reverse=True
                            )
                            # 添加最多3个高搜索量的相关词
                            for related in related_keywords[:3]:
                                keyword_results[url]['data'].append(related)
                                keyword_results[url]['total_results'] += 1
            except Exception as e:
                logger.error(f"批量查询关键词信息时出错: {e}")
        
        # 格式化详细更新信息
        self._format_detailed_updates(message_parts, updated_urls, url_keywords_map, keyword_results)
        
        # 发送通知消息
        notification_sent = self.send_telegram_notification({
            site_id: message_parts
        })
        
        # 更新数据存储
        self.previous_data[site_id] = new_encrypted_data
        self._save_data(self.previous_data)
        
        # 记录统计信息
        logger.info(f"网站 {site_id} 统计: 新URL数量: {new_url_count}, 更新URL数量: {updated_url_count}, 总计: {len(updated_urls)}")
        
        return updated_urls
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """计算两个字符串的相似度，使用简单的Jaccard相似度
        
        Args:
            str1: 第一个字符串
            str2: 第二个字符串
            
        Returns:
            相似度得分，范围0-1，1表示完全相同
        """
        # 转换为集合
        set1 = set(str1.split())
        set2 = set(str2.split())
        
        # 计算交集大小
        intersection = len(set1.intersection(set2))
        # 计算并集大小
        union = len(set1.union(set2))
        
        # 如果并集为空，返回0
        if union == 0:
            return 0
            
        # 返回Jaccard相似度
        return intersection / union

    def _batch_query_keywords(self, keywords_list):
        """批量查询关键词信息，每次最多查询5个关键词
        :param keywords_list: 关键词列表
        :return: 关键词查询结果字典
        """
        if not self.api_url or len(self.api_url) == 0:
            logger.warning("未设置关键词API URL，将不会查询关键词信息")
            return {}

        # 对关键词列表进行去重，避免重复查询
        unique_keywords = list(set(keywords_list))
        logger.debug(f"关键词去重: 原始数量 {len(keywords_list)}, 去重后数量 {len(unique_keywords)}")
        
        keyword_data = {}
        batch_size = 5  # 每批次最多5个关键词
        
        # 使用去重后的关键词列表进行查询
        for i in range(0, len(unique_keywords), batch_size):
            batch = unique_keywords[i:i + batch_size]
            combined_keywords = ",".join(batch)
            
            try:
                api_url = f"{self.api_url}{combined_keywords}"
                logger.debug(f"构造的API请求URL: {api_url}")
                
                response = requests.get(api_url, timeout=70)

                if response.status_code == 200:
                    try:
                        batch_data = response.json()
                        
                        # 验证API返回格式
                        if batch_data.get('status') == 'success' and 'data' in batch_data:
                            # 将返回的数据添加到结果中
                            for item in batch_data.get('data', []):
                                keyword = item.get('keyword', '')
                                if keyword:
                                    # 标准化月份名称为大写，确保匹配一致性
                                    if 'metrics' in item and 'monthly_searches' in item['metrics']:
                                        for month_data in item['metrics']['monthly_searches']:
                                            if 'month' in month_data:
                                                month_data['month'] = month_data['month'].upper()
                                    
                                    # 记录关键词数据
                                    if keyword in keyword_data:
                                        # 如果关键词已存在，更新数据
                                        keyword_data[keyword].update(item)
                                    else:
                                        keyword_data[keyword] = item
                        else:
                            logger.warning(f"API返回状态不是success或缺少data字段: {batch_data.get('status')}")
                    except json.JSONDecodeError as json_err:
                        logger.error(f"JSON解析错误: {json_err}, 响应内容: {response.text}")
                    except Exception as e:
                        logger.error(f"处理API响应时出错: {e}")
                else:
                    logger.warning(f"API请求失败，状态码: {response.status_code}")
            except requests.RequestException as req_err:
                logger.error(f"请求异常: {req_err}")
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON解析错误: {json_err}, 响应内容: {response.text}")

            # 在每次请求之间随机等待3到7秒
            if i + batch_size < len(unique_keywords):
                wait_time = random.uniform(3, 7)
                logger.debug(f"等待 {wait_time:.2f} 秒后继续查询")
                time.sleep(wait_time)
        
        return keyword_data
    
    def send_telegram_notification(self, updates_by_site: Dict[str, List[str]]) -> bool:
        """发送Telegram通知"""
        # 检查是否有任何更新
        if not any(updates_by_site.values()):
            logger.info("没有更新，不发送通知")
            return True
            
        # 过滤空列表，确保只处理有实际更新的站点
        updates_by_site = {site_id: urls for site_id, urls in updates_by_site.items() if urls}
        
        # 再次检查过滤后是否还有更新
        if not updates_by_site:
            logger.info("过滤后没有更新，不发送通知")
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
        current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            keyword_results = self._batch_query_keywords(list(url_keywords_map.values()))
            
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
        
        # 生成完整消息
        full_message = "\n".join(message_parts).strip()
        
        # Telegram消息长度限制
        max_message_length = 4000
        
        # 检查消息长度，如果超过限制则分割发送
        if len(full_message) > max_message_length:
            return self._send_long_message(full_message, max_message_length)
        else:
            # 消息长度在限制内，直接发送
            return self._send_telegram_message(full_message)
    
    def _send_telegram_message(self, message: str) -> bool:
        """发送单条Telegram消息
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            发送是否成功
        """
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
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"发送Telegram消息时出错: {e}")
            return False
    
    def _send_long_message(self, message: str, max_length: int) -> bool:
        """将长消息分割为多条发送
        
        Args:
            message: 完整消息内容
            max_length: 单条消息最大长度
            
        Returns:
            是否全部发送成功
        """
        logger.info(f"消息长度 ({len(message)}) 超过Telegram限制，将分多条发送")
        
        # 分割消息的标记
        parts_count = (len(message) + max_length - 1) // max_length  # 向上取整
        
        # 前言部分（包含在第一条消息中）
        header_lines = []
        message_lines = message.split('\n')
        
        # 提取前3行作为所有消息的头部（通常包含通知标题、日期和总更新数）
        if len(message_lines) > 3:
            header_lines = message_lines[:3]
            message_lines = message_lines[3:]
        
        # 分割剩余行
        chunks = []
        current_chunk = header_lines.copy()
        current_length = len('\n'.join(current_chunk))
        
        for line in message_lines:
            # 估算加上当前行后的长度
            line_length = len(line) + 1  # +1 是换行符
            
            # 如果加上当前行会超出限制，则开始新的块
            if current_length + line_length > max_length and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = header_lines.copy()  # 每个块都以头部开始
                current_chunk.append(f"\n(第 {len(chunks)+1}/{parts_count} 部分)")
                current_length = len('\n'.join(current_chunk))
            
            current_chunk.append(line)
            current_length += line_length
        
        # 添加最后一个块
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        # 发送所有分割后的消息
        all_success = True
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"发送第 {i}/{len(chunks)} 部分消息，长度: {len(chunk)}")
            
            # 添加分页信息
            if i == 1:
                chunk = f"{chunk}\n\n(消息太长，分 {len(chunks)} 部分发送，这是第 {i} 部分)"
            else:
                chunk = f"{chunk}\n\n(第 {i}/{len(chunks)} 部分)"
            
            if not self._send_telegram_message(chunk):
                all_success = False
                logger.error(f"第 {i}/{len(chunks)} 部分消息发送失败")
            
            # 消息之间添加短暂延迟，避免API限制
            if i < len(chunks):
                time.sleep(1)
        
        if all_success:
            logger.info(f"已成功发送所有 {len(chunks)} 部分Telegram通知")
        else:
            logger.warning("部分Telegram通知发送失败")
            
        return all_success
    
    def _format_detailed_updates(self, message_parts: List[str], urls: List[str],
                               url_keywords_map: Dict[str, str],
                               keyword_results: Dict[str, Dict[str, Any]]) -> None:
        """
        格式化详细的更新信息，展示原始关键词数据和最高流量相关词
        
        Args:
            message_parts: 消息部分列表，将被修改
            urls: 要格式化的URL列表
            url_keywords_map: URL到提取关键词的映射
            keyword_results: URL到API响应结果的映射
        """
        if not urls:
            return
            
        # 将 URL 分为两组：有关键词数据的和没有关键词数据的
        urls_with_data = []
        urls_without_data = []
        
        # 跟踪全局最高流量的相关词
        global_highest_volume_keyword = None
        global_highest_volume = 0
        
        # 跟踪符合增长趋势的关键词
        trending_keywords = []
        
        for url in urls:
            if url in keyword_results and keyword_results[url].get('data', []):
                urls_with_data.append(url)
            else:
                urls_without_data.append(url)
        
        # 1. 处理有关键词数据的URL
        processed_urls = []
        if urls_with_data:
            message_parts.append("\n🔍 <b>有详细搜索数据的URL：</b>")
            
            for url in urls_with_data:
                original_keyword = url_keywords_map.get(url, "")
                
                # 跳过没有原始关键词的URL
                if not original_keyword:
                    continue
                
                # 查找API返回的数据
                api_data = keyword_results[url]
                keyword_data_list = api_data.get('data', [])
                
                if not keyword_data_list:
                    continue
                
                # 1.1 查找原始关键词的数据 - 使用精确匹配
                original_keyword_data = None
                highest_volume_keyword_data = None
                highest_volume = 0
                
                # 检查所有关键词数据
                for kw_data in keyword_data_list:
                    keyword = kw_data.get('keyword', '')
                    search_volume = kw_data.get('metrics', {}).get('avg_monthly_searches', 0)
                    
                    # 精确匹配原始关键词 - 不区分大小写
                    if keyword.lower() == original_keyword.lower():
                        original_keyword_data = kw_data
                    
                    # 跟踪当前URL中最高流量的关键词
                    if search_volume > highest_volume:
                        highest_volume = search_volume
                        highest_volume_keyword_data = kw_data
                    
                    # 同时跟踪全局最高流量的关键词
                    if search_volume > global_highest_volume:
                        global_highest_volume = search_volume
                        global_highest_volume_keyword = kw_data
                    
                    # 检查月度趋势数据，寻找符合特定增长模式的关键词
                    monthly_searches = kw_data.get('metrics', {}).get('monthly_searches', [])
                    if monthly_searches:
                        # 按时间顺序排序月度数据
                        sorted_monthly_data = sorted(
                            monthly_searches,
                            key=lambda x: (x.get('year', ''), x.get('month', ''))
                        )
                        
                        # 创建月份到搜索量的映射
                        month_to_searches = {}
                        for month_info in sorted_monthly_data:
                            year = month_info.get('year', '')
                            month = month_info.get('month', '')
                            searches = month_info.get('searches', 0)
                            month_key = f"{year}/{month}"
                            month_to_searches[month_key] = searches
                        
                        # 检查特定月份的趋势模式: 10月和11月为0，然后持续增长
                        oct_searches = month_to_searches.get('2024/OCTOBER', 0)
                        nov_searches = month_to_searches.get('2024/NOVEMBER', 0)
                        dec_searches = month_to_searches.get('2024/DECEMBER', 0)
                        jan_searches = month_to_searches.get('2025/JANUARY', 0)
                        feb_searches = month_to_searches.get('2025/FEBRUARY', 0)
                        
                        # 判断是否符合增长趋势条件
                        is_trending = (
                            oct_searches == 0 and 
                            nov_searches == 0 and 
                            dec_searches > 0 and 
                            jan_searches > dec_searches and 
                            feb_searches > jan_searches
                        )
                        
                        if is_trending:
                            # 记录趋势关键词
                            trending_keywords.append({
                                'keyword': keyword,
                                'search_volume': search_volume,
                                'monthly_data': sorted_monthly_data
                            })
                
                # 记录已处理的URL，避免重复
                processed_urls.append(url)
                
                # 1.2 显示原始关键词的数据
                if original_keyword_data:
                    # 使用原始关键词自己的数据
                    metrics = original_keyword_data.get('metrics', {})
                    avg_searches = metrics.get('avg_monthly_searches', 0)
                    
                    # 添加关键词信息
                    message_parts.append(f"\n{len(processed_urls)}. <b>{original_keyword}</b> [{avg_searches}]")
                    
                    # 显示月度搜索趋势
                    monthly_searches = metrics.get('monthly_searches', [])
                    if monthly_searches:
                        # 按时间顺序排序月度数据
                        sorted_monthly_data = sorted(
                            monthly_searches,
                            key=lambda x: (x.get('year', ''), x.get('month', ''))
                        )
                        
                        # 构建月度趋势数据
                        trend_parts = []
                        for month_info in sorted_monthly_data:
                            year = month_info.get('year', '')
                            month = month_info.get('month', '')
                            searches = month_info.get('searches', 0)
                            
                            # 将月份名称转换为短格式
                            month_short = month[:3].title() if month else ""
                            trend_parts.append(f"{year}/{month_short}: {searches}")
                        
                        # 添加月度趋势信息
                        if trend_parts:
                            message_parts.append(f"   📈 月度趋势: {', '.join(trend_parts)}")
                else:
                    # 原始关键词在API结果中不存在，显示无数据提示
                    message_parts.append(f"\n{len(processed_urls)}. <b>{original_keyword}</b> [无数据]")
            
            # 1.3 单独显示全局最高流量的关键词（如果有）
            # 确保它至少高于某个阈值（例如1000），避免显示无关紧要的低流量词
            if global_highest_volume_keyword and global_highest_volume > 1000:
                keyword = global_highest_volume_keyword.get('keyword', '')
                metrics = global_highest_volume_keyword.get('metrics', {})
                avg_searches = metrics.get('avg_monthly_searches', 0)
                
                # 添加全局最高流量关键词信息
                message_parts.append(f"\n🔝 <b>本批次最高流量相关词: {keyword}</b> [{avg_searches}]")
                
                # 显示月度搜索趋势
                monthly_searches = metrics.get('monthly_searches', [])
                if monthly_searches:
                    # 按时间顺序排序月度数据
                    sorted_monthly_data = sorted(
                        monthly_searches,
                        key=lambda x: (x.get('year', ''), x.get('month', ''))
                    )
                    
                    # 构建月度趋势数据
                    trend_parts = []
                    for month_info in sorted_monthly_data:
                        year = month_info.get('year', '')
                        month = month_info.get('month', '')
                        searches = month_info.get('searches', 0)
                        
                        # 将月份名称转换为短格式
                        month_short = month[:3].title() if month else ""
                        trend_parts.append(f"{year}/{month_short}: {searches}")
                    
                    # 添加月度趋势信息
                    if trend_parts:
                        message_parts.append(f"   📈 月度趋势: {', '.join(trend_parts)}")
        
        # 2. 处理没有关键词数据的URL
        if urls_without_data:
            message_parts.append("\n🔍 <b>无搜索数据的URL：</b>")
            
            # 分组显示这些URL（每3个为一组）
            for i in range(0, len(urls_without_data), 3):
                group = urls_without_data[i:i+3]
                encoded_urls = []
                
                for url in group:
                    keyword = url_keywords_map.get(url, "未知关键词")
                    encoded_urls.append(f"<b>{keyword}</b>")
                
                message_parts.append(f"\n{', '.join(encoded_urls)}")
        
        # 3. 显示符合增长趋势的关键词
        if trending_keywords:
            # 对趋势关键词按搜索量排序
            trending_keywords.sort(key=lambda x: x['search_volume'], reverse=True)
            
            message_parts.append("\n🚀 <b>检测到增长趋势的关键词：</b>")
            for i, trend_data in enumerate(trending_keywords):
                keyword = trend_data['keyword']
                search_volume = trend_data['search_volume']
                
                # 添加关键词信息
                message_parts.append(f"\n{i+1}. <b>{keyword}</b> [{search_volume}]")
                
                # 显示月度搜索趋势
                monthly_data = trend_data['monthly_data']
                if monthly_data:
                    # 构建月度趋势数据
                    trend_parts = []
                    for month_info in monthly_data:
                        year = month_info.get('year', '')
                        month = month_info.get('month', '')
                        searches = month_info.get('searches', 0)
                        
                        # 将月份名称转换为短格式
                        month_short = month[:3].title() if month else ""
                        trend_parts.append(f"{year}/{month_short}: {searches}")
                    
                    # 添加月度趋势信息
                    if trend_parts:
                        message_parts.append(f"   📈 月度趋势: {', '.join(trend_parts)}")

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
        urls_with_data = []
        urls_without_data = []
        
        for url in urls:
            # 提取URL名称
            url_name = url.split('/')[-1].replace('-', ' ')
            url_link = f"<a href='{url}'>{url_name}</a>"
            
            # 提取关键词信息
            keywords = url_keywords_map.get(url, "")
            keyword_data_list = []
            
            if url in keyword_results:
                # 提取所有关键词信息
                try:
                    data = keyword_results[url].get('data', [])
                    if data:
                        for keyword_entry in data:
                            keyword_text = keyword_entry.get('keyword', '')
                            metrics = keyword_entry.get('metrics', {})
                            search_volume = metrics.get('avg_monthly_searches', 0)
                            competition = metrics.get('competition', 'N/A')
                            
                            # 根据竞争度选择不同的图标
                            icon = "🟢" if competition == "LOW" else "🟡" if competition == "MEDIUM" else "🔴" if competition == "HIGH" else "⚪"
                            
                            # 获取月度搜索数据
                            monthly_searches = metrics.get('monthly_searches', [])
                            monthly_data = []
                            if monthly_searches:
                                # 排序月度搜索数据
                                monthly_searches.sort(key=lambda x: (x.get("year", ""), x.get("month", "")))
                                # 获取最近6个月的数据
                                monthly_data = monthly_searches[-6:] if len(monthly_searches) > 6 else monthly_searches
                            
                            keyword_data_list.append((keyword_text, search_volume, monthly_data, icon))
                except Exception as e:
                    logger.error(f"处理紧凑模式关键词数据时出错: {e}")
            
            # 区分有数据和无数据的URL
            if keyword_data_list:
                urls_with_data.append((url_link, keyword_data_list))
            else:
                urls_without_data.append((url_link, keywords))
        
        # 添加有数据的URL
        if urls_with_data:
            message_parts.append("<b>🔍 有搜索数据的URL:</b>")
            for i, (url_link, keyword_list) in enumerate(urls_with_data, 1):
                # 按搜索量排序关键词
                keyword_list.sort(key=lambda x: x[1], reverse=True)
                
                # 添加URL标题行
                message_parts.append(f"{i}. {url_link}")
                
                # 添加每个关键词的信息
                for keyword_text, volume, monthly_data, icon in keyword_list:
                    message_parts.append(f"   {icon} <b>{keyword_text}</b> [搜索量: {volume}]")
                    
                    # 添加月度数据
                    if monthly_data:
                        months_text = []
                        for month_data in monthly_data:
                            year = month_data.get("year", "")
                            month = month_data.get("month", "")
                            searches = month_data.get("searches", 0)
                            month_abbr = month[:3].title() if month else ""
                            months_text.append(f"{year}/{month_abbr}: {searches}")
                        message_parts.append(f"     📈 月度趋势: {', '.join(months_text)}")
        
        # 添加无数据的URL，分批显示
        if urls_without_data:
            message_parts.append("<b>⚪ 无搜索数据:</b>")
            # 将无数据关键词按10个一组分批显示，避免消息过长
            no_data_chunks = [urls_without_data[i:i+10] for i in range(0, len(urls_without_data), 10)]
            for chunk in no_data_chunks:
                chunk_links = []
                for url_link, keywords in chunk:
                    if keywords:
                        chunk_links.append(f"{url_link} ({keywords})")
                    else:
                        chunk_links.append(url_link)
                message_parts.append(", ".join(chunk_links))

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
        # 按搜索量对URL和关键词进行分组
        high_volume = []  # >1000
        medium_volume = []  # 100-1000
        low_volume = []  # <100
        no_data = []  # 没有数据
        
        for url in urls:
            # 提取URL名称
            url_name = url.split('/')[-1].replace('-', ' ')
            url_link = f"<a href='{url}'>{url_name}</a>"
            
            # 提取关键词
            keywords = url_keywords_map.get(url, "")
            
            if url in keyword_results:
                try:
                    data = keyword_results[url].get('data', [])
                    if data:
                        # 处理所有关键词数据
                        for keyword_data in data:
                            keyword_text = keyword_data.get('keyword', '')
                            metrics = keyword_data.get('metrics', {})
                            search_volume = metrics.get('avg_monthly_searches', 0)
                            
                            # 获取月度搜索数据
                            monthly_searches = metrics.get('monthly_searches', [])
                            monthly_data = []
                            if monthly_searches:
                                # 排序月度搜索数据
                                monthly_searches.sort(key=lambda x: (x.get("year", ""), x.get("month", "")))
                                # 获取最近6个月的数据
                                monthly_data = monthly_searches[-6:] if len(monthly_searches) > 6 else monthly_searches
                            
                            # 根据搜索量分组
                            if search_volume > 1000:
                                high_volume.append((url_link, search_volume, keyword_text, monthly_data))
                            elif search_volume >= 100:
                                medium_volume.append((url_link, search_volume, keyword_text, monthly_data))
                            else:
                                low_volume.append((url_link, search_volume, keyword_text, monthly_data))
                except Exception as e:
                    logger.error(f"处理关键词数据时出错: {e}")
                    no_data.append((url_link, keywords))
            else:
                no_data.append((url_link, keywords))
        
        # 排序各组内的URL和关键词
        high_volume.sort(key=lambda x: x[1], reverse=True)
        medium_volume.sort(key=lambda x: x[1], reverse=True)
        low_volume.sort(key=lambda x: x[1], reverse=True)
        
        # 添加高搜索量组
        if high_volume:
            message_parts.append("<b>🔴 高搜索量 (>1000):</b>")
            for i, (url_link, volume, keyword, monthly_data) in enumerate(high_volume, 1):
                message_parts.append(f"{i}. {url_link} [{volume}] - {keyword}")
                # 添加月度数据
                if monthly_data:
                    months_text = []
                    for month_data in monthly_data:
                        year = month_data.get("year", "")
                        month = month_data.get("month", "")
                        searches = month_data.get("searches", 0)
                        month_abbr = month[:3].title() if month else ""
                        months_text.append(f"{year}/{month_abbr}: {searches}")
                    message_parts.append(f"   📈 月度趋势: {', '.join(months_text)}")
        
        # 添加中搜索量组
        if medium_volume:
            message_parts.append("<b>🟡 中搜索量 (100-1000):</b>")
            for i, (url_link, volume, keyword, monthly_data) in enumerate(medium_volume, 1):
                message_parts.append(f"{i}. {url_link} [{volume}] - {keyword}")
                # 添加月度数据
                if monthly_data:
                    months_text = []
                    for month_data in monthly_data:
                        year = month_data.get("year", "")
                        month = month_data.get("month", "")
                        searches = month_data.get("searches", 0)
                        month_abbr = month[:3].title() if month else ""
                        months_text.append(f"{year}/{month_abbr}: {searches}")
                    message_parts.append(f"   📈 月度趋势: {', '.join(months_text)}")
        
        # 添加低搜索量组
        if low_volume:
            message_parts.append("<b>🟢 低搜索量 (<100):</b>")
            for i, (url_link, volume, keyword, monthly_data) in enumerate(low_volume, 1):
                message_parts.append(f"{i}. {url_link} [{volume}] - {keyword}")
                # 添加月度数据
                if monthly_data:
                    months_text = []
                    for month_data in monthly_data:
                        year = month_data.get("year", "")
                        month = month_data.get("month", "")
                        searches = month_data.get("searches", 0)
                        month_abbr = month[:3].title() if month else ""
                        months_text.append(f"{year}/{month_abbr}: {searches}")
                    message_parts.append(f"   📈 月度趋势: {', '.join(months_text)}")
        
        # 添加无数据组，全部列出而不省略
        if no_data:
            message_parts.append("<b>⚪ 无搜索数据:</b>")
            # 将无数据关键词按10个一组分批显示，避免消息过长
            no_data_chunks = [no_data[i:i+10] for i in range(0, len(no_data), 10)]
            for chunk in no_data_chunks:
                chunk_links = []
                for url_link, keywords in chunk:
                    if keywords:
                        chunk_links.append(f"{url_link} ({keywords})")
                    else:
                        chunk_links.append(url_link)
                message_parts.append(", ".join(chunk_links))

    def run(self) -> None:
        """执行监控流程"""
        logger.info("开始执行内容监控...")
        
        all_updates = {}
        for i, website_url in enumerate(self.website_urls):
            try:
                # 处理每个网站
                updated_urls = self.process_site(website_url, i)
                
                if updated_urls:
                    site_id = self._get_site_identifier(website_url)
                    all_updates[site_id] = updated_urls
            except Exception as e:
                logger.error(f"处理网站时出错: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        if not all_updates:
            logger.info("没有检测到内容更新")
            return
            
        logger.info(f"监控完成，共有 {len(all_updates)} 个网站有更新")
        total_updates = sum(len(urls) for urls in all_updates.values())
        logger.info(f"总共 {total_updates} 个URL已更新")

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