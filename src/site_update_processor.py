#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点更新处理器模块
专门负责处理站点更新的单一职责
"""

import base64
import json
import logging
from typing import Dict, List, Any
from urllib.parse import urlparse

from src.config import config
from src.data_manager import data_manager
from src.encryption import encryptor
from src.sitemap_api import sitemap_api

# 配置日志
logger = logging.getLogger('content_watcher.site_update_processor')


class SiteUpdateProcessor:
    """站点更新处理器 - 符合单一职责原则"""

    def process_site_updates(self, site_id: str, site_data: dict, 
                           url_keywords_map: dict, global_keyword_data: dict) -> List[str]:
        """处理单个网站的更新，使用全局关键词数据

        Args:
            site_id: 站点ID
            site_data: 站点数据，包含更新URL等信息
            url_keywords_map: URL到关键词的映射
            global_keyword_data: 全局关键词数据

        Returns:
            更新的URL列表
        """
        logger.info(f"处理网站 {site_id} 的更新")

        updated_urls = site_data.get('updated_urls', [])
        new_encrypted_data = site_data.get('new_encrypted_data', [])

        if not updated_urls:
            logger.info(f"网站 {site_id} 没有需要处理的更新")
            return []

        # 构建关键词数据映射
        keyword_results, keywords_data_to_store = self._build_keyword_mappings(
            url_keywords_map, global_keyword_data
        )

        # 发送到网站地图API
        if config.sitemap_api_enabled and updated_urls:
            self._send_to_sitemap_api(updated_urls, url_keywords_map, keyword_results)

        # 保存关键词数据
        self._save_keyword_data(updated_urls, keywords_data_to_store, new_encrypted_data)

        # 更新数据存储
        data_manager.update_site_data(site_id, new_encrypted_data)

        logger.info(f"网站 {site_id} 处理完成")
        return updated_urls

    def _build_keyword_mappings(self, url_keywords_map: dict, 
                              global_keyword_data: dict) -> tuple[dict, dict]:
        """构建关键词数据映射"""
        keyword_results = {}
        keywords_data_to_store = {}

        for url, keyword in url_keywords_map.items():
            if keyword in global_keyword_data:
                # 获取原始关键词数据
                original_keyword_data = global_keyword_data[keyword]

                # 为每个URL创建一个包含原始关键词数据的结果
                keyword_results[url] = {
                    'status': 'success',
                    'geo_target': '全球',
                    'total_results': 1,
                    'data': [original_keyword_data]  # 只添加原始关键词数据
                }

                # 只存储当前关键词的数据
                keywords_data_to_store[url] = {
                    'keyword': keyword,
                    'data': original_keyword_data
                }

        return keyword_results, keywords_data_to_store

    def _send_to_sitemap_api(self, updated_urls: List[str], 
                           url_keywords_map: dict, keyword_results: dict) -> None:
        """发送更新数据到网站地图API"""
        try:
            # 准备批量提交数据
            batch_updates = []

            for url in updated_urls:
                # 获取URL的关键词
                keyword = url_keywords_map.get(url, "")
                keywords_list = [keyword] if keyword else []
                # 获取关键词数据
                api_data = keyword_results.get(url, {})
                
                try:
                    # 记录关键词数据的结构（调试级别）
                    logger.debug(f"关键词数量: {len(keywords_list)}")
                    logger.debug(f"关键词数据类型: {type(api_data)}, 是否为空: {not bool(api_data)}")
                    if api_data:
                        logger.debug(f"关键词数据包含的键: {list(api_data.keys())}")
                    if api_data and 'data' in api_data:
                        logger.debug(f"关键词数据包含 {len(api_data['data'])} 个项目")

                    # 准备单条更新数据
                    update_data = sitemap_api.prepare_update_data(url, keywords_list, api_data)
                    batch_updates.append(update_data)
                except Exception as e:
                    # 不输出完整URL，避免敏感信息泄露
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.error(f"准备URL数据时出错: 域名={domain_part}")

            # 批量提交数据
            if batch_updates:
                self._batch_submit_updates(batch_updates)
                
        except Exception as e:
            logger.error(f"发送数据到API时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    def _batch_submit_updates(self, batch_updates: List[Dict]) -> None:
        """批量提交更新数据"""
        from collections import deque
        import time

        # 创建队列
        update_queue = deque(batch_updates)
        max_batch_size = sitemap_api.max_batch_size
        total_updates = len(batch_updates)
        processed_updates = 0
        failed_updates = []  # 存储失败的更新

        logger.info(f"开始批量提交处理，共 {total_updates} 条数据，每批 {max_batch_size} 条")

        # 处理队列中的数据
        while update_queue:
            # 从队列中获取一批数据
            current_batch = []
            batch_size = min(max_batch_size, len(update_queue))

            for _ in range(batch_size):
                if update_queue:  # 再次检查队列是否为空
                    current_batch.append(update_queue.popleft())

            # 更新进度
            processed_updates += len(current_batch)
            progress = (processed_updates / total_updates) * 100

            # 只在最后一批输出进度日志
            if processed_updates == total_updates:
                logger.info(f"批量提交进度: {processed_updates}/{total_updates} ({progress:.1f}%)")

            # 批量提交
            batch_sent = sitemap_api.send_batch_updates(current_batch)

            if batch_sent:
                # 只在最后一批输出成功日志
                if processed_updates == total_updates:
                    logger.info(f"成功批量提交全部 {total_updates} 条数据")
            else:
                logger.warning(f"批量提交 {len(current_batch)} 条数据失败")
                # 将所有失败的批次数据添加到失败列表
                failed_updates.extend(current_batch)

                # 记录详细的批量提交失败信息，帮助调试
                for i, update_data in enumerate(current_batch):
                    url = update_data.get("new_url", "")
                    keywords = update_data.get("keywords", [])
                    keyword_trends = update_data.get("keyword_trends_data", [])
                    # 不输出完整URL，避免敏感信息泄露
                    domain_part = urlparse(url).netloc if url else '***'
                    logger.debug(f"批量提交失败的数据 {i+1}/{len(current_batch)}: "
                               f"域名={domain_part}, 关键词={keywords}, 趋势数据项数={len(keyword_trends)}")

            # 批次间添加小延迟，避免请求过快
            if update_queue:  # 如果还有数据要处理
                time.sleep(1)  # 等待1秒

        # 最终统计
        success_count = total_updates - len(failed_updates)

        # 只在有失败或全部成功时输出统计信息
        if failed_updates:
            logger.warning(f"批量提交完成，成功: {success_count}/{total_updates}, 失败: {len(failed_updates)}")
            self._log_failed_updates(failed_updates)
        elif total_updates > 0:  # 只在有数据提交时输出
            logger.info(f"批量提交完成，所有 {total_updates} 条数据提交成功")

    def _log_failed_updates(self, failed_updates: List[Dict]) -> None:
        """记录失败的更新"""
        logger.warning(f"有 {len(failed_updates)} 条数据提交失败，请检查日志")

        # 输出失败的URL详情
        for i, update in enumerate(failed_updates[:5]):  # 只显示前5个失败的URL
            url = update.get("new_url", "")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.warning(f"失败域名 {i+1}: {domain_part}")

        if len(failed_updates) > 5:
            logger.warning(f"还有 {len(failed_updates) - 5} 个失败的URL未显示")

    def _save_keyword_data(self, updated_urls: List[str], 
                         keywords_data_to_store: dict, new_encrypted_data: List[Dict]) -> None:
        """保存关键词数据到加密数据中"""
        for url in updated_urls:
            if url in keywords_data_to_store:
                # 找到URL数据的索引
                url_encrypted = encryptor.encrypt_url(url)
                for i, item in enumerate(new_encrypted_data):
                    if item.get('encrypted_url') == url_encrypted:
                        # 加密关键词数据
                        keywords_json = json.dumps(keywords_data_to_store[url])
                        encrypted_keywords = encryptor.encrypt_data(keywords_json.encode('utf-8'))
                        new_encrypted_data[i]['keywords_data'] = base64.b64encode(
                            encrypted_keywords).decode('utf-8')
                        break 