#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多API关键词查询管理器
统一管理和协调多个关键词API的查询请求
"""

import logging
import threading
from typing import Dict, List, Any

from src.config import config
from src.keyword_api import KeywordAPI
from src.api_health_monitor import api_health_monitor
from src.api_scheduler_config import APISchedulerConfig
from src.thread_resource_manager import ThreadResourceManager
from src.keyword_query_strategies import DirectParallelStrategy, QueueSchedulerStrategy

# 配置日志
logger = logging.getLogger('content_watcher.multi_api_manager')


class MultiAPIKeywordManager:
    """多API关键词查询管理器，支持智能队列调度"""

    def __init__(self, scheduler_config: APISchedulerConfig = None):
        """初始化多API管理器"""
        self.logger = logging.getLogger('content_watcher.keyword_api_multi')
        self._api_clients = {}  # 缓存API客户端实例
        self._api_clients_lock = threading.RLock()  # 线程安全锁
        
        # 使用配置对象而非硬编码
        self.config = scheduler_config or APISchedulerConfig()
        self._workers_initialized = False
        
        # 初始化线程资源管理器
        self.thread_manager = ThreadResourceManager(
            max_workers=self.config.max_workers,
            timeout=self.config.queue_timeout
        )
        
        # 记录实际使用的批处理大小
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"多API管理器初始化，批处理大小: {self.config.batch_size}")

    def _ensure_workers_initialized(self):
        """确保工作线程数已正确初始化"""
        if not self._workers_initialized:
            api_count = len(config.keywords_api_urls) if config.keywords_api_urls else 1
            self.max_queue_workers = max(1, min(self.config.max_workers, api_count))
            self._workers_initialized = True
            self.logger.debug(f"初始化队列工作线程数: {self.max_queue_workers}")

    def batch_query_keywords_parallel(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """并发查询关键词信息，使用多个API地址
        
        Args:
            keywords_list: 关键词列表
            max_retries: 最大重试次数
            
        Returns:
            关键词数据字典，键为关键词，值为API返回的数据
        """
        if not keywords_list:
            return {}
        
        try:
            # 防护检查：确保有可用的API地址
            if not config.keywords_api_urls:
                self.logger.error("没有配置可用的关键词API地址，跳过关键词查询")
                return {}

            # 根据API数量决定使用单API还是多API模式
            if len(config.keywords_api_urls) <= 1:
                return self._handle_single_api_mode(keywords_list, max_retries)

            # 选择查询策略
            return self._select_and_execute_strategy(keywords_list, max_retries)

        except Exception as e:
            self.logger.error(f"并发关键词查询失败: {e}")
            return {}

    def _handle_single_api_mode(self, keywords_list: List[str], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """处理单API模式"""
        if len(config.keywords_api_urls) == 1:
            api_url = config.keywords_api_urls[0]
            from src.privacy_utils import PrivacyMasker
            masked_url = PrivacyMasker.mask_api_url(api_url)
            self.logger.info(f"使用单API模式: {masked_url}")
            api = KeywordAPI(api_url)
            return api.batch_query_keywords(keywords_list, max_retries)
        else:
            self.logger.error("没有配置任何关键词API地址，跳过关键词查询")
            return {}

    def _select_and_execute_strategy(self, keywords_list: List[str], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """选择并执行查询策略"""
        # 基于性能测试结果，优先使用串行处理模式
        self.logger.info(f"使用优化串行处理模式: {len(keywords_list)} 个关键词")

        # 尝试使用优化的串行处理器
        try:
            from src.optimized_serial_processor import get_optimized_processor
            processor = get_optimized_processor()
            result = processor.process_keywords_optimized(keywords_list)
            return result.get('results', {})

        except ImportError:
            self.logger.warning("优化串行处理器不可用，降级到原有模式")
            return self._fallback_strategy(keywords_list, max_retries)

    def _fallback_strategy(self, keywords_list: List[str], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """降级策略：根据批量大小选择合适的策略"""
        # 降级策略：大批量使用队列，小批量使用并发
        if len(keywords_list) > 100:
            self.logger.info(f"降级到队列调度模式: {len(keywords_list)} 个关键词")
            strategy = QueueSchedulerStrategy(self._api_clients, self.logger, self.config)
            return strategy.execute_query(keywords_list, max_retries)
        else:
            self.logger.info(f"降级到直接并发模式: {len(keywords_list)} 个关键词")
            strategy = DirectParallelStrategy(self._api_clients, self.logger)
            return strategy.execute_query(keywords_list, max_retries)

    def _get_api_client(self, api_url: str) -> KeywordAPI:
        """获取或创建API客户端实例（线程安全）"""
        with self._api_clients_lock:
            if api_url not in self._api_clients:
                self._api_clients[api_url] = KeywordAPI(api_url)
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(api_url)
                self.logger.debug(f"创建新的API客户端: {masked_url}")
            return self._api_clients[api_url]

    def _get_adaptive_batch_size(self, api_url: str) -> int:
        """根据API健康状态获取自适应批次大小 - 根据seokey API限制

        Args:
            api_url: API地址

        Returns:
            推荐的批次大小（最大为5）
        """
        # 根据seokey API限制，最大支持5个关键词/请求
        # 可以根据API健康状态动态调整
        if api_health_monitor.is_api_available(api_url):
            health_summary = api_health_monitor.get_health_summary().get(api_url, {})
            success_rate = health_summary.get('success_rate', 1.0)

            if success_rate > 0.9:
                return 5  # 健康状态良好，使用最大批次
            elif success_rate > 0.7:
                return 4  # 健康状态一般，减少批次
            else:
                return 3  # 健康状态较差，进一步减少批次
        else:
            return 3  # API不可用时使用较小批次

    def _handle_api_failure(self, failed_keywords: List[str], failed_api_index: int, max_retries: int) -> Dict[str, Dict[str, Any]]:
        """处理API失败，尝试用其他API重新查询"""
        if len(config.keywords_api_urls) == 1:
            # 只有一个API，记录失败但不创建虚假数据
            self.logger.warning(f"单API模式下查询失败，跳过 {len(failed_keywords)} 个关键词")
            return {}

        # 尝试用其他API查询
        for api_index, api_url in enumerate(config.keywords_api_urls):
            if api_index != failed_api_index:
                try:
                    api_client = self._get_api_client(api_url)
                    result = api_client.batch_query_keywords(failed_keywords, max_retries)
                    if result:  # 确保有有效结果
                        self.logger.info(f"故障转移成功，API {api_index} 处理了 {len(result)} 个关键词")
                        return result
                except Exception as e:
                    self.logger.warning(f"故障转移到API {api_index} 失败: {e}")
                    continue

        # 所有API都失败，记录失败但不创建虚假数据
        self.logger.warning(f"所有API都失败，跳过 {len(failed_keywords)} 个关键词")
        return {}

    def close(self):
        """关闭所有API客户端连接和线程资源"""
        # 优雅关闭线程资源
        try:
            self.thread_manager.shutdown_gracefully()
        except Exception as e:
            self.logger.warning(f"关闭线程资源时出错: {e}")
        
        # 关闭API客户端连接
        with self._api_clients_lock:
            for api_url, client in self._api_clients.items():
                try:
                    if hasattr(client, 'close'):
                        client.close()
                        from src.privacy_utils import PrivacyMasker
                        masked_url = PrivacyMasker.mask_api_url(api_url)
                        self.logger.debug(f"关闭API客户端连接: {masked_url}")
                except Exception as e:
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.warning(f"关闭API客户端连接时出错 {masked_url}: {e}")
            self._api_clients.clear()

    def __del__(self):
        """析构函数，确保资源清理"""
        try:
            self.close()
        except Exception:
            # 析构函数中不应抛出异常
            pass


# 创建全局多API管理器实例
multi_api_manager = MultiAPIKeywordManager()