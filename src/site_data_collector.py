#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点数据收集器模块
专门负责站点数据收集的单一职责
"""

import base64
import json
import logging
import random
from typing import Tuple, Dict, List, Set

from src.data_manager import data_manager
from src.encryption import encryptor
from src.keyword_extractor import keyword_extractor
from src.sitemap_parser import sitemap_parser

# 配置日志
logger = logging.getLogger('content_watcher.site_data_collector')


class SiteDataCollector:
    """站点数据收集器 - 符合单一职责原则"""

    def __init__(self, max_first_run_updates: int = 0):
        """初始化收集器
        
        Args:
            max_first_run_updates: 首次运行时最多报告的更新数量，0表示不限制
        """
        self.max_first_run_updates = max_first_run_updates

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

        # 检查是否是首次运行（没有历史数据）
        is_first_run = len(previous_urls) == 0

        # 查找今天更新的URL
        updated_urls, new_encrypted_data, stats = self._find_updated_urls(
            sitemap_data, previous_urls, previous_keywords_data
        )

        if not updated_urls:
            logger.info(f"网站 {site_id} 没有发现更新")
            # 更新储存的数据
            data_manager.update_site_data(site_id, new_encrypted_data)
            return site_id, {}

        # 提取关键词并过滤URL
        url_keywords_map, valid_urls, keywords_set = self._extract_and_filter_keywords(updated_urls)
        updated_urls = valid_urls
        logger.info(f"网站 {site_id} 过滤后的有效URL数量: {len(updated_urls)}")

        # 首次运行限制处理
        if is_first_run and self._should_limit_first_run(updated_urls):
            updated_urls, url_keywords_map, keywords_set = self._limit_first_run_updates(
                updated_urls, url_keywords_map
            )

        # 记录统计信息
        new_url_count, updated_url_count = stats
        logger.info(f"网站 {site_id} 统计: 新URL数量: {new_url_count}, 更新URL数量: {updated_url_count}, 总计: {len(updated_urls)}")

        # 返回收集的数据
        return site_id, {
            'updated_urls': updated_urls,
            'url_keywords_map': url_keywords_map,
            'keywords': list(keywords_set),
            'new_encrypted_data': new_encrypted_data,
            'is_first_run': is_first_run
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

            # 创建加密后的URL数据以保存
            encrypted_url = encryptor.encrypt_url(url)
            url_data = {
                'encrypted_url': encrypted_url,
                'lastmod': lastmod
            }

            # 如果有上一次的关键词数据，保留它
            if url in previous_keywords_data:
                # 加密关键词数据
                keywords_json = json.dumps(previous_keywords_data[url])
                encrypted_keywords = encryptor.encrypt_data(keywords_json.encode('utf-8'))
                url_data['keywords_data'] = base64.b64encode(encrypted_keywords).decode('utf-8')

            new_encrypted_data.append(url_data)

        return updated_urls, new_encrypted_data, (new_url_count, updated_url_count)

    def _extract_and_filter_keywords(self, updated_urls: List[str]) -> Tuple[Dict[str, str], List[str], Set[str]]:
        """提取关键词并过滤URL"""
        url_keywords_map = {}
        valid_urls = []
        keywords_set = set()

        for url in updated_urls:
            keyword = keyword_extractor.extract_keywords_from_url(url)
            # 只处理有效关键词的URL
            if keyword:  # 如果关键词不为空
                url_keywords_map[url] = keyword
                valid_urls.append(url)
                keywords_set.add(keyword)

        return url_keywords_map, valid_urls, keywords_set

    def _should_limit_first_run(self, updated_urls: List[str]) -> bool:
        """判断是否应该限制首次运行的更新数量"""
        return (self.max_first_run_updates > 0 and 
                len(updated_urls) > self.max_first_run_updates)

    def _limit_first_run_updates(self, updated_urls: List[str], 
                                url_keywords_map: Dict[str, str]) -> Tuple[List[str], Dict[str, str], Set[str]]:
        """限制首次运行的更新数量"""
        logger.info(f"首次运行，更新URL数量({len(updated_urls)})超过限制({self.max_first_run_updates})，将只处理部分更新")
        # 随机选择一些URL作为示例
        sample_urls = random.sample(updated_urls, self.max_first_run_updates)
        # 更新关键词映射
        new_url_keywords_map = {url: url_keywords_map[url] for url in sample_urls if url in url_keywords_map}
        # 更新关键词集合
        new_keywords_set = set(new_url_keywords_map.values())
        
        return sample_urls, new_url_keywords_map, new_keywords_set 