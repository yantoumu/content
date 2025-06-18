#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ContentWatcher 最终综合测试
验证完整调用链和错误处理
"""

import os
import logging
from unittest.mock import patch

# 设置环境变量
os.environ['WEBSITE_URLS'] = '["https://example.com/sitemap.xml", "https://test.com/sitemap.xml"]'
os.environ['ENCRYPTION_KEY'] = "1234567890123456789012345678901234567890123456789012345678901234"
os.environ['KEYWORDS_API_URLS'] = '["https://api1.example.com/keywords/", "https://api2.example.com/keywords/"]'

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_final_test():
    """运行最终综合测试"""
    print("🚀 开始ContentWatcher最终综合测试...")
    print("="*60)
    
    try:
        from src.content_watcher import ContentWatcher
        from src.sitemap_parser import sitemap_parser
        from src.keyword_api_multi import multi_api_manager
        from src.sitemap_api import sitemap_api
        from src.config import config
        
        # 显示配置信息
        print(f"📋 配置信息:")
        print(f"   - 网站数量: {len(config.website_urls)}")
        print(f"   - 关键词API数量: {len(config.keywords_api_urls)}")
        print(f"   - 网站地图API启用: {config.sitemap_api_enabled}")
        
        # 创建ContentWatcher实例
        watcher = ContentWatcher(test_mode=True, max_first_run_updates=10)
        print("✅ ContentWatcher初始化成功")
        
        # 模拟测试数据
        mock_sitemap_data_1 = {
            'https://example.com/game/action-game': '2025-06-18',
            'https://example.com/game/puzzle-game': '2025-06-18',
            'https://example.com/game/strategy-game': '2025-06-17'
        }
        
        mock_keyword_data = {
            'action game': {'volume': 1000, 'difficulty': 0.5},
            'puzzle game': {'volume': 800, 'difficulty': 0.3},
            'strategy game': {'volume': 600, 'difficulty': 0.4}
        }
        
        print("\n🔄 测试完整执行流程...")
        
        # Mock各个组件的返回值
        with patch.object(sitemap_parser, 'download_and_parse_sitemap', return_value=mock_sitemap_data_1), \
             patch.object(multi_api_manager, 'batch_query_keywords_parallel', return_value=mock_keyword_data), \
             patch.object(sitemap_api, 'send_batch_updates', return_value=True):
            
            print("   🔄 执行watcher.run()...")
            watcher.run()
            print("   ✅ 完整流程执行成功")
        
        print("\n🎉 所有测试通过！调用链工作正常")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 综合测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_final_test()
    exit(0 if success else 1) 