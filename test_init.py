#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ContentWatcher初始化和调用链
"""

import os
import logging

# 设置环境变量
os.environ['WEBSITE_URLS'] = '["https://example.com/sitemap.xml"]'
os.environ['ENCRYPTION_KEY'] = "1234567890123456789012345678901234567890123456789012345678901234"
os.environ['KEYWORDS_API_URL'] = "https://api.example.com/keywords/"

# 配置日志
logging.basicConfig(level=logging.INFO)

def test_initialization():
    """测试初始化和调用链"""
    try:
        from src.content_watcher import ContentWatcher
        
        watcher = ContentWatcher(test_mode=True, max_first_run_updates=1)
        print('✅ ContentWatcher完全初始化成功')
        
        # 检查各个组件
        print('📦 检查组件：')
        print(f'  - SiteDataCollector: {type(watcher.site_data_collector).__name__}')
        print(f'  - SiteUpdateProcessor: {type(watcher.site_update_processor).__name__}')
        
        # 检查配置
        from src.config import config
        print(f'  - 网站数量: {len(config.website_urls)}')
        print(f'  - 关键词API数量: {len(config.keywords_api_urls)}')
        
        # 检查关键模块实例
        from src.keyword_api import keyword_api
        from src.keyword_api_multi import multi_api_manager
        from src.sitemap_parser import sitemap_parser
        from src.data_manager import data_manager
        from src.encryption import encryptor
        
        print('🔧 检查模块实例：')
        print(f'  - keyword_api: {type(keyword_api).__name__}')
        print(f'  - multi_api_manager: {type(multi_api_manager).__name__}')
        print(f'  - sitemap_parser: {type(sitemap_parser).__name__}')
        print(f'  - data_manager: {type(data_manager).__name__}')
        print(f'  - encryptor: {type(encryptor).__name__}')
        
        print('✅ 所有组件检查通过')
        
        return True
        
    except Exception as e:
        print(f'❌ 初始化失败: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_initialization()
    exit(0 if success else 1) 