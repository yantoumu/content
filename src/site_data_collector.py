#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点数据收集器模块
专门负责站点数据收集的单一职责
"""

import base64
import json
import logging
from typing import Tuple, Dict, List, Set

from src.data_manager import data_manager
from src.encryption import encryptor
from src.keyword_extractor import keyword_extractor
from src.sitemap_parser import sitemap_parser

# 配置日志
logger = logging.getLogger('content_watcher.site_data_collector')


class SiteDataCollector:
    """站点数据收集器 - 符合单一职责原则"""

    def __init__(self):
        """初始化收集器 - 统一使用全量处理模式"""
        logger.info("SiteDataCollector初始化: 启用全量处理模式")

    def collect_site_data(self, site_url: str, site_index: int) -> Tuple[str, Dict]:
        """收集单个网站的更新URL和关键词

        Args:
            site_url: 网站URL
            site_index: 网站索引

        Returns:
            站点ID和包含更新URL、关键词等信息的字典
        """
        site_id = data_manager.get_site_identifier(site_url)
        logger.info(f"正在收集网站 {site_index+1} ({site_id}) 的数据")

        try:
            # 下载和解析网站地图
            sitemap_data = sitemap_parser.download_and_parse_sitemap(site_url, site_id)
            if not sitemap_data:
                logger.warning(f"网站 {site_id} 未返回有效数据")
                return site_id, {}
        except Exception as e:
            logger.error(f"网站 {site_id} 数据收集失败: {e}")
            return site_id, {}

        # 解密上一次的数据用于对比
        previous_urls, previous_keywords_data = data_manager.get_previous_urls(site_id)

        # 查找今天更新的URL
        updated_urls, new_encrypted_data, stats = self._find_updated_urls(
            sitemap_data, previous_urls, previous_keywords_data
        )

        if not updated_urls:
            logger.info(f"网站 {site_id} 没有发现更新")
            # 没有更新时，不进行保存操作，让site_update_processor处理
            return site_id, {
                'updated_urls': [],
                'new_encrypted_data': new_encrypted_data
            }

        # 提取关键词并过滤URL
        url_keywords_map, valid_urls, keywords_set = self._extract_and_filter_keywords(updated_urls)
        updated_urls = valid_urls
        logger.info(f"网站 {site_id} 过滤后的有效URL数量: {len(updated_urls)}")

        # 记录统计信息
        new_url_count, updated_url_count = stats
        logger.info(f"网站 {site_id} 统计: 新URL数量: {new_url_count}, 更新URL数量: {updated_url_count}, 总计: {len(updated_urls)}")

        # 返回收集的数据
        return site_id, {
            'updated_urls': updated_urls,
            'url_keywords_map': url_keywords_map,
            'keywords': list(keywords_set),
            'new_encrypted_data': new_encrypted_data
        }

    def _find_updated_urls(self, sitemap_data: Dict, previous_urls: Dict, 
                          previous_keywords_data: Dict) -> Tuple[List[str], List[Dict], Tuple[int, int]]:
        """查找更新的URL"""
        updated_urls = []
        new_encrypted_data = []
        new_url_count = 0
        updated_url_count = 0

        for url, lastmod in sitemap_data.items():
            # 检查URL是否为新URL或今天更新的URL
            is_new = url not in previous_urls

            # 对于已存在的URL，检查lastmod是否更新
            is_updated = False
            if not is_new and lastmod:
                prev_lastmod = previous_urls.get(url)
                if prev_lastmod != lastmod and sitemap_parser.is_updated_today(lastmod):
                    is_updated = True

            # 添加新URL或更新的URL
            if is_new or is_updated:
                if is_new:
                    new_url_count += 1
                else:
                    updated_url_count += 1
                updated_urls.append(url)

            # 只为已存在且有关键词数据的URL创建加密数据
            # 新URL和更新URL的数据将在关键词验证成功后再创建
            if not is_new and not is_updated and url in previous_keywords_data:
                # 这是一个已存在且有关键词数据的URL，保留它
                encrypted_url = encryptor.encrypt_url(url)
                url_data = {
                    'encrypted_url': encrypted_url,
                    'lastmod': lastmod
                }

                # 加密关键词数据
                keywords_json = json.dumps(previous_keywords_data[url])
                encrypted_keywords = encryptor.encrypt_data(keywords_json.encode('utf-8'))
                url_data['keywords_data'] = base64.b64encode(encrypted_keywords).decode('utf-8')

                new_encrypted_data.append(url_data)
            elif not is_new and not is_updated:
                # 这是一个已存在但没有关键词数据的URL，也保留基本信息
                encrypted_url = encryptor.encrypt_url(url)
                url_data = {
                    'encrypted_url': encrypted_url,
                    'lastmod': lastmod
                }
                new_encrypted_data.append(url_data)

        return updated_urls, new_encrypted_data, (new_url_count, updated_url_count)

    def _extract_and_filter_keywords(self, updated_urls: List[str]) -> Tuple[Dict[str, str], List[str], Set[str]]:
        """提取关键词并过滤URL"""
        url_keywords_map = {}
        valid_urls = []
        keywords_set = set()

        for url in updated_urls:
            keyword_raw = keyword_extractor.extract_keywords_from_url(url)
            if not keyword_raw:
                continue

            # 使用统一的关键词规范化函数
            keyword = keyword_extractor.normalize_keyword(keyword_raw)

            # 跳过无效关键词
            if not keyword:
                continue

            url_keywords_map[url] = keyword
            valid_urls.append(url)
            keywords_set.add(keyword)

        return url_keywords_map, valid_urls, keywords_set


