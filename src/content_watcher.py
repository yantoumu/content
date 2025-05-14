#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容监控模块
处理网站内容更新监控的核心逻辑
"""

import base64
import datetime
import json
import logging
import random
import time
from typing import List

from src.config import config
from src.data_manager import data_manager
from src.encryption import encryptor
from src.keyword_api_client import keyword_api_client
from src.keyword_extractor import keyword_extractor
from src.sitemap_api import sitemap_api
from src.sitemap_parser import sitemap_parser
# 移除 Telegram 通知和消息格式化模块

# 配置日志
logger = logging.getLogger('content_watcher.core')

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

    def process_site(self, site_url: str, site_index: int) -> List[str]:
        """处理单个网站，返回今日更新的URL列表"""
        site_id = data_manager.get_site_identifier(site_url)
        logger.info(f"正在处理网站 {site_index+1} ({site_id})")

        # 下载和解析网站地图
        sitemap_data = sitemap_parser.download_and_parse_sitemap(site_url, site_id)
        if not sitemap_data:
            logger.warning(f"网站 {site_id} 未返回有效数据")
            return []

        # 解密上一次的数据用于对比
        previous_urls, previous_keywords_data = data_manager.get_previous_urls(site_id)

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

        # 如果没有变化，直接返回空列表
        if not updated_urls:
            logger.info(f"网站 {site_id} 没有发现更新")

            # 更新储存的数据
            data_manager.update_site_data(site_id, new_encrypted_data)

            return []

        # 提取更新URL的关键词，并过滤掉没有有效关键词的URL
        url_keywords_map = {}
        valid_urls = []
        for url in updated_urls:
            keyword = keyword_extractor.extract_keywords_from_url(url)
            # 只处理有效关键词的URL
            if keyword:  # 如果关键词不为空
                url_keywords_map[url] = keyword
                valid_urls.append(url)
            else:
                # 不输出跳过URL的日志，减少日志输出
                pass  # 使用pass语句作为空操作

        # 更新URL列表，只保留有效关键词的URL
        updated_urls = valid_urls
        logger.info(f"过滤后的有效URL数量: {len(updated_urls)}")

        # 如果是首次运行且URL数量很多，限制通知的URL数量
        if is_first_run and len(updated_urls) > self.max_first_run_updates:
            logger.info(f"首次运行，更新URL数量({len(updated_urls)})超过限制({self.max_first_run_updates})，将只发送部分更新")
            # 随机选择一些URL作为示例
            sample_urls = random.sample(updated_urls, self.max_first_run_updates)
            updated_urls = sample_urls
            # 更新关键词映射
            url_keywords_map = {url: url_keywords_map[url] for url in updated_urls if url in url_keywords_map}

        # 移除构建通知消息的代码
        logger.info(f"共发现 {len(updated_urls)} 个更新")

        # 批量查询关键词信息
        keyword_results = {}
        keywords_data_to_store = {}  # 用于存储到 GitHub 的关键词数据

        # 始终查询关键词信息，无论是否首次运行
        if url_keywords_map:
            try:
                # 获取所有关键词列表
                keywords_list = list(url_keywords_map.values())
                # 批量查询关键词
                raw_keyword_data = keyword_api_client.batch_query_keywords(keywords_list)

                # 将关键词数据转换为URL到API响应的映射，并准备存储数据
                for url, keyword in url_keywords_map.items():
                    if keyword in raw_keyword_data:
                        # 获取原始关键词数据
                        original_keyword_data = raw_keyword_data[keyword]

                        # 为每个URL创建一个包含原始关键词数据的结果
                        keyword_results[url] = {
                            'status': 'success',
                            'geo_target': '全球',
                            'total_results': 1,
                            'data': [original_keyword_data]  # 只添加原始关键词数据
                        }

                        # 只存储当前关键词的数据，不再存储高流量关键词
                        keywords_data_to_store[url] = {
                            'keyword': keyword,
                            'data': original_keyword_data
                        }
            except Exception as e:
                logger.error(f"批量查询关键词信息时出错")
                for keyword in keywords_list:
                    logger.error(f"关键词: {keyword}")

        # 格式化详细更新信息，只包含原始关键词数据
        # 注释掉这部分代码，因为我们不再需要格式化消息
        # message_formatter.format_detailed_updates(message_parts, updated_urls, url_keywords_map, keyword_results)

        # 移除 Telegram 通知代码

        # 将更新数据发送到网站地图API
        if config.sitemap_api_enabled and updated_urls:
            try:
                # 准备批量提交数据
                batch_updates = []

                for url in updated_urls:
                    # 获取URL的关键词
                    keyword = url_keywords_map.get(url, "")
                    keywords_list = [keyword] if keyword else []
                    # 获取关键词数据
                    api_data = keyword_results.get(url, {})
                    # 准备单条更新数据
                    try:
                        # 记录关键词数据的结构
                        # 仅记录关键词数量，不记录具体内容
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
                        logger.error(f"准备URL数据时出错: {url}")

                # 如果有数据要提交
                if batch_updates:
                    # 使用队列来管理批量提交
                    from collections import deque
                    import time
                    import concurrent.futures

                    # 创建队列
                    update_queue = deque(batch_updates)
                    max_batch_size = sitemap_api.max_batch_size
                    total_updates = len(batch_updates)
                    processed_updates = 0
                    failed_updates = []  # 存储失败的更新

                    # 判断是否使用并行处理
                    use_parallel = len(batch_updates) > max_batch_size

                    logger.info(f"开始批量提交处理，共 {total_updates} 条数据，每批 {max_batch_size} 条")

                    # 使用批量提交逻辑
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
                                logger.debug(f"批量提交失败的数据 {i+1}/{len(current_batch)}: URL={url}, 关键词={keywords}, 趋势数据项数={len(keyword_trends)}")

                        # 批次间添加小延迟，避免请求过快
                        if update_queue:  # 如果还有数据要处理
                            time.sleep(1)  # 等待1秒

                    # 最终统计
                    success_count = total_updates - len(failed_updates)

                    # 只在有失败或全部成功时输出统计信息
                    if failed_updates:
                        logger.warning(f"批量提交完成，成功: {success_count}/{total_updates}, 失败: {len(failed_updates)}")
                        logger.warning(f"有 {len(failed_updates)} 条数据提交失败，请检查日志")

                        # 输出失败的URL详情
                        for i, update in enumerate(failed_updates[:5]):  # 只显示前5个失败的URL
                            url = update.get("new_url", "")
                            logger.warning(f"失败URL {i+1}: {url}")

                        if len(failed_updates) > 5:
                            logger.warning(f"还有 {len(failed_updates) - 5} 个失败的URL未显示")
                    elif total_updates > 0:  # 只在有数据提交时输出
                        logger.info(f"批量提交完成，所有 {total_updates} 条数据提交成功")
            except Exception as e:
                logger.error(f"发送数据到API时出错: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")

        # 加密并更新关键词数据
        for url in updated_urls:
            if url in keywords_data_to_store:
                # 在找到URL数据的索引
                url_encrypted = encryptor.encrypt_url(url)
                for i, item in enumerate(new_encrypted_data):
                    if item.get('encrypted_url') == url_encrypted:
                        # 加密关键词数据
                        keywords_json = json.dumps(keywords_data_to_store[url])
                        encrypted_keywords = encryptor.encrypt_data(keywords_json.encode('utf-8'))
                        new_encrypted_data[i]['keywords_data'] = base64.b64encode(encrypted_keywords).decode('utf-8')
                        break

        # 更新数据存储
        data_manager.update_site_data(site_id, new_encrypted_data)

        # 记录统计信息
        logger.info(f"网站 {site_id} 统计: 新URL数量: {new_url_count}, 更新URL数量: {updated_url_count}, 总计: {len(updated_urls)}")

        return updated_urls

    def run(self) -> None:
        """执行监控流程"""
        logger.info("开始执行内容监控...")

        all_updates = {}

        # 判断是否使用并行处理
        use_parallel = len(config.website_urls) > 1

        if use_parallel:
            # 并行处理多个网站
            import concurrent.futures

            # 创建线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(config.website_urls), 5)) as executor:
                # 提交所有网站处理任务
                future_to_site = {executor.submit(self._process_site_wrapper, website_url, i): (website_url, i)
                                  for i, website_url in enumerate(config.website_urls)}

                # 处理结果
                for future in concurrent.futures.as_completed(future_to_site):
                    website_url, i = future_to_site[future]
                    try:
                        updated_urls = future.result()
                        if updated_urls:
                            site_id = data_manager.get_site_identifier(website_url)
                            all_updates[site_id] = updated_urls
                    except Exception as e:
                        logger.error(f"并行处理网站 {i+1} 时出错: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
        else:
            # 串行处理网站
            for i, website_url in enumerate(config.website_urls):
                try:
                    # 处理每个网站
                    updated_urls = self.process_site(website_url, i)

                    if updated_urls:
                        site_id = data_manager.get_site_identifier(website_url)
                        all_updates[site_id] = updated_urls
                except Exception as e:
                    logger.error(f"处理网站时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

        if not all_updates:
            logger.info("没有检测到内容更新")
            # 即使没有更新，也要关闭会话
            self._close_api_clients()
            return

        logger.info(f"监控完成，共有 {len(all_updates)} 个网站有更新")
        total_updates = sum(len(urls) for urls in all_updates.values())
        logger.info(f"总共 {total_updates} 个URL已更新")

        # 关闭所有API客户端会话
        self._close_api_clients()

    def _process_site_wrapper(self, website_url: str, site_index: int) -> List[str]:
        """处理网站的包装方法，用于并行处理

        Args:
            website_url: 网站URL
            site_index: 网站索引

        Returns:
            更新的URL列表
        """
        try:
            logger.info(f"并行处理网站 {site_index+1} ({website_url})")
            return self.process_site(website_url, site_index)
        except Exception as e:
            logger.error(f"并行处理网站 {site_index+1} 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _close_api_clients(self):
        """关闭所有API客户端会话"""
        try:
            # 关闭关键词API客户端会话
            if hasattr(keyword_api_client, 'close'):
                keyword_api_client.close()
                logger.debug("关闭关键词API客户端会话")

            # 关闭网站地图解析器会话
            if hasattr(sitemap_parser, 'close'):
                sitemap_parser.close()
                logger.debug("关闭网站地图解析器会话")

            # 关闭其他可能使用会话的客户端
            # 如果将来有其他使用session的客户端，可以在这里添加
        except Exception as e:
            logger.warning(f"关闭API客户端会话时出错: {e}")
