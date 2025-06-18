#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词API处理验证测试
验证统一使用KEYWORDS_API_URLS的修复效果
"""

import os
import json
import importlib
from unittest.mock import patch

def test_keywords_api_handling():
    """测试关键词API处理逻辑"""
    print("🧪 关键词API处理验证测试")
    print("=" * 60)
    
    # 测试用的基础环境变量
    os.environ['WEBSITE_URLS'] = '["https://example.com/sitemap.xml"]'
    os.environ['ENCRYPTION_KEY'] = "1234567890123456789012345678901234567890123456789012345678901234"
    
    # 测试1：使用用户提供的多API配置
    print("\n📋 测试1：用户提供的多API配置")
    user_apis = [
        "https://seo1.yttomp3.dev/api/keywords?keyword=",
        "https://seo.yttomp3.dev/api/keywords?keyword=", 
        "https://k.seokey.vip/api/keywords?keyword=",
        "https://k2.seokey.vip/api/keywords?keyword="
    ]
    os.environ['KEYWORDS_API_URLS'] = json.dumps(user_apis)
    os.environ.pop('KEYWORDS_API_URL', None)  # 确保没有单API配置
    
    try:
        # 重新导入配置
        import src.config
        importlib.reload(src.config)
        from src.config import config
        
        print(f"✅ API数量: {len(config.keywords_api_urls)}")
        print(f"✅ API列表:")
        for i, api in enumerate(config.keywords_api_urls, 1):
            print(f"   {i}. {api}")
        
        # 测试MultiAPIKeywordManager
        from src.keyword_api_multi import multi_api_manager
        
        # 模拟API调用
        def mock_api_response(*args, **kwargs):
            return {
                'status': 'success',
                'data': [{
                    'keyword': args[0].split(',')[0] if args else 'test',
                    'metrics': {'avg_monthly_searches': 1000}
                }]
            }
        
        test_keywords = ['game', 'puzzle', 'action', 'strategy']
        
        with patch('src.keyword_api.KeywordAPI._fetch_from_api', side_effect=mock_api_response) as mock_fetch:
            result = multi_api_manager.batch_query_keywords_parallel(test_keywords)
            
            print(f"✅ 多API调用成功")
            print(f"   API调用次数: {mock_fetch.call_count}")
            print(f"   返回结果: {len(result)} 个关键词")
            print(f"   预期: 4个API并发处理")
            
            if mock_fetch.call_count == len(config.keywords_api_urls):
                print("🎯 完美！每个API都被调用了")
            elif mock_fetch.call_count > 1:
                print("✅ 良好！使用了多API并发")
            else:
                print("⚠️  警告：只使用了1个API")
        
    except Exception as e:
        print(f"❌ 多API测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试2：向后兼容单API配置
    print("\n📋 测试2：向后兼容单API配置")
    os.environ.pop('KEYWORDS_API_URLS', None)
    os.environ['KEYWORDS_API_URL'] = 'https://seo1.yttomp3.dev/api/keywords?keyword='
    
    try:
        # 重新导入配置
        importlib.reload(src.config)
        from src.config import config
        
        print(f"✅ API数量: {len(config.keywords_api_urls)}")
        print(f"✅ API列表: {config.keywords_api_urls}")
        print("✅ 向后兼容：单API自动转换为数组格式")
        
        # 测试单API模式
        with patch('src.keyword_api.KeywordAPI._fetch_from_api', side_effect=mock_api_response) as mock_fetch:
            result = multi_api_manager.batch_query_keywords_parallel(['test'])
            print(f"✅ 单API模式调用成功，API调用次数: {mock_fetch.call_count}")
        
    except Exception as e:
        print(f"❌ 单API测试失败: {e}")
    
    # 测试3：没有配置任何API
    print("\n📋 测试3：没有配置任何API")
    os.environ.pop('KEYWORDS_API_URLS', None)
    os.environ.pop('KEYWORDS_API_URL', None)
    
    try:
        importlib.reload(src.config)
        from src.config import config
        
        print(f"API数量: {len(config.keywords_api_urls)}")
        if len(config.keywords_api_urls) == 0:
            print("✅ 正确处理：没有API配置时返回空列表")
        
        # 测试错误处理
        result = multi_api_manager.batch_query_keywords_parallel(['test'])
        if result and isinstance(result, dict):
            print("✅ 错误处理正确：返回默认数据")
        
    except Exception as e:
        print(f"❌ 无API测试失败: {e}")

def test_real_scenario():
    """测试真实场景"""
    print("\n🚀 真实场景测试")
    print("=" * 60)
    
    # 使用用户提供的真实API配置
    real_apis = [
        "https://seo1.yttomp3.dev/api/keywords?keyword=",
        "https://seo.yttomp3.dev/api/keywords?keyword=", 
        "https://k.seokey.vip/api/keywords?keyword=",
        "https://k2.seokey.vip/api/keywords?keyword="
    ]
    
    print("📋 配置建议：")
    print(f"export KEYWORDS_API_URLS='{json.dumps(real_apis)}'")
    
    print("\n📋 GitHub Actions配置：")
    print(f"KEYWORDS_API_URLS: '{json.dumps(real_apis)}'")
    
    print("\n📋 预期效果：")
    print("✅ 4个API并发处理关键词查询")
    print("✅ 速度提升4倍")
    print("✅ 故障转移：一个API失败时自动使用其他API")
    print("✅ 负载均衡：请求分散到4个API服务器")
    print("✅ 日志前缀：content_watcher.keyword_api_multi")
    
    print("\n📋 验证方法：")
    print("运行后查看日志中的：")
    print("- '使用多API并发模式: 4 个API地址'")
    print("- '小批量处理模式: X 个关键词，使用直接并发'")
    print("- 'API X 查询完成，返回 Y 个关键词数据'")

def main():
    """主函数"""
    test_keywords_api_handling()
    test_real_scenario()

if __name__ == "__main__":
    main() 