#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API调度器配置模块
处理多API调度的配置管理和超时计算
"""

import logging
from src.config import config

# 配置日志
logger = logging.getLogger('content_watcher.api_scheduler_config')


class APISchedulerConfig:
    """API调度器配置类 - 单一职责：管理调度配置和超时计算"""

    def __init__(self, batch_size: int = None, batch_interval: float = None,
                 api_safe_rate: int = 1, max_workers: int = 2):
        """初始化调度器配置
        
        Args:
            batch_size: 批处理大小
            batch_interval: 批次间隔时间
            api_safe_rate: API安全频率（请求/秒）
            max_workers: 最大工作线程数
        """
        # 使用配置中的批处理大小，如果没有指定则使用配置默认值
        self.batch_size = batch_size if batch_size is not None else config.keywords_batch_size
        self.batch_interval = batch_interval if batch_interval is not None else config.api_request_interval
        self.api_safe_rate = api_safe_rate  # 每个API安全频率（请求/秒）
        self.max_workers = max_workers  # 最大工作线程数
        
        # 动态计算队列超时时间
        base_timeout = getattr(config, 'queue_timeout', 300)
        self.queue_timeout = self._calculate_dynamic_timeout(base_timeout)

        # 根据seokey API特性优化配置
        if hasattr(config, 'enable_performance_mode') and config.enable_performance_mode:
            logger.info("启用seokey API优化模式")
            self.batch_size = 5  # seokey API支持最多5个关键词/请求
            self.batch_interval = max(self.batch_interval, 2.0)  # 确保至少2秒间隔
            self.max_workers = min(max_workers, 2)  # seokey API限制最多2个并发线程
            # 为seokey API计算更合理的超时时间
            self.queue_timeout = self._calculate_seokey_timeout()
            logger.info(f"seokey优化配置: batch_size={self.batch_size}, interval={self.batch_interval}, workers={self.max_workers}, timeout={self.queue_timeout}s")

        # 验证配置合理性 - 根据seokey API限制
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置参数的合理性"""
        if self.batch_size < 1:
            logger.warning(f"批处理大小不合理({self.batch_size})，已重置为1")
            self.batch_size = 1
        elif self.batch_size > 5:  # seokey API最大支持5个关键词/请求
            logger.warning(f"批处理大小过大({self.batch_size})，已重置为5")
            self.batch_size = 5

    def _calculate_dynamic_timeout(self, base_timeout: int) -> int:
        """动态计算队列超时时间
        
        Args:
            base_timeout: 基础超时时间
            
        Returns:
            int: 调整后的超时时间
        """
        # 根据批次大小和间隔计算预期处理时间
        estimated_batch_time = self.batch_interval + 30  # 30秒缓冲时间
        
        # 考虑重试次数（最多2次重试）
        max_retry_time = estimated_batch_time * 3
        
        # 动态超时 = 基础超时 + 预估处理时间
        dynamic_timeout = max(base_timeout, max_retry_time)
        
        # 设置合理的上限（最多30分钟）
        return min(dynamic_timeout, 1800)

    def _calculate_seokey_timeout(self) -> int:
        """为seokey API计算专用超时时间
        
        Returns:
            int: seokey API专用超时时间
        """
        # seokey API响应时间约70秒
        single_request_time = 70
        
        # 考虑批次间隔和重试
        batch_processing_time = single_request_time + self.batch_interval
        
        # 为每个批次预留充足时间（包括3次重试）
        max_batch_time = batch_processing_time * 4  # 4倍缓冲
        
        # 最少5分钟，最多20分钟
        return max(300, min(max_batch_time, 1200))

    def get_config_summary(self) -> dict:
        """获取配置摘要信息
        
        Returns:
            dict: 配置摘要
        """
        return {
            'batch_size': self.batch_size,
            'batch_interval': self.batch_interval,
            'max_workers': self.max_workers,
            'queue_timeout': self.queue_timeout,
            'api_safe_rate': self.api_safe_rate
        }