#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
处理环境变量和配置验证
"""

import json
import logging
import os

# 配置日志 - 将默认级别设置为WARNING，只输出警告和错误
logging.basicConfig(
    level=logging.WARNING,  # 只输出警告和错误
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 设置第三方库的日志级别，减少日志输出
# 将urllib3的日志级别设置为WARNING，只显示警告和错误
logging.getLogger('urllib3').setLevel(logging.WARNING)

# 为关键模块设置日志级别
# 允许核心模块输出信息级别的日志
logging.getLogger('content_watcher.core').setLevel(logging.INFO)

logger = logging.getLogger('content_watcher.config')


class ConfigValidator:
    """配置验证器 - 符合单一职责原则"""
    
    @staticmethod
    def validate_website_urls(urls: list) -> None:
        """验证网站URL列表"""
        if not urls:
            logger.error("未提供网站URL列表")
            raise ValueError("WEBSITE_URLS必须是有效的JSON数组")
    
    @staticmethod
    def validate_and_filter_api_urls(urls: list) -> list:
        """验证并过滤API URL列表"""
        if not urls or not any(urls):
            logger.error("未设置关键词API URL")
            raise ValueError("KEYWORDS_API_URL或KEYWORDS_API_URLS是必需的配置项")
        
        # 过滤和验证URL
        valid_urls = []
        seen_urls = set()
        for url in urls:
            if not url or not url.strip():
                continue
            url = url.strip()
            # 基础URL格式验证
            if not (url.startswith('http://') or url.startswith('https://')):
                logger.warning(f"跳过无效URL格式: {url}")
                continue
            # 去重
            if url in seen_urls:
                logger.warning(f"跳过重复URL: {url}")
                continue
            seen_urls.add(url)
            valid_urls.append(url)
        
        if not valid_urls:
            logger.error("没有有效的关键词API URL")
            raise ValueError("所有KEYWORDS_API_URL都无效")
        
        return valid_urls


class Config:
    """配置管理类，处理环境变量和配置验证"""

    def __init__(self):
        """初始化配置"""
        # 是否在测试模式下运行
        self.test_mode = False

        # 首次运行时最多报告的更新数量 - 不限制数量
        self.max_first_run_updates = 0  # 0表示不限制

        # 获取密钥
        self.encryption_key_str = os.environ.get('ENCRYPTION_KEY', '')

        # 移除 Telegram 相关配置

        # 关键词API配置 - 支持多个API地址
        keywords_api_urls_str = os.environ.get('KEYWORDS_API_URLS', '')
        if keywords_api_urls_str:
            try:
                parsed_urls = json.loads(keywords_api_urls_str)
                if not isinstance(parsed_urls, list):
                    logger.error("KEYWORDS_API_URLS必须是JSON数组格式")
                    self.keywords_api_urls = []
                else:
                    self.keywords_api_urls = parsed_urls
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"KEYWORDS_API_URLS JSON解析失败: {e}")
                self.keywords_api_urls = []
        else:
            # 向后兼容单API配置
            single_url = os.environ.get('KEYWORDS_API_URL', '')
            self.keywords_api_urls = [single_url] if single_url else []

        # 网站地图更新API相关配置
        raw_api_url = os.environ.get('SITEMAP_API_URL', '')
        # 确保使用正确的API URL
        if raw_api_url:
            # 解析基础URL部分（协议和域名）
            import re
            base_url_match = re.match(r'(https?://[^/]+).*', raw_api_url)
            if base_url_match:
                base_url = base_url_match.group(1)
                # 使用正确的API路径 - 只使用批量提交
                self.sitemap_batch_api_url = f"{base_url}/api/v1/sitemap-updates/batch"  # 批量提交的API
            else:
                # 如果无法解析，尝试构造批量提交URL
                if raw_api_url.endswith('/api/v1/sitemap-update'):
                    self.sitemap_batch_api_url = raw_api_url.replace('/api/v1/sitemap-update', '/api/v1/sitemap-updates/batch')
                elif raw_api_url.endswith('/api/v1/sitemap-updates'):
                    self.sitemap_batch_api_url = f"{raw_api_url}/batch"
                else:
                    self.sitemap_batch_api_url = f"{raw_api_url}/api/v1/sitemap-updates/batch"
        else:
            self.sitemap_batch_api_url = ''

        self.sitemap_api_key = os.environ.get('SITEMAP_API_KEY', '')
        self.sitemap_api_enabled = False

        # 解析网站URL列表 - 同时支持WEBSITE_URLS和SITEMAP_URLS以保持向后兼容性
        urls_json = os.environ.get('WEBSITE_URLS', os.environ.get('SITEMAP_URLS', '[]'))
        self.website_urls = json.loads(urls_json)

        # 验证配置
        self.validate_config()

    def validate_config(self) -> None:
        """验证配置是否有效"""
        # 使用验证器验证网站URL列表
        ConfigValidator.validate_website_urls(self.website_urls)

        # 检查网站地图API配置 - 只使用批量提交
        self.sitemap_api_enabled = bool(self.sitemap_batch_api_url and self.sitemap_api_key)
        if not self.sitemap_api_enabled:
            logger.warning("未设置网站地图API URL或API Key，将不会发送更新到API")
        else:
            logger.info("网站地图API已启用")

        # 使用验证器验证关键词API URLs
        self.keywords_api_urls = ConfigValidator.validate_and_filter_api_urls(self.keywords_api_urls)
        logger.info(f"关键词API已配置，共 {len(self.keywords_api_urls)} 个有效API地址")

# 创建全局配置实例
config = Config()
