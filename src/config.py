#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块
管理应用程序的所有配置项
"""

import os
import json
import logging
from typing import List

# 配置日志
logger = logging.getLogger('content_watcher.config')


class ConfigValidator:
    """配置验证器 - 单一职责：验证配置"""

    @staticmethod
    def validate_website_urls(urls: List[str]) -> None:
        """验证网站URL列表"""
        if not urls:
            logger.warning("未配置网站URL列表，将无法执行监控")
            return

        valid_urls = []
        for url in urls:
            url = url.strip()
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'
                valid_urls.append(url)

        if not valid_urls:
            logger.warning("没有有效的网站URL")
        else:
            logger.info(f"已配置 {len(valid_urls)} 个有效网站URL")

    @staticmethod
    def validate_and_filter_api_urls(urls: List[str]) -> List[str]:
        """验证并过滤API URL列表"""
        if not urls:
            logger.warning("未配置关键词API URL列表")
            return []

        valid_urls = []
        for url in urls:
            url = url.strip()
            if url and url.startswith(('http://', 'https://')):
                valid_urls.append(url)
            elif url:
                logger.warning(f"跳过无效的API URL: {url}")

        return valid_urls

    @staticmethod
    def validate_batch_size(batch_size: int) -> int:
        """验证批处理大小配置 - 针对API 500错误优化"""
        if batch_size < 1:
            logger.warning(f"批处理大小不能小于1，已重置为1")
            return 1
        elif batch_size > 3:  # 从10降低到3，减少API压力
            logger.warning(f"批处理大小过大({batch_size})，已重置为3以减少API 500错误")
            return 3
        return batch_size


class Config:
    """应用程序配置类 - 单一职责：管理配置"""

    def __init__(self):
        """初始化配置"""
        # 基础配置
        self.debug = os.environ.get('DEBUG', 'false').lower() == 'true'

        # 数据存储配置
        self.data_file = os.environ.get('DATA_FILE', 'data/sites_data.json')

        # 加密配置
        self.encryption_key = os.environ.get('ENCRYPTION_KEY', '')

        # 网站监控配置
        self.max_concurrent = int(os.environ.get('MAX_CONCURRENT', '3'))

        # 关键词批处理配置 - 针对API 500错误优化
        raw_batch_size = int(os.environ.get('KEYWORDS_BATCH_SIZE', '2'))  # 从4降低到2
        self.keywords_batch_size = ConfigValidator.validate_batch_size(raw_batch_size)
        if raw_batch_size != self.keywords_batch_size:
            logger.info(f"关键词批处理大小已调整: {raw_batch_size} → {self.keywords_batch_size}")

        # 关键词API配置
        keywords_urls_json = os.environ.get('KEYWORDS_API_URLS', '[]')
        try:
            self.keywords_api_urls = json.loads(keywords_urls_json)
        except json.JSONDecodeError:
            logger.warning("KEYWORDS_API_URLS格式无效，使用空列表")
            self.keywords_api_urls = []

        # API健康检查和容错配置 - 新增
        self.api_retry_max = int(os.environ.get('API_RETRY_MAX', '3'))  # 最大重试次数
        self.api_health_check_interval = int(os.environ.get('API_HEALTH_CHECK_INTERVAL', '30'))  # 健康检查间隔
        self.api_circuit_breaker_threshold = int(os.environ.get('API_CIRCUIT_BREAKER_THRESHOLD', '5'))  # 熔断阈值
        self.api_request_interval = float(os.environ.get('API_REQUEST_INTERVAL', '1.0'))  # 请求间隔(秒)

        # 配置超时设置 - 针对API 500错误优化
        self.keyword_query_timeout = int(os.environ.get('KEYWORD_QUERY_TIMEOUT', '60'))  # 从30增加到60秒
        self.site_request_timeout = int(os.environ.get('SITE_REQUEST_TIMEOUT', '20'))  # 网站请求超时(秒)

        # API密钥配置 - 继续使用SITEMAP_API_KEY作为通用API密钥
        self.sitemap_api_key = os.environ.get('SITEMAP_API_KEY', '')

        # 新增关键词指标批量接口配置
        metrics_api_url = os.environ.get('KEYWORD_METRICS_API_URL', '')
        # 与旧 sitemap_api_key 复用同一 API Key
        # 确保使用正确的API URL - 自动拼接批量API路径
        if metrics_api_url:
            # 解析基础URL部分（协议和域名）
            import re
            base_url_match = re.match(r'(https?://[^/]+).*', metrics_api_url)
            if base_url_match:
                base_url = base_url_match.group(1)
                # 使用正确的API路径 - 批量关键词指标API
                self.metrics_batch_api_url = f"{base_url}/api/v1/keyword-metrics/batch"
            else:
                # 如果无法解析，尝试构造批量提交URL
                if metrics_api_url.endswith('/api/v1/keyword-metrics'):
                    self.metrics_batch_api_url = f"{metrics_api_url}/batch"
                elif metrics_api_url.endswith('/api/v1/keyword-metrics/batch'):
                    # 已经是完整路径，直接使用
                    self.metrics_batch_api_url = metrics_api_url
                else:
                    self.metrics_batch_api_url = f"{metrics_api_url}/api/v1/keyword-metrics/batch"
        else:
            self.metrics_batch_api_url = ''

        # 启用标志：同时存在 URL 与 API Key 即视为启用
        self.metrics_api_enabled = bool(self.metrics_batch_api_url and self.sitemap_api_key)

        if self.metrics_api_enabled:
            logger.info("关键词指标批量 API 已启用")
        else:
            logger.warning("关键词指标批量 API 未启用或缺少配置")

        # 解析网站URL列表 - 同时支持WEBSITE_URLS和SITEMAP_URLS以保持向后兼容性
        urls_json = os.environ.get('WEBSITE_URLS', os.environ.get('SITEMAP_URLS', '[]'))
        self.website_urls = json.loads(urls_json)

        # 验证配置
        self.validate_config()

    def validate_config(self) -> None:
        """验证配置是否有效"""
        # 使用验证器验证网站URL列表
        ConfigValidator.validate_website_urls(self.website_urls)

        # 使用验证器验证关键词API URLs
        self.keywords_api_urls = ConfigValidator.validate_and_filter_api_urls(self.keywords_api_urls)
        logger.info(f"关键词API已配置，共 {len(self.keywords_api_urls)} 个有效API地址")
        logger.info(f"关键词批处理大小: {self.keywords_batch_size}")


# 创建全局配置实例
config = Config()
