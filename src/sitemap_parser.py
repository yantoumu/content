#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网站地图解析模块
处理网站地图的下载和解析
"""

import logging
import datetime
import gzip
import io
import time
import re
import zlib  # 修复：在模块级别导入zlib，避免作用域问题
from typing import Dict, Optional, List
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

        # 设置简洁的浏览器请求头，让requests自动处理压缩
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        # 性能优化配置
        from src.config import config
        self.performance_mode = hasattr(config, 'enable_performance_mode') and config.enable_performance_mode
        if self.performance_mode:
            # 性能模式下减少超时时间和重试次数
            self.default_timeout = 15
            self.max_retries = 2
            logger.info("Sitemap解析器启用性能优化模式")
        else:
            self.default_timeout = 70
            self.max_retries = 3

    def download_and_parse_sitemap(self, url: str, site_id: str) -> Dict[str, Optional[str]]:
        """下载并解析网站地图，返回URL和最后修改日期的映射"""
        try:
            # 不输出完整URL，只输出域名部分
            domain_part = urlparse(url).netloc if url else '***'
            logger.info(f"正在下载网站地图: {domain_part}")
            return self._dispatch_by_format(url)
        except Exception as e:
            logger.error(f"处理网站地图时出现错误: {e}")
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"出错的域名: {domain_part}")
            return {}

    def _dispatch_by_format(self, url: str) -> Dict[str, Optional[str]]:
        """根据URL格式分发到相应的解析器，优先使用正则表达式提取"""
        # RSS feed检测
        if '/rss/' in url.lower() or url.lower().endswith('.rss') or 'feed' in url.lower():
            logger.info("检测到RSS feed，尝试RSS解析")
            return self._parse_rss_feed(url)

        # TXT格式检测
        if url.lower().endswith('.txt'):
            logger.info("检测到TXT格式，尝试纯文本解析")
            return self._parse_txt_sitemap(url)

        # 特殊网站检测
        if 'hahagames.com' in url.lower():
            logger.info("检测到hahagames.com，使用特殊处理")
            return self._parse_hahagames_sitemap(url)

        # 标准XML sitemap处理 - 优先尝试正则表达式提取
        return self._parse_standard_sitemap_with_regex_priority(url)

    def _parse_standard_sitemap_with_regex_priority(self, url: str) -> Dict[str, Optional[str]]:
        """优先使用正则表达式提取，失败时回退到XML解析"""
        try:
            headers = self._get_standard_headers()
            response = self._download_with_retry(url, headers)

            # 第一步：尝试正则表达式快速提取
            regex_result = self._try_regex_extraction(response, url)
            if self._is_extraction_successful(regex_result):
                logger.info(f"正则表达式提取成功: {len(regex_result)} 个URL")
                return regex_result

            # 第二步：回退到现有的XML解析方法
            logger.info("正则表达式提取失败，回退到XML解析")
            return self._parse_response_content(response, url)

        except (requests.exceptions.RequestException, ET.ParseError, ValueError) as e:
            logger.error(f"网络或解析错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"所有提取方法都失败，未预期错误: {e}")
            return {}

    def _parse_standard_sitemap(self, url: str) -> Dict[str, Optional[str]]:
        """解析标准XML sitemap"""
        headers = self._get_standard_headers()
        response = self._download_with_retry(url, headers)
        return self._parse_response_content(response, url)

    def _get_standard_headers(self) -> Dict[str, str]:
        """获取标准请求头"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }

    def _parse_response_content(self, response: requests.Response, url: str) -> Dict[str, Optional[str]]:
        """智能解析响应内容，预检测格式避免无效尝试"""
        try:
            # 检查内容类型
            content_type = response.headers.get('content-type', '').lower()
            logger.debug(f"Content-Type: {content_type}")

            # 检查是否是HTML格式
            if 'text/html' in content_type:
                domain_part = urlparse(url).netloc if url else '***'
                logger.info(f"检测到HTML格式sitemap，尝试HTML解析: {domain_part}")
                return self._parse_html_sitemap(response, url)

            # 预检测是否为压缩内容（优先检测，避免无效XML解析）
            if self._is_compressed_content(response):
                logger.info("预检测到压缩内容，直接解压处理")
                return self._handle_compressed_sitemap(response, url)

            # 尝试解析XML（仅在非压缩内容时）
            try:
                root = ET.fromstring(response.content)
                return self._extract_sitemap_data(root, url)
            except ET.ParseError as parse_error:
                # 如果XML解析失败，再次检查是否为压缩内容（兜底策略）
                logger.warning("XML解析失败，进行压缩内容兜底检测")
                logger.error(f"XML解析失败，内容长度: {len(response.content)} bytes")

                # 最后尝试压缩解析
                if response.content.startswith(b'\x1f\x8b'):  # gzip魔数
                    logger.info("发现gzip魔数，尝试压缩解析")
                    return self._handle_compressed_sitemap(response, url)

                raise parse_error

        except (requests.exceptions.RequestException, ET.ParseError) as e:
            logger.error(f"网络或XML解析失败: {e}")
            return {}
        except Exception as e:
            logger.error(f"解析响应内容时发生未预期错误: {e}")
            return {}

    def _extract_sitemap_data(self, root: ET.Element, url: str) -> Dict[str, Optional[str]]:
        """从XML根元素提取sitemap数据"""
        # 提取URL数据
        sitemap_data = self._extract_urls_from_xml(root)

        if not sitemap_data:
            domain_part = urlparse(url).netloc if url else '***'
            logger.warning(f"sitemap解析成功但未找到任何URL: {domain_part}")
            # 检查是否是sitemap index文件
            sitemap_data = self._try_parse_sitemap_index(root, url)
            if not sitemap_data:
                # 打印XML结构用于调试
                logger.debug(f"XML根元素: {root.tag}, 子元素数量: {len(root)}")
                if len(root) > 0:
                    logger.debug(f"第一个子元素: {root[0].tag}")
                    # 打印前几个子元素的标签名
                    child_tags = [child.tag for child in root[:5]]
                    logger.debug(f"前几个子元素标签: {child_tags}")

        logger.info(f"已解析网站地图，找到 {len(sitemap_data)} 个URL")
        return sitemap_data

    def _is_compressed_content(self, response: requests.Response) -> bool:
        """智能检测是否为压缩内容（支持多种压缩格式）"""
        content = response.content

        # 优先检查Content-Encoding头（最可靠）
        content_encoding = response.headers.get('content-encoding', '').lower()
        if any(encoding in content_encoding for encoding in ['gzip', 'deflate', 'br', 'brotli']):
            return True

        # 检查二进制内容特征
        if len(content) >= 2:
            # gzip魔数检测
            if content[:2] == b'\x1f\x8b':
                return True
            # zip魔数检测
            if content[:2] == b'PK':
                return True

        # 检查URL扩展名
        if response.url.endswith(('.gz', '.zip', '.bz2')):
            return True

        # 检查Content-Type头中的压缩指示
        content_type = response.headers.get('content-type', '').lower()
        if 'gzip' in content_type or 'compressed' in content_type:
            return True

        return False

    def _handle_compressed_sitemap(self, response: requests.Response, url: str) -> Dict[str, Optional[str]]:
        """智能处理压缩的sitemap文件（支持多种压缩格式）"""
        content = response.content
        decompressed_content = None

        # 获取压缩类型
        content_encoding = response.headers.get('content-encoding', '').lower()

        try:
            # 策略1: 基于Content-Encoding头的解压
            if 'br' in content_encoding or 'brotli' in content_encoding:
                try:
                    import brotli
                    decompressed_content = brotli.decompress(content)
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.info(f"成功使用Brotli解压: {domain_part}")
                except ImportError:
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.warning(f"Brotli库未安装，无法解压 {domain_part}，建议安装: pip install brotli")
                    # 尝试其他解压方式作为降级
                    if content[:2] == b'\x1f\x8b':  # 检查是否为gzip
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz_file:
                                decompressed_content = gz_file.read()
                            logger.info(f"降级使用gzip解压成功: {domain_part}")
                        except:
                            decompressed_content = content
                    else:
                        decompressed_content = content
                except Exception as e:
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.warning(f"Brotli解压失败 {domain_part}: {e}")
                    decompressed_content = content

            elif 'gzip' in content_encoding or content[:2] == b'\x1f\x8b':
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz_file:
                    decompressed_content = gz_file.read()
                domain_part = urlparse(url).netloc if url else '***'
                logger.info(f"成功使用gzip解压: {domain_part}")

            elif 'deflate' in content_encoding:
                # zlib已在模块级别导入，直接使用
                decompressed_content = zlib.decompress(content)
                domain_part = urlparse(url).netloc if url else '***'
                logger.info(f"成功使用deflate解压: {domain_part}")

            # 策略2: 基于URL扩展名的解压
            elif url.endswith('.gz'):
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz_file:
                        decompressed_content = gz_file.read()
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.info(f"基于.gz扩展名成功解压: {domain_part}")
                except:
                    decompressed_content = content
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.warning(f"gzip解压失败，使用原始内容: {domain_part}")

            # 策略3: 直接使用原内容
            else:
                decompressed_content = content
                domain_part = urlparse(url).netloc if url else '***'
                logger.info(f"使用原始内容（未检测到压缩）: {domain_part}")

        except (gzip.BadGzipFile, zlib.error, ImportError) as e:
            logger.warning(f"解压失败，使用原始内容: {e}")
            decompressed_content = content
        except Exception as e:
            logger.error(f"解压过程中发生未预期错误: {e}")
            decompressed_content = content

        # 解析解压后的内容
        try:
            root = ET.fromstring(decompressed_content)
            return self._extract_sitemap_data(root, url)

        except ET.ParseError as e:
            logger.error(f"XML解析失败: {e}")
            # 提供调试信息但不输出敏感内容
            logger.error(f"内容编码: {content_encoding}")
            logger.error(f"原始内容长度: {len(content)} bytes")
            if decompressed_content:
                logger.error(f"解压内容长度: {len(decompressed_content)} bytes")
            else:
                logger.error("解压内容为空")
            return {}
        except Exception as e:
            logger.error(f"处理压缩sitemap时发生未预期错误: {e}")
            return {}

    def _download_with_retry(self, url: str, headers: dict, max_retries: int = None) -> requests.Response:
        """智能重试下载，针对不同错误类型使用不同策略"""
        if max_retries is None:
            max_retries = self.max_retries if hasattr(self, 'max_retries') else 3

        last_exception = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # 等待时间：1秒、3秒、5秒
                    wait_time = 1 + attempt * 2
                    logger.info(f"重试第{attempt}次，等待{wait_time}秒...")
                    time.sleep(wait_time)
                
                # 根据重试次数调整请求策略
                current_headers = headers.copy()
                if attempt > 0:
                    # 第二次尝试：更换User-Agent
                    user_agents = [
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101'
                    ]
                    current_headers['User-Agent'] = user_agents[attempt % len(user_agents)]
                
                if attempt > 1:
                    # 第三次尝试：添加Referer
                    current_headers['Referer'] = 'https://www.google.com/'
                
                timeout = self.default_timeout if hasattr(self, 'default_timeout') else 70
                response = self.session.get(url, timeout=timeout, headers=current_headers)
                response.raise_for_status()
                return response
                
            except requests.exceptions.HTTPError as e:
                last_exception = e
                if e.response.status_code == 403:
                    logger.warning(f"403错误，尝试更换请求策略 (尝试 {attempt + 1}/{max_retries})")
                    continue
                elif e.response.status_code >= 500:
                    logger.warning(f"服务器错误 {e.response.status_code}，稍后重试 (尝试 {attempt + 1}/{max_retries})")
                    continue
                else:
                    # 其他HTTP错误直接抛出
                    raise
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"网络错误，重试 (尝试 {attempt + 1}/{max_retries}): {e}")
                continue
            except Exception as e:
                last_exception = e
                logger.warning(f"未预期错误，重试 (尝试 {attempt + 1}/{max_retries}): {e}")
                continue
        
        # 所有重试都失败，抛出最后一个异常
        raise last_exception

    def _handle_gz_sitemap(self, content: bytes, url: str) -> Dict[str, Optional[str]]:
        """处理.gz压缩的sitemap文件（保留向后兼容）"""
        # 创建临时响应对象
        class TempResponse:
            def __init__(self, content, url):
                self.content = content
                self.url = url
                self.headers = {}
        
        return self._handle_compressed_sitemap(TempResponse(content, url), url)

    def _parse_rss_feed(self, url: str) -> Dict[str, Optional[str]]:
        """解析RSS feed格式"""
        try:
            response = self.session.get(url, timeout=70)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            sitemap_data = {}
            
            # RSS格式解析 - 支持多种RSS结构
            # 方法1: 标准RSS格式 <item><link>
            for item in root.findall('.//item'):
                link_elem = item.find('link')
                pubdate_elem = item.find('pubDate')
                
                # 如果没有找到link元素，尝试查找guid元素
                if link_elem is None:
                    link_elem = item.find('guid')
                
                if link_elem is not None and link_elem.text:
                    url_text = link_elem.text.strip()
                    if not SitemapParser._should_exclude_url(url_text):
                        pubdate_text = pubdate_elem.text.strip() if pubdate_elem is not None and pubdate_elem.text else None
                        sitemap_data[url_text] = pubdate_text
            
            # 方法2: 如果标准方法没找到URL，尝试其他RSS变体
            if not sitemap_data:
                # 查找所有包含URL的元素
                for elem in root.iter():
                    if elem.text and elem.text.strip().startswith('http'):
                        url_text = elem.text.strip()
                        if not SitemapParser._should_exclude_url(url_text):
                            sitemap_data[url_text] = None
            
            domain_part = urlparse(url).netloc if url else '***'
            logger.info(f"成功解析RSS feed: {domain_part}")
            return sitemap_data

        except Exception as e:
            logger.error(f"解析RSS feed失败: {e}")
            return {}

    def _parse_txt_sitemap(self, url: str) -> Dict[str, Optional[str]]:
        """解析纯文本格式的sitemap（每行一个URL）"""
        try:
            # 使用更完整的浏览器请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/plain,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = self.session.get(url, timeout=70, headers=headers)
            response.raise_for_status()
            
            # 解析文本内容
            content = response.text
            sitemap_data = {}
            
            for line in content.splitlines():
                line = line.strip()
                if line and line.startswith('http'):
                    if not SitemapParser._should_exclude_url(line):
                        sitemap_data[line] = None  # TXT格式通常没有lastmod信息
            
            domain_part = urlparse(url).netloc if url else '***'
            logger.info(f"成功解析TXT sitemap: {domain_part}")
            return sitemap_data

        except Exception as e:
            logger.error(f"解析TXT sitemap失败: {e}")
            return {}

    def _parse_hahagames_sitemap(self, url: str) -> Dict[str, Optional[str]]:
        """特殊处理hahagames.com的sitemap"""
        try:
            logger.info("开始特殊处理hahagames.com sitemap")
            
            # 使用多种不同的请求头尝试
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0'
            ]
            
            referers = [
                'https://www.google.com/',
                'https://www.bing.com/',
                'https://duckduckgo.com/',
                'https://www.hahagames.com/',
                ''  # 无Referer
            ]
            
            for i, user_agent in enumerate(user_agents):
                for j, referer in enumerate(referers):
                    try:
                        logger.info(f"尝试方案 {i+1}-{j+1}: UA={i+1}, Referer={j+1}")
                        
                        headers = {
                            'User-Agent': user_agent,
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'same-origin' if referer else 'none',
                            'Cache-Control': 'no-cache',
                            'Pragma': 'no-cache',
                        }
                        
                        if referer:
                            headers['Referer'] = referer
                        
                        # 创建新的session避免cookie干扰
                        temp_session = requests.Session()
                        temp_session.headers.update(headers)
                        
                        # 先访问主页建立session
                        if referer == 'https://www.hahagames.com/':
                            try:
                                temp_session.get('https://www.hahagames.com/', timeout=30)
                                time.sleep(2)  # 等待2秒
                            except:
                                pass
                        
                        # 请求sitemap
                        response = temp_session.get(url, timeout=70)
                        response.raise_for_status()
                        
                        logger.info(f"成功获取响应: 状态码={response.status_code}, 内容长度={len(response.content)}")
                        
                        # 检查内容类型
                        content_type = response.headers.get('content-type', '').lower()
                        logger.info(f"Content-Type: {content_type}")
                        
                        # 如果是HTML，尝试从中提取sitemap链接
                        if 'text/html' in content_type:
                            return self._extract_sitemap_from_html(response.text, url)
                        
                        # 尝试解析XML
                        try:
                            root = ET.fromstring(response.content)
                            sitemap_data = self._extract_urls_from_xml(root)
                            
                            if not sitemap_data:
                                sitemap_data = self._try_parse_sitemap_index(root, url)
                            
                            if sitemap_data:
                                domain_part = urlparse(url).netloc if url else '***'
                                logger.info(f"{domain_part}解析成功: {len(sitemap_data)} 个URL")
                                return sitemap_data
                                
                        except ET.ParseError as e:
                            logger.warning(f"XML解析失败: {e}")
                            # 记录内容长度用于调试，但不输出敏感内容
                            logger.debug(f"内容长度: {len(response.content)} bytes")
                            continue
                        
                        temp_session.close()
                        
                    except requests.RequestException as e:
                        logger.warning(f"请求失败 (方案 {i+1}-{j+1}): {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"处理失败 (方案 {i+1}-{j+1}): {e}")
                        continue
                    
                    # 每次尝试间隔
                    time.sleep(1)
            
            logger.error("所有方案都失败了，无法获取hahagames.com sitemap")
            return {}
            
        except Exception as e:
            logger.error(f"hahagames.com特殊处理失败: {e}")
            return {}

    def _parse_html_sitemap(self, response, url: str) -> Dict[str, Optional[str]]:
        """解析HTML格式的sitemap"""
        try:
            html_content = response.text
            domain_part = urlparse(url).netloc if url else '***'

            # 首先尝试从HTML中提取sitemap链接
            sitemap_data = self._extract_sitemap_from_html(html_content, url)

            if sitemap_data:
                logger.info(f"从HTML中找到并解析了sitemap链接: {domain_part}")
                return sitemap_data

            # 如果没有找到sitemap链接，尝试直接从HTML页面提取URL
            logger.info(f"未找到sitemap链接，尝试直接从HTML页面提取URL: {domain_part}")
            return self._extract_urls_from_html(html_content, url)

        except Exception as e:
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"HTML sitemap解析失败: {domain_part}, 错误: {e}")
            return {}

    def _extract_sitemap_from_html(self, html_content: str, original_url: str) -> Dict[str, Optional[str]]:
        """从HTML页面中提取sitemap链接"""
        try:
            sitemap_data = {}
            
            # 查找常见的sitemap链接模式
            import re
            
            # 查找sitemap相关的链接
            sitemap_patterns = [
                r'<link[^>]*rel=["\']sitemap["\'][^>]*href=["\']([^"\']+)["\']',
                r'<a[^>]*href=["\']([^"\']*sitemap[^"\']*\.xml[^"\']*)["\']',
                r'href=["\']([^"\']*sitemap[^"\']*)["\']',
                r'(https?://[^"\'\s]*sitemap[^"\'\s]*\.xml[^"\'\s]*)',
            ]
            
            found_links = []
            for pattern in sitemap_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                found_links.extend(matches)
            
            # 去重并过滤
            unique_links = list(set(found_links))
            logger.info(f"从HTML中找到 {len(unique_links)} 个潜在sitemap链接")
            
            for link in unique_links[:5]:  # 最多处理5个链接
                try:
                    # 构建完整URL
                    if link.startswith('http'):
                        full_url = link
                    elif link.startswith('/'):
                        base_url = '/'.join(original_url.split('/')[:3])
                        full_url = base_url + link
                    else:
                        base_url = '/'.join(original_url.split('/')[:-1])
                        full_url = base_url + '/' + link
                    
                    domain_part = urlparse(full_url).netloc if full_url else '***'
                    logger.info(f"尝试解析找到的sitemap: {domain_part}")

                    # 递归解析找到的sitemap
                    sub_data = self.download_and_parse_sitemap(full_url, "sub")
                    sitemap_data.update(sub_data)
                    
                except Exception as e:
                    logger.warning(f"解析子sitemap失败: {link}, 错误: {e}")
                    continue
            
            return sitemap_data
            
        except Exception as e:
            logger.error(f"从HTML提取sitemap失败: {e}")
            return {}

    def _extract_urls_from_html(self, html_content: str, base_url: str) -> Dict[str, Optional[str]]:
        """直接从HTML页面提取URL"""
        try:
            import re
            from urllib.parse import urljoin, urlparse

            sitemap_data = {}
            domain = urlparse(base_url).netloc

            # 常见的URL提取模式
            url_patterns = [
                # href属性中的链接
                r'href=["\']([^"\']+)["\']',
                # JavaScript中的URL
                r'["\']https?://[^"\']+["\']',
                # 相对路径链接
                r'href=["\'](/[^"\']*)["\']',
            ]

            found_urls = set()

            for pattern in url_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    # 构建完整URL
                    if match.startswith('http'):
                        full_url = match
                    elif match.startswith('/'):
                        full_url = urljoin(base_url, match)
                    else:
                        continue

                    # 过滤：只保留同域名的内容URL
                    if self._is_valid_content_url(full_url, domain):
                        found_urls.add(full_url)

            # 转换为sitemap格式
            for url in found_urls:
                if not self._should_exclude_url(url):
                    sitemap_data[url] = None  # HTML页面通常没有lastmod信息

            logger.info(f"从HTML页面提取到 {len(sitemap_data)} 个有效URL")
            return sitemap_data

        except Exception as e:
            logger.error(f"从HTML页面提取URL失败: {e}")
            return {}

    def _is_valid_content_url(self, url: str, domain: str) -> bool:
        """判断URL是否是有效的内容URL"""
        try:
            parsed = urlparse(url)

            # 必须是同域名
            if parsed.netloc != domain:
                return False

            path = parsed.path.lower()

            # 排除常见的非内容URL
            excluded_patterns = [
                '/css/', '/js/', '/images/', '/img/', '/assets/', '/ui/',
                '/admin/', '/api/', '/ajax/', '/login/', '/register/',
                '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
                '.pdf', '.zip', '.rar', '.xml', '/search', '/contact', '/about',
                '/rss', '/feed', '/sitemap', '/robots', '/favicon'
            ]

            for pattern in excluded_patterns:
                if pattern in path:
                    return False

            # 游戏网站特定的内容URL模式
            content_patterns = [
                '/game/', '/games/', '/play/', '/category/',
                '/tag/', '/genre/', '/arcade/', '/puzzle/',
                '/action/', '/adventure/', '/strategy/', '/sports/'
            ]

            # 如果包含内容模式，认为是有效URL
            for pattern in content_patterns:
                if pattern in path:
                    return True

            # 如果路径看起来像内容页面（有意义的路径，不是根目录）
            if len(path) > 1 and path != '/' and not path.endswith('/'):
                # 检查是否包含有意义的路径段
                path_segments = [seg for seg in path.split('/') if seg]
                if len(path_segments) >= 1:
                    # 路径段长度合理且包含字母
                    last_segment = path_segments[-1]
                    if 3 <= len(last_segment) <= 100 and re.search(r'[a-zA-Z]', last_segment):
                        return True

            return False

        except Exception:
            return False

    def _try_parse_sitemap_index(self, root: ET.Element, original_url: str) -> Dict[str, Optional[str]]:
        """尝试解析sitemap index文件，获取子sitemap并合并结果"""
        try:
            # XML命名空间
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
            }
            
            # 查找sitemap元素而不是url元素 - 使用多种方法确保兼容性
            sitemap_urls = []
            
            # 方法1: 使用命名空间前缀
            for sitemap_elem in root.findall('.//sm:sitemap', namespaces):
                loc_elem = sitemap_elem.find('./sm:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    sitemap_urls.append(loc_elem.text.strip())
            
            # 方法2: 如果方法1失败，直接遍历查找
            if not sitemap_urls:
                for elem in root.iter():
                    if elem.tag.endswith('}sitemap') or elem.tag == 'sitemap':
                        for child in elem:
                            if (child.tag.endswith('}loc') or child.tag == 'loc') and child.text:
                                sitemap_urls.append(child.text.strip())
            
            # 方法3: 检查是否为纯文本格式的sitemap index (如game-game.com)
            if not sitemap_urls:
                sitemap_urls = self._extract_text_sitemap_urls(root, original_url)
            
            # 验证找到的URL是否都是sitemap格式
            if sitemap_urls:
                xml_count = sum(1 for url in sitemap_urls if url.endswith('.xml') or url.endswith('.xml.gz'))
                if xml_count > len(sitemap_urls) * 0.8:  # 80%以上是XML文件才认为是sitemap index
                    logger.info(f"检测到sitemap index格式，XML文件比例: {xml_count}/{len(sitemap_urls)}")
                else:
                    logger.warning(f"URL列表中XML文件比例过低: {xml_count}/{len(sitemap_urls)}，可能不是sitemap index")
                    return {}
            
            if sitemap_urls:
                logger.info(f"发现sitemap index，包含 {len(sitemap_urls)} 个子sitemap")
                
                # 合并所有子sitemap的结果
                combined_data = {}
                for sub_url in sitemap_urls[:5]:  # 限制最多处理5个子sitemap
                    domain_part = urlparse(sub_url).netloc if sub_url else '***'
                    logger.info(f"解析子sitemap: {domain_part}")
                    try:
                        sub_data = self.download_and_parse_sitemap(sub_url, "sub")
                        combined_data.update(sub_data)
                        time.sleep(0.5)  # 避免请求过快
                    except Exception as e:
                        logger.warning(f"解析子sitemap失败: {domain_part}, 错误: {e}")
                        continue
                
                logger.info(f"sitemap index解析完成，总共获得 {len(combined_data)} 个URL")
                return combined_data
            
            return {}
            
        except Exception as e:
            logger.error(f"解析sitemap index失败: {e}")
            return {}

    def _extract_text_sitemap_urls(self, root: ET.Element, original_url: str) -> List[str]:
        """从纯文本内容中提取sitemap URL列表（如game-game.com格式）"""
        try:
            sitemap_urls = []
            
            # 遍历所有文本内容，查找URL
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    text = elem.text.strip()
                    # 按空格分割，查找所有URL
                    for part in text.split():
                        part = part.strip()
                        if (part.startswith('http') and 
                            ('.xml' in part or '.gz' in part) and 
                            'sitemap' in part.lower()):
                            sitemap_urls.append(part)
            
            # 去重并限制数量
            unique_urls = list(dict.fromkeys(sitemap_urls))  # 保持顺序的去重
            logger.info(f"从文本内容中提取到 {len(unique_urls)} 个sitemap URL")
            
            return unique_urls[:20]  # 限制最多20个子sitemap
            
        except Exception as e:
            logger.error(f"提取文本sitemap URL失败: {e}")
            return []

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

        # 查找所有URL条目 - 使用多种方法以确保兼容性
        url_elements = []
        
        # 方法1: 使用命名空间前缀
        url_elements = root.findall('.//sm:url', namespaces)
        
        # 方法2: 如果方法1失败，尝试完整命名空间
        if not url_elements:
            url_elements = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url')
        
        # 方法3: 如果前面都失败，直接遍历查找
        if not url_elements:
            for elem in root.iter():
                if elem.tag.endswith('}url') or elem.tag == 'url':
                    url_elements.append(elem)
        
        # 方法4: 最后尝试不带命名空间
        if not url_elements:
            url_elements = root.findall('.//url')
        
        for url_elem in url_elements:
            # 查找loc和lastmod元素，使用多种方法
            loc_elem = None
            lastmod_elem = None
            
            # 尝试带命名空间前缀的查找
            loc_elem = url_elem.find('./sm:loc', namespaces)
            lastmod_elem = url_elem.find('./sm:lastmod', namespaces)
            
            # 如果失败，直接遍历子元素查找
            if loc_elem is None or lastmod_elem is None:
                for child in url_elem:
                    if child.tag.endswith('}loc') or child.tag == 'loc':
                        loc_elem = child
                    elif child.tag.endswith('}lastmod') or child.tag == 'lastmod':
                        lastmod_elem = child

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

    def _try_regex_extraction(self, response, url: str) -> Dict[str, Optional[str]]:
        """尝试使用正则表达式提取URL"""
        try:
            content = response.text

            # 检测内容是否适合正则提取
            if not self._is_suitable_for_regex(content):
                logger.debug("内容不适合正则表达式提取")
                return {}

            # 根据域名选择合适的正则模式
            domain_patterns = self._get_domain_patterns(url)

            urls = set()
            for pattern in domain_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                urls.update(matches)

            # 过滤和验证URL
            validated_urls = {}
            for url_text in urls:
                if self._is_valid_extracted_url(url_text):
                    validated_urls[url_text] = None  # 正则方法暂不提取lastmod

            logger.debug(f"正则表达式提取到 {len(validated_urls)} 个有效URL")
            return validated_urls

        except Exception as e:
            logger.debug(f"正则表达式提取出错: {e}")
            return {}

    def _is_suitable_for_regex(self, content: str) -> bool:
        """判断内容是否适合正则表达式提取"""
        # 检查是否为压缩内容
        if content.startswith('\x1f\x8b'):
            return False

        # 检查是否包含真正复杂的XML结构（排除常见的sitemap命名空间）
        complex_xml_indicators = [
            '<?xml-stylesheet',
            '<![CDATA[',
            '&lt;', '&gt;', '&amp;'  # 实体编码
        ]

        for indicator in complex_xml_indicators:
            if indicator in content:
                return False

        # 检查URL密度（URL较多时正则更有优势）
        url_count = len(re.findall(r'https?://[^\s<>"\']+', content))
        if url_count > 10:  # 如果有足够的URL，就尝试正则提取
            return True

        # 检查内容大小（大文件更适合正则处理）
        if len(content) > 500000:  # 500KB以上
            return True

        return False

    def _get_domain_patterns(self, url: str) -> List[str]:
        """根据域名获取合适的正则模式"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # 基础模式
        base_domain = re.escape(domain)
        patterns = [
            f'https://{base_domain}/[a-zA-Z0-9\\-/._~:?#\\[\\]@!$&\'()*+,;=%]+',
        ]

        # 针对特定域名的优化模式
        domain_specific_patterns = {
            'azgames.io': [
                f'https://{base_domain}[^\\s<>"\']*',  # 使用与123.py相同的模式
            ],
            'nointernetgame.com': [
                f'https://{base_domain}/game/[a-zA-Z0-9\\-/]+',
                f'https://{base_domain}/[a-zA-Z0-9\\-]+\\.html',
            ],
            # 可以继续添加其他域名的特定模式
        }

        if domain in domain_specific_patterns:
            patterns.extend(domain_specific_patterns[domain])

        return patterns

    def _is_valid_extracted_url(self, url: str) -> bool:
        """验证提取的URL是否有效"""
        # 排除明显的非内容URL
        exclude_patterns = [
            r'sitemap.*\.xml',
            r'\.(?:css|js|png|jpg|jpeg|gif|ico|svg|woff|ttf)$',
            r'/(?:admin|api|wp-admin|wp-content)/',
            r'\.(?:zip|rar|pdf|doc|docx)$',
        ]

        for pattern in exclude_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        # 检查URL长度合理性
        if len(url) > 200 or len(url) < 10:
            return False

        return True

    def _is_extraction_successful(self, result: Dict) -> bool:
        """判断提取是否成功"""
        if not result:
            return False

        # 检查提取的URL数量是否合理
        url_count = len(result)
        if url_count < 5:  # 太少可能提取不完整
            return False

        if url_count > 10000:  # 太多可能包含噪音
            return False

        # 检查URL质量（简单启发式）
        valid_urls = 0
        for url in list(result.keys())[:10]:  # 检查前10个URL
            if self._looks_like_content_url(url):
                valid_urls += 1

        # 至少70%的URL看起来像内容URL
        return (valid_urls / min(10, len(result))) >= 0.7

    def _looks_like_content_url(self, url: str) -> bool:
        """简单判断URL是否像内容URL"""
        # 包含常见的内容路径
        content_indicators = [
            '/game/', '/article/', '/post/', '/page/',
            '/category/', '/tag/', '/archive/',
        ]

        for indicator in content_indicators:
            if indicator in url.lower():
                return True

        # 或者路径看起来像内容标识符
        path_part = url.split('/')[-1]
        if re.match(r'^[a-zA-Z0-9\-]{3,50}$', path_part):
            return True

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
