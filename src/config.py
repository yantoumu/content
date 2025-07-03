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
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(url)
                logger.warning(f"跳过无效的API URL: {masked_url}")

        return valid_urls

    @staticmethod
    def validate_batch_size(batch_size: int) -> int:
        """验证批处理大小配置 - 根据seokey API限制调整为5"""
        if batch_size < 1:
            logger.warning(f"批处理大小不能小于1，已重置为1")
            return 1
        elif batch_size > 5:  # seokey API最大支持5个关键词/请求
            logger.warning(f"批处理大小过大({batch_size})，已重置为5以符合API限制")
            return 5
        return batch_size

    @staticmethod
    def validate_api_key(api_key: str, api_name: str = "API") -> bool:
        """验证API密钥格式和基本有效性
        
        Args:
            api_key: API密钥
            api_name: API名称，用于日志
            
        Returns:
            bool: 密钥是否有效
        """
        if not api_key:
            logger.warning(f"{api_name}密钥为空")
            return False
        
        api_key = api_key.strip()
        
        # 基本格式验证
        if len(api_key) < 8:
            logger.warning(f"{api_name}密钥过短（少于8个字符）")
            return False
        
        if len(api_key) > 256:
            logger.warning(f"{api_name}密钥过长（超过256个字符）")
            return False
        
        # 检查是否包含非法字符（基本ASCII检查）
        if not api_key.isprintable():
            logger.warning(f"{api_name}密钥包含非打印字符")
            return False
        
        # 检查是否为占位符或默认值
        placeholder_patterns = ['your_api_key', 'test', 'demo', 'example', 'placeholder']
        if any(pattern in api_key.lower() for pattern in placeholder_patterns):
            logger.warning(f"{api_name}密钥似乎是占位符或示例值")
            return False
        
        return True


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

        # 网站监控配置 - 优化网站地图并发处理
        self.max_concurrent = int(os.environ.get('MAX_CONCURRENT', '10'))  # 从3提升到10，提高网站地图处理效率

        # 关键词批处理配置 - 根据seokey API限制调整为5
        raw_batch_size = int(os.environ.get('KEYWORDS_BATCH_SIZE', '5'))  # seokey API支持最多5个关键词/请求
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

        # API健康检查和容错配置 - 根据seokey API特性调整
        self.api_retry_max = int(os.environ.get('API_RETRY_MAX', '2'))  # 减少重试次数，避免长时间等待
        self.api_health_check_interval = int(os.environ.get('API_HEALTH_CHECK_INTERVAL', '30'))  # 健康检查间隔
        self.api_circuit_breaker_threshold = int(os.environ.get('API_CIRCUIT_BREAKER_THRESHOLD', '3'))  # 降低熔断阈值
        self.api_request_interval = float(os.environ.get('API_REQUEST_INTERVAL', '2.0'))  # 增加请求间隔到2秒

        # 配置超时设置 - 根据seokey API响应时间调整
        self.keyword_query_timeout = int(os.environ.get('KEYWORD_QUERY_TIMEOUT', '80'))  # API查询超时80秒，考虑70秒响应时间
        self.site_request_timeout = int(os.environ.get('SITE_REQUEST_TIMEOUT', '20'))  # 网站请求超时20秒
        self.queue_timeout = int(os.environ.get('QUEUE_TIMEOUT', '300'))  # 队列处理超时300秒，考虑长响应时间

        # 性能优化模式配置
        self.enable_performance_mode = os.environ.get('ENABLE_PERFORMANCE_MODE', 'true').lower() == 'true'

        # 移除首次运行分批处理配置 - 统一使用全量处理模式
        logger.info("✅ 系统启用全量处理模式: 处理sitemap中的所有URL")

        # 关键词指标API批量提交配置
        self.metrics_api_max_batch_size = int(os.environ.get('METRICS_API_MAX_BATCH_SIZE', '200'))  # 批量提交最大条数

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

        # 启用标志：同时存在 URL 与有效 API Key 即视为启用
        api_key_valid = ConfigValidator.validate_api_key(self.sitemap_api_key, "SITEMAP_API")
        self.metrics_api_enabled = bool(self.metrics_batch_api_url and api_key_valid)

        if self.metrics_api_enabled:
            logger.info("关键词指标批量 API 已启用")
        else:
            if not self.metrics_batch_api_url:
                logger.warning("关键词指标批量 API 未启用：缺少API URL配置")
            elif not api_key_valid:
                logger.warning("关键词指标批量 API 未启用：API密钥无效或缺失")
            else:
                logger.warning("关键词指标批量 API 未启用或缺少配置")

        # 解析网站URL列表 - 优先使用WEBSITE_URLS，保持向后兼容性
        urls_json = os.environ.get('WEBSITE_URLS', os.environ.get('SITEMAP_URLS', '[]'))
        self.website_urls = json.loads(urls_json)

        # 如果同时设置了两个环境变量，发出警告
        if os.environ.get('WEBSITE_URLS') and os.environ.get('SITEMAP_URLS'):
            logger.warning("同时检测到WEBSITE_URLS和SITEMAP_URLS环境变量，优先使用WEBSITE_URLS")

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
