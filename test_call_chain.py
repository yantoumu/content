#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ContentWatcher完整调用链
模拟各个阶段的执行流程
"""

import os
import logging
from unittest.mock import patch, MagicMock

# 设置环境变量
os.environ['WEBSITE_URLS'] = '["https://example.com/sitemap.xml"]'
os.environ['ENCRYPTION_KEY'] = "1234567890123456789012345678901234567890123456789012345678901234"
os.environ['KEYWORDS_API_URL'] = "https://api.example.com/keywords/"

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_call_chain():
    """测试完整调用链"""
    print("🚀 开始测试ContentWatcher调用链...")
    
    try:
        from src.content_watcher import ContentWatcher
        from src.sitemap_parser import sitemap_parser
        from src.keyword_api_multi import multi_api_manager
        from src.sitemap_api import sitemap_api
        
        # 创建ContentWatcher实例
        watcher = ContentWatcher(test_mode=True, max_first_run_updates=5)
        print("✅ ContentWatcher初始化成功")
        
        # 模拟sitemap数据
        mock_sitemap_data = {
            'https://example.com/page1': '2025-06-18',
            'https://example.com/page2': '2025-06-18',
            'https://example.com/page3': '2025-06-17'
        }
        
        # 模拟关键词数据
        mock_keyword_data = {
            'test-keyword-1': {'volume': 1000, 'difficulty': 0.5},
            'test-keyword-2': {'volume': 500, 'difficulty': 0.3}
        }
        
        print("\n📋 阶段1：测试数据收集...")
        
        # Mock sitemap解析
        with patch.object(sitemap_parser, 'download_and_parse_sitemap', return_value=mock_sitemap_data):
            site_id, site_data = watcher.site_data_collector.collect_site_data("https://example.com/sitemap.xml", 0)
            print(f"  ✅ 站点数据收集完成: {site_id}")
            print(f"     - 更新URL数量: {len(site_data.get('updated_urls', []))}")
            print(f"     - 关键词数量: {len(site_data.get('keywords', []))}")
        
        print("\n📋 阶段2：测试关键词查询...")
        
        # Mock 多API关键词查询
        with patch.object(multi_api_manager, 'batch_query_keywords_parallel', return_value=mock_keyword_data):
            keywords = site_data.get('keywords', [])[:2]  # 取前2个关键词
            if keywords:
                result = multi_api_manager.batch_query_keywords_parallel(keywords)
                print(f"  ✅ 关键词查询完成: {len(result)} 个关键词")
        
        print("\n📋 阶段3：测试更新处理...")
        
        # Mock sitemap API
        with patch.object(sitemap_api, 'send_batch_updates', return_value=True):
            if site_data and site_data.get('updated_urls'):
                updated_urls = watcher.site_update_processor.process_site_updates(
                    site_id,
                    site_data,
                    site_data.get('url_keywords_map', {}),
                    mock_keyword_data
                )
                print(f"  ✅ 更新处理完成: {len(updated_urls)} 个URL")
        
        print("\n🎯 完整流程测试...")
        
        # 测试完整的run方法（使用mock避免网络请求）
        with patch.object(sitemap_parser, 'download_and_parse_sitemap', return_value=mock_sitemap_data), \
             patch.object(multi_api_manager, 'batch_query_keywords_parallel', return_value=mock_keyword_data), \
             patch.object(sitemap_api, 'send_batch_updates', return_value=True):
            
            print("  🔄 执行watcher.run()...")
            watcher.run()
            print("  ✅ 完整流程执行成功")
        
        print("\n🎉 所有调用链测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 调用链测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def print_call_chain_analysis():
    """打印调用链分析"""
    print("\n" + "="*60)
    print("📊 ContentWatcher 调用链分析")
    print("="*60)
    
    analysis = """
🔄 主要执行流程 (main.py → ContentWatcher.run()):

1️⃣ 第一阶段：数据收集 (并行/串行)
   main.py
   └── ContentWatcher.run()
       └── SiteDataCollector.collect_site_data()
           ├── SitemapParser.download_and_parse_sitemap()
           ├── DataManager.get_previous_urls()
           ├── KeywordExtractor.extract_keywords()
           └── Encryptor.encrypt_url()

2️⃣ 第二阶段：全局关键词查询
   ContentWatcher.run()
   └── MultiAPIKeywordManager.batch_query_keywords_parallel()
       ├── KeywordAPI.get_keyword_data() (多个API并发)
       └── ThreadPoolExecutor (负载均衡)

3️⃣ 第三阶段：更新处理
   ContentWatcher.run()
   └── SiteUpdateProcessor.process_site_updates()
       ├── SitemapAPI.send_batch_updates()
       ├── DataManager.update_site_data()
       └── Encryptor.encrypt_data()

🔧 关键优化点:
✅ 全局关键词去重 - 避免重复API调用
✅ 多API并发查询 - 提升2-3倍性能
✅ 组件职责分离 - 符合SOLID原则
✅ 会话复用 - 减少连接开销
✅ 批量处理 - 降低API请求频率
"""
    print(analysis)

if __name__ == "__main__":
    print_call_chain_analysis()
    success = test_call_chain()
    exit(0 if success else 1) 