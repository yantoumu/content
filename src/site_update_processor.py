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
from src.keyword_metrics_api import metrics_api
from src.privacy_utils import PrivacyMasker

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
            # 没有更新时，仍需要保存现有的成功数据（保持previous_data.json的完整性）
            # 但只保存已经验证过的数据，不添加新的未验证数据
            self._save_existing_verified_data(site_id, new_encrypted_data)
            return []

        # 构建关键词数据映射
        keyword_results, keywords_data_to_store = self._build_keyword_mappings(
            url_keywords_map, global_keyword_data
        )

        # 只保存查询成功的URL数据
        successful_urls = list(keywords_data_to_store.keys())
        failed_urls = [url for url in updated_urls if url not in successful_urls]

        if failed_urls:
            logger.warning(f"网站 {site_id} 有 {len(failed_urls)} 个URL的关键词查询失败，将在下次运行时重试")

        if successful_urls:
            logger.info(f"网站 {site_id} 有 {len(successful_urls)} 个URL查询成功，将保存完整数据")
            # 更新加密数据，添加关键词数据
            self._update_encrypted_data_with_keywords(new_encrypted_data, keywords_data_to_store, successful_urls)
            # 保存成功查询的URL数据
            data_manager.update_site_data(site_id, new_encrypted_data)
        else:
            logger.warning(f"网站 {site_id} 没有成功查询的URL，不保存数据")

        # 发送到关键词指标批量 API
        if config.metrics_api_enabled and successful_urls:
            self._send_to_metrics_api(successful_urls, url_keywords_map, keyword_results)

        logger.info(f"网站 {site_id} 处理完成")
        return successful_urls

    def _build_keyword_mappings(self, url_keywords_map: dict,
                              global_keyword_data: dict) -> tuple[dict, dict]:
        """构建关键词数据映射，只处理真实查询成功的数据"""
        keyword_results = {}
        keywords_data_to_store = {}
        skipped_count = 0

        for url, keyword in url_keywords_map.items():
            # 尝试找到匹配的关键词数据（支持灵活匹配）
            matched_keyword_data = self._find_matching_keyword_data(keyword, global_keyword_data)

            if matched_keyword_data:
                original_keyword_data, matched_api_keyword = matched_keyword_data

                # 验证数据是否为真实查询结果
                if self._is_valid_keyword_data(original_keyword_data, keyword):
                    # 为每个URL创建一个包含原始关键词数据的结果
                    keyword_results[url] = {
                        'status': 'success',
                        'geo_target': 'GLOBAL',
                        'total_results': 1,
                        'data': [original_keyword_data]  # 只添加原始关键词数据
                    }

                    # 只存储当前关键词的数据
                    keywords_data_to_store[url] = {
                        'keyword': keyword,
                        'data': original_keyword_data
                    }
                else:
                    skipped_count += 1
                    masked_keyword = PrivacyMasker.mask_keyword(keyword)
                    logger.warning(f"跳过无效的关键词数据: {masked_keyword}")
            else:
                skipped_count += 1
                masked_keyword = PrivacyMasker.mask_keyword(keyword)
                logger.warning(f"关键词查询失败，跳过: {masked_keyword}")

        if skipped_count > 0:
            logger.info(f"共跳过 {skipped_count} 个无效或查询失败的关键词")

        return keyword_results, keywords_data_to_store

    def _update_encrypted_data_with_keywords(self, new_encrypted_data: List[Dict],
                                           keywords_data_to_store: Dict[str, Dict],
                                           successful_urls: List[str]) -> None:
        """更新加密数据，为成功查询的URL添加关键词数据

        增强版：如果成功的URL没有对应的加密数据，则创建新的加密数据项
        """
        import base64
        import json
        from src.encryption import encryptor

        # 创建URL到加密数据的映射
        url_to_encrypted_data = {}
        for item in new_encrypted_data:
            if 'encrypted_url' in item:
                try:
                    decrypted_url = encryptor.decrypt_url(item['encrypted_url'])
                    if decrypted_url:
                        url_to_encrypted_data[decrypted_url] = item
                except Exception as e:
                    logger.error(f"解密URL时出错: {e}")

        # 为成功查询的URL添加关键词数据
        for url in successful_urls:
            if url in keywords_data_to_store:
                try:
                    # 如果URL没有对应的加密数据，创建新的
                    if url not in url_to_encrypted_data:
                        logger.debug(f"为成功URL创建新的加密数据: {PrivacyMasker.extract_domain_safely(url)}")
                        encrypted_url = encryptor.encrypt_url(url)
                        new_item = {
                            'encrypted_url': encrypted_url,
                            'lastmod': None  # 新URL暂时没有lastmod信息
                        }
                        url_to_encrypted_data[url] = new_item
                        new_encrypted_data.append(new_item)

                    # 加密关键词数据并添加到对应项
                    keywords_json = json.dumps(keywords_data_to_store[url])
                    encrypted_keywords = encryptor.encrypt_data(keywords_json.encode('utf-8'))
                    url_to_encrypted_data[url]['keywords_data'] = base64.b64encode(encrypted_keywords).decode('utf-8')

                except Exception as e:
                    logger.error(f"处理URL加密数据时出错: {e}")
                    # 不输出完整URL，避免敏感信息泄露
                    domain_part = PrivacyMasker.extract_domain_safely(url)
                    logger.error(f"出错的域名: {domain_part}")

        # 从new_encrypted_data中移除失败的URL，只保留成功的
        successful_encrypted_data = []
        for item in new_encrypted_data:
            if 'encrypted_url' in item:
                try:
                    decrypted_url = encryptor.decrypt_url(item['encrypted_url'])
                    if decrypted_url and decrypted_url in successful_urls:
                        successful_encrypted_data.append(item)
                    elif decrypted_url:
                        # 这是一个失败的URL，不保存
                        logger.debug(f"跳过保存失败查询的URL: {PrivacyMasker.extract_domain_safely(decrypted_url)}")
                except Exception as e:
                    logger.error(f"处理加密URL时出错: {e}")
            else:
                # 保留没有encrypted_url的项目（如果有的话）
                successful_encrypted_data.append(item)

        # 更新原始列表
        new_encrypted_data.clear()
        new_encrypted_data.extend(successful_encrypted_data)

        logger.info(f"成功处理 {len(successful_encrypted_data)} 个URL的加密数据")

    def _save_existing_verified_data(self, site_id: str, new_encrypted_data: List[Dict]) -> None:
        """安全地保存现有的已验证数据，不添加新的未验证数据

        Args:
            site_id: 站点ID
            new_encrypted_data: 包含现有数据的加密数据列表
        """
        # 只保存已经包含keywords_data的URL（这些是之前验证成功的）
        verified_data = []
        for item in new_encrypted_data:
            if 'keywords_data' in item:
                # 这是之前验证成功的数据，可以保留
                verified_data.append(item)
            else:
                # 这是新的未验证数据，不保存
                try:
                    if 'encrypted_url' in item:
                        decrypted_url = encryptor.decrypt_url(item['encrypted_url'])
                        if decrypted_url:
                            domain = PrivacyMasker.extract_domain_safely(decrypted_url)
                            logger.debug(f"跳过保存未验证的URL: {domain}")
                except Exception as e:
                    logger.error(f"处理加密URL时出错: {e}")

        # 只保存已验证的数据
        data_manager.update_site_data(site_id, verified_data)
        logger.info(f"网站 {site_id} 保存了 {len(verified_data)} 个已验证的URL")



    def _is_valid_keyword_data(self, keyword_data: dict, keyword: str) -> bool:
        """验证关键词数据是否为真实查询结果

        Args:
            keyword_data: 关键词数据
            keyword: 关键词字符串

        Returns:
            bool: 数据是否有效
        """
        if not keyword_data or not isinstance(keyword_data, dict):
            return False

        # 检查是否包含必要的字段 - 放宽验证条件
        # 只要有keyword字段或metrics字段之一即可
        has_keyword_field = 'keyword' in keyword_data
        has_metrics_field = 'metrics' in keyword_data

        if not has_keyword_field and not has_metrics_field:
            return False

        # 如果有keyword字段，检查是否匹配（允许合理的变体）
        if has_keyword_field:
            api_keyword = keyword_data.get('keyword', '').strip().lower()
            input_keyword = keyword.strip().lower()
            if api_keyword and not self._keywords_match(api_keyword, input_keyword):
                # 关键词不匹配，记录调试信息
                masked_api_kw = PrivacyMasker.mask_keyword(api_keyword)
                masked_input_kw = PrivacyMasker.mask_keyword(input_keyword)
                logger.debug(f"关键词不匹配: API返回={masked_api_kw}, 期望={masked_input_kw}")
                return False

        # 检查metrics字段
        if has_metrics_field:
            metrics = keyword_data.get('metrics', {})
            if not isinstance(metrics, dict):
                return False

            # 检查是否有基本的指标字段 - 放宽要求，只需要有一个即可
            required_fields = ['avg_monthly_searches', 'competition', 'competition_index']
            has_any_metric = any(field in metrics for field in required_fields)

            if not has_any_metric:
                logger.debug(f"关键词数据缺少所有必要的指标字段: {required_fields}")
                return False
        else:
            # 如果没有metrics字段，但有其他有用的数据，也可以接受
            # 检查是否有其他有用的字段
            useful_fields = ['avg_monthly_searches', 'competition', 'competition_index', 'search_volume']
            has_useful_data = any(field in keyword_data for field in useful_fields)

            if not has_useful_data:
                return False

        # 数据通过验证
        return True

    def _keywords_match(self, api_keyword: str, input_keyword: str) -> bool:
        """检查两个关键词是否匹配，允许合理的变体

        Args:
            api_keyword: API返回的关键词（已转小写）
            input_keyword: 输入的关键词（已转小写）

        Returns:
            bool: 是否匹配
        """
        # 完全匹配
        if api_keyword == input_keyword:
            return True

        # 处理单复数差异（简单的s结尾处理）
        # 检查是否一个是另一个的单数/复数形式
        if api_keyword.endswith('s') and api_keyword[:-1] == input_keyword:
            return True
        if input_keyword.endswith('s') and input_keyword[:-1] == api_keyword:
            return True

        # 处理常见的复数变化
        # 可以根据需要扩展更多规则

        return False

    def _find_matching_keyword_data(self, target_keyword: str, global_keyword_data: dict):
        """在全局关键词数据中查找匹配的关键词数据

        Args:
            target_keyword: 目标关键词
            global_keyword_data: 全局关键词数据字典

        Returns:
            tuple: (关键词数据, 匹配的API关键词) 或 None
        """
        # 首先尝试精确匹配
        if target_keyword in global_keyword_data:
            return global_keyword_data[target_keyword], target_keyword

        # 如果精确匹配失败，尝试灵活匹配
        target_lower = target_keyword.lower()

        for api_keyword, keyword_data in global_keyword_data.items():
            api_keyword_lower = api_keyword.lower()

            # 使用关键词匹配方法检查是否匹配
            if self._keywords_match(api_keyword_lower, target_lower):
                logger.debug(f"找到灵活匹配: 目标='{target_keyword}' -> API='{api_keyword}'")
                return keyword_data, api_keyword

        # 没有找到匹配
        return None

    def _send_to_metrics_api(self, updated_urls: List[str],
                           url_keywords_map: dict, keyword_results: dict) -> None:
        """发送更新数据到关键词指标批量 API"""
        try:
            # 准备批量提交数据
            batch_updates = []

            for url in updated_urls:
                # 获取URL的关键词
                keyword = url_keywords_map.get(url, "")
                if not keyword:
                    # 文档要求 keyword 必填，跳过无关键词 URL
                    continue
                keywords_list = [keyword]
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
                    update_data = metrics_api.prepare_update_data(url, keywords_list, api_data)
                    batch_updates.append(update_data)
                except ValueError as e:
                    # 数据验证失败，跳过这个URL
                    domain_part = PrivacyMasker.extract_domain_safely(url)
                    masked_keyword = PrivacyMasker.mask_keyword(keyword)
                    logger.warning(f"跳过无效数据: 域名={domain_part}, 关键词={masked_keyword}, 原因={e}")
                except Exception as e:
                    # 其他错误
                    domain_part = PrivacyMasker.extract_domain_safely(url)
                    logger.error(f"准备URL数据时出错: 域名={domain_part}, 错误={e}")

            # 批量提交数据
            if batch_updates:
                self._batch_submit_updates(batch_updates)
                
        except Exception as e:
            logger.error(f"发送数据到API时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    def _batch_submit_updates(self, batch_updates: List[Dict]) -> None:
        """批量提交更新数据 - 性能优化版本"""
        from collections import deque
        import time

        # 创建队列
        update_queue = deque(batch_updates)
        max_batch_size = metrics_api.max_batch_size
        total_updates = len(batch_updates)
        processed_updates = 0
        failed_updates = []  # 存储失败的更新
        retry_updates = []  # 存储需要重试的更新

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
            batch_sent = metrics_api.send_batch_updates(current_batch)

            if batch_sent:
                # 只在最后一批输出成功日志
                if processed_updates == total_updates:
                    logger.info(f"成功批量提交全部 {total_updates} 条数据")
            else:
                logger.warning(f"批量提交 {len(current_batch)} 条数据失败，将加入重试队列")
                # 将失败的批次加入重试队列
                retry_updates.extend(current_batch)

                # 记录详细的批量提交失败信息，帮助调试
                for i, update_data in enumerate(current_batch):
                    url = update_data.get("url", "")
                    keywords = [update_data.get("keyword", "")]
                    keyword_trends = update_data.get("metrics", {})
                    # 不输出完整URL，避免敏感信息泄露
                    domain_part = PrivacyMasker.extract_domain_safely(url)
                    logger.debug(f"批量提交失败的数据 {i+1}/{len(current_batch)}: "
                               f"域名={domain_part}, 关键词={keywords}, 趋势数据项数={len(keyword_trends)}")

            # 批次间添加小延迟，避免请求过快
            if update_queue:  # 如果还有数据要处理
                time.sleep(0.5)  # 减少到0.5秒，提升处理速度

        # 处理重试队列
        if retry_updates:
            logger.info(f"开始重试 {len(retry_updates)} 条失败的数据")
            self._retry_failed_updates(retry_updates, failed_updates)

        # 最终统计
        success_count = total_updates - len(failed_updates)

        # 只在有失败或全部成功时输出统计信息
        if failed_updates:
            logger.warning(f"批量提交完成，成功: {success_count}/{total_updates}, 失败: {len(failed_updates)}")
            self._log_failed_updates(failed_updates)
        elif total_updates > 0:  # 只在有数据提交时输出
            logger.info(f"批量提交完成，所有 {total_updates} 条数据提交成功")

    def _retry_failed_updates(self, retry_updates: List[Dict], failed_updates: List[Dict]) -> None:
        """重试失败的更新 - 性能优化：单次重试机制"""
        import time
        from collections import deque

        if not retry_updates:
            return

        # 等待3秒后重试，给API服务器恢复时间
        time.sleep(3)

        # 使用较小的批次大小进行重试
        retry_batch_size = max(1, metrics_api.max_batch_size // 2)
        logger.info(f"重试批次大小: {retry_batch_size}")

        retry_queue = deque(retry_updates)
        retry_success_count = 0

        while retry_queue:
            # 准备重试批次
            current_retry_batch = []
            for _ in range(min(retry_batch_size, len(retry_queue))):
                if retry_queue:
                    current_retry_batch.append(retry_queue.popleft())

            if not current_retry_batch:
                break

            # 重试提交
            retry_sent = metrics_api.send_batch_updates(current_retry_batch)

            if retry_sent:
                retry_success_count += len(current_retry_batch)
                logger.debug(f"重试成功: {len(current_retry_batch)} 条数据")
            else:
                # 重试仍然失败，加入最终失败列表
                failed_updates.extend(current_retry_batch)
                logger.debug(f"重试失败: {len(current_retry_batch)} 条数据")

            # 重试间隔
            if retry_queue:
                time.sleep(1)

        if retry_success_count > 0:
            logger.info(f"重试成功: {retry_success_count}/{len(retry_updates)} 条数据")

    def _log_failed_updates(self, failed_updates: List[Dict]) -> None:
        """记录失败的更新"""
        logger.warning(f"有 {len(failed_updates)} 条数据提交失败，请检查日志")

        # 输出失败的URL详情
        for i, update in enumerate(failed_updates[:5]):  # 只显示前5个失败的URL
            url = update.get("url", "")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = PrivacyMasker.extract_domain_safely(url)
            logger.warning(f"失败域名 {i+1}: {domain_part}")

        if len(failed_updates) > 5:
            logger.warning(f"还有 {len(failed_updates) - 5} 个失败的URL未显示")

