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

        # 关键词API配置
        self.keywords_api_url = os.environ.get('KEYWORDS_API_URL', '')

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
        # 验证网站URL列表
        if not self.website_urls:
            logger.error("未提供网站URL列表")
            raise ValueError("WEBSITE_URLS必须是有效的JSON数组")

        # 移除 Telegram 配置验证

        # 检查网站地图API配置 - 只使用批量提交
        self.sitemap_api_enabled = bool(self.sitemap_batch_api_url and self.sitemap_api_key)
        if not self.sitemap_api_enabled:
            logger.warning("未设置网站地图API URL或API Key，将不会发送更新到API")
        else:
            logger.info("网站地图API已启用")

        # 验证关键词API URL
        if not self.keywords_api_url:
            logger.error("未设置关键词API URL")
            raise ValueError("KEYWORDS_API_URL是必需的配置项")
        else:
            logger.info("关键词API已配置")

# 创建全局配置实例
config = Config()
