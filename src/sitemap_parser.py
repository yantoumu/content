#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网站地图解析模块
处理网站地图的下载和解析
"""

import gzip
import bz2
import logging
import datetime
from abc import ABC, abstractmethod
from typing import Dict, Optional, Union
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

# 配置日志
logger = logging.getLogger('content_watcher.sitemap_parser')


class CompressionHandler(ABC):
    """压缩处理器抽象基类"""

    @abstractmethod
    def can_handle(self, content_type: str, url: str) -> bool:
        """检查是否能处理指定的压缩格式

        Args:
            content_type: HTTP响应的Content-Type头
            url: 请求的URL

        Returns:
            如果能处理返回True，否则返回False
        """
        pass

    @abstractmethod
    def decompress(self, data: bytes) -> bytes:
        """解压数据

        Args:
            data: 压缩的二进制数据

        Returns:
            解压后的二进制数据

        Raises:
            Exception: 解压失败时抛出异常
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取压缩格式名称"""
        pass


class GzipCompressionHandler(CompressionHandler):
    """Gzip压缩处理器"""

    def can_handle(self, content_type: str, url: str) -> bool:
        """检查是否为gzip压缩格式"""
        # 检查Content-Type头
        if content_type and ('gzip' in content_type.lower() or 'application/x-gzip' in content_type.lower()):
            return True

        # 检查URL扩展名
        if url and url.lower().endswith('.gz'):
            return True

        return False

    def decompress(self, data: bytes) -> bytes:
        """使用gzip解压数据"""
        try:
            return gzip.decompress(data)
        except gzip.BadGzipFile as e:
            raise Exception(f"Gzip解压失败: {e}")
        except Exception as e:
            raise Exception(f"Gzip解压时出现未知错误: {e}")

    def get_name(self) -> str:
        """获取压缩格式名称"""
        return "gzip"


class BZip2CompressionHandler(CompressionHandler):
    """BZip2压缩处理器"""

    def can_handle(self, content_type: str, url: str) -> bool:
        """检查是否为bzip2压缩格式"""
        # 检查Content-Type头
        if content_type and ('bzip2' in content_type.lower() or 'application/x-bzip2' in content_type.lower()):
            return True

        # 检查URL扩展名
        if url and (url.lower().endswith('.bz2') or url.lower().endswith('.bzip2')):
            return True

        return False

    def decompress(self, data: bytes) -> bytes:
        """使用bzip2解压数据"""
        try:
            return bz2.decompress(data)
        except OSError as e:
            raise Exception(f"BZip2解压失败: {e}")
        except Exception as e:
            raise Exception(f"BZip2解压时出现未知错误: {e}")

    def get_name(self) -> str:
        """获取压缩格式名称"""
        return "bzip2"


class NoCompressionHandler(CompressionHandler):
    """无压缩处理器（用于处理未压缩的内容）"""

    def can_handle(self, content_type: str, url: str) -> bool:
        """总是返回True，作为默认处理器"""
        return True

    def decompress(self, data: bytes) -> bytes:
        """直接返回原始数据"""
        return data

    def get_name(self) -> str:
        """获取压缩格式名称"""
        return "none"


class CompressionDetector:
    """压缩格式检测器"""

    def __init__(self):
        """初始化检测器，注册所有支持的压缩处理器"""
        self.handlers = [
            GzipCompressionHandler(),
            # 未来可以在这里添加其他压缩格式处理器
            # BZip2CompressionHandler(),
            # DeflateCompressionHandler(),
            NoCompressionHandler(),  # 无压缩处理器应该放在最后作为默认选项
        ]

    def detect_and_get_handler(self, content_type: str, url: str) -> CompressionHandler:
        """检测压缩格式并返回对应的处理器

        Args:
            content_type: HTTP响应的Content-Type头
            url: 请求的URL

        Returns:
            对应的压缩处理器
        """
        for handler in self.handlers:
            if handler.can_handle(content_type, url):
                logger.debug(f"检测到压缩格式: {handler.get_name()}")
                return handler

        # 理论上不会到达这里，因为NoCompressionHandler总是返回True
        logger.warning("未找到合适的压缩处理器，使用无压缩处理器")
        return NoCompressionHandler()

class SitemapParser:
    """处理网站地图的下载和解析"""

    def __init__(self):
        """初始化解析器"""
        # 创建会话对象用于复用连接
        self.session = requests.Session()
        
        # 设置标准浏览器请求头，避免403错误
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # 创建压缩检测器
        self.compression_detector = CompressionDetector()

    def download_and_parse_sitemap(self, url: str, site_id: str) -> Dict[str, Optional[str]]:
        """下载并解析网站地图，返回URL和最后修改日期的映射"""
        sitemap_data = {}

        try:
            logger.info("正在下载网站地图")
            
            # 动态添加Referer头部，使用网站首页作为来源（关键修复）
            parsed_url = urlparse(url)
            referer_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
            headers = {'Referer': referer_url}
            
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # 获取响应内容和头信息
            raw_content = response.content
            content_type = response.headers.get('Content-Type', '').lower()

            # 检测并处理压缩格式
            compression_handler = self.compression_detector.detect_and_get_handler(content_type, url)

            try:
                # 解压内容（如果需要）
                content = compression_handler.decompress(raw_content)
                if compression_handler.get_name() != "none":
                    logger.info(f"成功解压{compression_handler.get_name()}格式的网站地图")
            except Exception as e:
                logger.error(f"解压网站地图时出错: {e}")
                # 不输出完整URL，避免敏感信息泄露
                domain_part = urlparse(url).netloc if url else '***'
                logger.error(f"出错的域名: {domain_part}")
                return {}

            # 解析XML内容
            root = self._parse_xml_content(content)
            if root is None:
                return {}

            # 提取URL数据
            sitemap_data = self._extract_urls_from_xml(root)

            logger.info(f"已解析网站地图，找到 {len(sitemap_data)} 个URL")
            return sitemap_data

        except requests.RequestException as e:
            logger.error(f"下载网站地图时出错: {e}")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"出错的域名: {domain_part}")
            return {}
        except ET.ParseError as e:
            logger.error(f"解析XML时出错: {e}")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"出错的域名: {domain_part}")
            return {}
        except Exception as e:
            logger.error(f"处理网站地图时出现未知错误: {e}")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"出错的域名: {domain_part}")
            return {}

    def _parse_xml_content(self, content: bytes) -> Optional[ET.Element]:
        """解析XML内容，处理不同的编码格式

        Args:
            content: XML内容的二进制数据

        Returns:
            解析后的XML根元素，失败时返回None
        """
        try:
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

            return root

        except ET.ParseError as e:
            logger.error(f"解析XML时出错: {e}")
            return None
        except Exception as e:
            logger.error(f"处理XML内容时出现未知错误: {e}")
            return None

    def _extract_urls_from_xml(self, root: ET.Element) -> Dict[str, Optional[str]]:
        """从XML根元素中提取URL数据

        Args:
            root: XML根元素

        Returns:
            URL到lastmod的映射字典
        """
        sitemap_data = {}

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

        return sitemap_data

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
