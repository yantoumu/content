#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网站地图解析模块
处理网站地图的下载和解析
"""

import logging
import datetime
from typing import Dict, Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

# 配置日志
logger = logging.getLogger('content_watcher.sitemap_parser')

class SitemapParser:
    """处理网站地图的下载和解析"""

    def __init__(self):
        """初始化解析器"""
        # 创建会话对象用于复用连接
        self.session = requests.Session()

    def download_and_parse_sitemap(self, url: str, site_id: str) -> Dict[str, Optional[str]]:
        """下载并解析网站地图，返回URL和最后修改日期的映射"""
        sitemap_data = {}

        try:
            logger.info(f"正在下载网站地图: {site_id}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # 解析XML，使用更高效的方式
            content = response.content

            # 预处理XML内容，检查是否需要处理编码问题
            if content.startswith(b'<?xml'):
                # XML内容正常，直接解析
                root = ET.fromstring(content)
            else:
                # 尝试使用不同的编码解析
                try:
                    content_str = content.decode('utf-8')
                    root = ET.fromstring(content_str)
                except (UnicodeDecodeError, ET.ParseError):
                    try:
                        content_str = content.decode('latin-1')
                        root = ET.fromstring(content_str)
                    except (UnicodeDecodeError, ET.ParseError):
                        # 如果仍然无法解析，抛出异常
                        raise ET.ParseError("Unable to parse XML content")

            # XML命名空间
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
            }

            # 查找所有URL条目
            # 使用标准的ElementTree API
            for url_elem in root.findall('.//sm:url', namespaces):
                loc_elem = url_elem.find('./sm:loc', namespaces)
                lastmod_elem = url_elem.find('./sm:lastmod', namespaces)

                if loc_elem is not None and loc_elem.text:
                    url_text = loc_elem.text.strip()

                    # 检查URL是否应该被排除
                    if SitemapParser._should_exclude_url(url_text):
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
            logger.error(f"出错的URL: {url}")
            return {}
        except Exception as e:
            logger.error(f"处理网站地图时出现未知错误: {e}")
            return {}

    @staticmethod
    def _should_exclude_url(url: str) -> bool:
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

    @staticmethod
    def is_updated_today(lastmod: Optional[str]) -> bool:
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

    def close(self):
        """关闭会话连接

        在不再需要使用解析器时调用此方法
        """
        if hasattr(self, 'session') and self.session:
            logger.debug("关闭网站地图解析器会话")
            self.session.close()

    def __del__(self):
        """析构函数，确保在对象被垃圾回收时关闭会话"""
        self.close()

# 创建全局解析器实例
sitemap_parser = SitemapParser()
