#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容监控模块
处理网站内容更新监控的核心逻辑
"""

import logging
from typing import List

from src.config import config
from src.keyword_api import keyword_api
from src.keyword_api_multi import multi_api_manager
from src.site_data_collector import SiteDataCollector
from src.site_update_processor import SiteUpdateProcessor
from src.sitemap_parser import sitemap_parser
# 移除 Telegram 通知和消息格式化模块

# 配置日志
logger = logging.getLogger('content_watcher.core')

class ContentWatcher:
    """监控多个网站内容更新并发送通知"""

    def __init__(self, test_mode=False, max_first_run_updates=0):
        """初始化监控器

        Args:
            test_mode: 是否在测试模式下运行
            max_first_run_updates: 首次运行时最多报告的更新数量，0表示不限制
        """
        # 是否在测试模式下运行
        self.test_mode = test_mode

        # 使用专门的数据收集器和更新处理器
        self.site_data_collector = SiteDataCollector(max_first_run_updates)
        self.site_update_processor = SiteUpdateProcessor()

    # 已删除已弃用的process_site方法 - 使用_collect_site_data和_process_site_updates替代

    def run(self) -> None:
        """执行监控流程

        实现全局关键词收集和去重，避免对相同关键词的重复请求
        """
        logger.info("开始执行内容监控...")

        # 第一阶段：收集所有网站的更新URL和关键词
        all_site_data = {}
        global_keywords = set()  # 用于全局关键词去重
        site_url_keywords_map = {}  # 存储每个网站的URL到关键词的映射

        # 判断是否使用并行处理
        use_parallel = len(config.website_urls) > 1

        # 第一阶段：收集阶段
        logger.info("第一阶段：收集所有网站的更新URL和关键词")
        if use_parallel:
            # 并行处理多个网站 - 仅收集阶段
            import concurrent.futures

            # 创建线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(config.website_urls), 5)) as executor:
                # 提交所有网站处理任务
                future_to_site = {executor.submit(self.site_data_collector.collect_site_data, website_url, i): (website_url, i)
                                  for i, website_url in enumerate(config.website_urls)}

                # 处理结果
                for future in concurrent.futures.as_completed(future_to_site):
                    website_url, i = future_to_site[future]
                    try:
                        site_id, site_data = future.result()
                        if site_data and site_data.get('updated_urls'):
                            all_site_data[site_id] = site_data
                            # 收集全局关键词
                            for keyword in site_data.get('keywords', []):
                                if keyword:  # 确保关键词不为空
                                    global_keywords.add(keyword)
                            # 存储URL到关键词的映射
                            site_url_keywords_map[site_id] = site_data.get('url_keywords_map', {})
                    except Exception as e:
                        logger.error(f"并行处理网站 {i+1} 时出错: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
        else:
            # 串行处理网站 - 仅收集阶段
            for i, website_url in enumerate(config.website_urls):
                try:
                    site_id, site_data = self.site_data_collector.collect_site_data(website_url, i)
                    if site_data and site_data.get('updated_urls'):
                        all_site_data[site_id] = site_data
                        # 收集全局关键词
                        for keyword in site_data.get('keywords', []):
                            if keyword:  # 确保关键词不为空
                                global_keywords.add(keyword)
                        # 存储URL到关键词的映射
                        site_url_keywords_map[site_id] = site_data.get('url_keywords_map', {})
                except Exception as e:
                    logger.error(f"处理网站时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

        if not all_site_data:
            logger.info("没有检测到内容更新")
            # 即使没有更新，也要关闭会话
            self._close_api_clients()
            return

        # 第二阶段：全局关键词查询
        logger.info(f"第二阶段：全局关键词查询，共 {len(global_keywords)} 个唯一关键词")
        global_keyword_list = list(global_keywords)
        global_keyword_data = {}

        if global_keyword_list:
            # 批量查询所有唯一关键词 - 使用多API并发查询
            global_keyword_data = multi_api_manager.batch_query_keywords_parallel(global_keyword_list)
            logger.info(f"成功查询 {len(global_keyword_data)} 个关键词数据")

        # 第三阶段：处理每个网站的更新
        logger.info("第三阶段：处理每个网站的更新")
        all_updates = {}

        for site_id, site_data in all_site_data.items():
            try:
                # 处理网站更新
                updated_urls = self.site_update_processor.process_site_updates(
                    site_id,
                    site_data,
                    site_url_keywords_map.get(site_id, {}),
                    global_keyword_data
                )

                if updated_urls:
                    all_updates[site_id] = updated_urls
            except Exception as e:
                logger.error(f"处理网站 {site_id} 更新时出错: {e}")
                import traceback
                logger.error(traceback.format_exc())

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
            # 首先收集网站数据
            site_id, site_data = self.site_data_collector.collect_site_data(website_url, site_index)
            if not site_data or not site_data.get('updated_urls'):
                return []

            # 然后处理网站更新
            # 注意：这里没有全局关键词去重，因为这是并行处理的旧方法
            # 建议使用run方法中的新流程而不是这个包装方法
            url_keywords_map = site_data.get('url_keywords_map', {})
            keywords_list = list(set(url_keywords_map.values()))
            keyword_data = {}

            if keywords_list:
                # 批量查询关键词 - 使用多API并发查询
                keyword_data = multi_api_manager.batch_query_keywords_parallel(keywords_list)

            # 处理网站更新
            return self.site_update_processor.process_site_updates(site_id, site_data, url_keywords_map, keyword_data)
        except Exception as e:
            logger.error(f"并行处理网站 {site_index+1} 时出错")
            import traceback
            logger.error(traceback.format_exc())
            return []

    # 已删除重复的_collect_site_data方法 - 使用SiteDataCollector替代

    # 已删除重复的_process_site_updates方法 - 使用SiteUpdateProcessor替代

    def _close_api_clients(self):
        """关闭所有API客户端会话"""
        try:
            # 关闭关键词API客户端会话
            if hasattr(keyword_api, 'session') and hasattr(keyword_api.session, 'close'):
                keyword_api.session.close()
                logger.debug("关闭关键词API客户端会话")

            # 关闭多API管理器中的客户端连接
            if hasattr(multi_api_manager, 'close'):
                multi_api_manager.close()
                logger.debug("关闭多API管理器客户端连接")

            # 关闭网站地图解析器会话
            if hasattr(sitemap_parser, 'session') and hasattr(sitemap_parser.session, 'close'):
                sitemap_parser.session.close()
                logger.debug("关闭网站地图解析器会话")

            # 关闭其他可能使用会话的客户端
            # 如果将来有其他使用session的客户端，可以在这里添加
        except Exception as e:
            logger.warning(f"关闭API客户端会话时出错: {e}")
