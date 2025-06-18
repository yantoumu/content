#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整调用链分析工具
追踪从main.py到多API均衡的完整执行流程
"""

import logging
import os
import json
import sys
from typing import Dict, List, Any

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class CallChainAnalyzer:
    """调用链分析器"""
    
    def __init__(self):
        self.logger = logging.getLogger('call_chain_analyzer')
        self.call_stack = []
        
    def analyze_full_chain(self):
        """分析完整调用链"""
        print("=" * 80)
        print("🔍 完整调用链分析")
        print("=" * 80)
        
        # 1. 分析入口点
        self._analyze_entry_point()
        
        # 2. 分析配置加载
        self._analyze_config_loading()
        
        # 3. 分析内容监控器
        self._analyze_content_watcher()
        
        # 4. 分析多API均衡机制
        self._analyze_multi_api_balance()
        
        # 5. 分析最佳实践评估
        self._analyze_best_practices()
        
    def _analyze_entry_point(self):
        """分析程序入口点"""
        print("\n📍 1. 程序入口点分析 (main.py)")
        print("-" * 50)
        
        print("✅ 入口流程:")
        print("  main() -> parse_args() -> ContentWatcher() -> watcher.run()")
        
        print("\n🔧 参数解析:")
        print("  --test: 测试模式")
        print("  --max-updates: 首次运行更新数量限制")
        
    def _analyze_config_loading(self):
        """分析配置加载过程"""
        print("\n📍 2. 配置加载分析 (src/config.py)")
        print("-" * 50)
        
        # 模拟配置加载
        keywords_api_urls_str = os.environ.get('KEYWORDS_API_URLS', '')
        keywords_api_url = os.environ.get('KEYWORDS_API_URL', '')
        
        print("🔧 配置优先级:")
        print("  1. KEYWORDS_API_URLS (多API配置) - 优先")
        print("  2. KEYWORDS_API_URL (单API配置) - 向后兼容")
        
        if keywords_api_urls_str:
            try:
                parsed_urls = json.loads(keywords_api_urls_str)
                print(f"\n✅ 检测到KEYWORDS_API_URLS: {len(parsed_urls)} 个API")
                for i, url in enumerate(parsed_urls):
                    print(f"  API {i+1}: {url}")
                    
                print(f"\n🎯 模式选择: {'多API并发模式' if len(parsed_urls) > 1 else '单API模式'}")
                
            except json.JSONDecodeError as e:
                print(f"❌ KEYWORDS_API_URLS JSON解析失败: {e}")
                
        elif keywords_api_url:
            print(f"\n⚠️  检测到单API配置: {keywords_api_url}")
            print("  建议升级为KEYWORDS_API_URLS以启用多API并发")
            
        else:
            print("\n❌ 未检测到任何API配置")
            
    def _analyze_content_watcher(self):
        """分析内容监控器"""
        print("\n📍 3. 内容监控器分析")
        print("-" * 50)
        
        print("🔄 调用链:")
        print("  ContentWatcher.run()")
        print("  └── site_update_processor.process_updates()")
        print("      └── keyword_extractor.extract_keywords()")
        print("          └── MultiAPIKeywordManager.batch_query_keywords_parallel()")
        
    def _analyze_multi_api_balance(self):
        """分析多API均衡机制"""
        print("\n📍 4. 多API均衡机制分析")
        print("-" * 50)
        
        # 模拟配置
        keywords_api_urls_str = os.environ.get('KEYWORDS_API_URLS', '')
        if not keywords_api_urls_str:
            print("❌ 未配置KEYWORDS_API_URLS，无法分析均衡机制")
            return
            
        try:
            api_urls = json.loads(keywords_api_urls_str)
            api_count = len(api_urls)
            
            print(f"🎯 API数量: {api_count}")
            print(f"🔀 均衡策略: {'多API并发' if api_count > 1 else '单API模式'}")
            
            if api_count > 1:
                print("\n📊 负载均衡机制:")
                print("  1. 关键词分片 (Keyword Sharding)")
                print("     - 将关键词列表按API数量分割")
                print("     - 每个API处理一个分片")
                
                print("\n  2. 并发执行模式:")
                print("     - 小批量 (≤100): 直接并发 (_batch_query_direct_parallel)")
                print("     - 大批量 (>100): 队列调度 (_batch_query_with_queue_scheduler)")
                
                print("\n  3. 分片算法:")
                print("     - 循环分配: keywords[i] -> API[i % api_count]")
                print("     - 确保负载均匀分布")
                
                # 模拟分片
                test_keywords = [f"keyword_{i}" for i in range(12)]
                print(f"\n  4. 分片示例 (12个关键词 -> {api_count}个API):")
                for i, keyword in enumerate(test_keywords):
                    api_index = i % api_count
                    print(f"     {keyword} -> API_{api_index + 1}")
                    
                print("\n  5. 容错机制:")
                print("     - API失败时自动重试")
                print("     - 失败关键词重新分配到其他API")
                print("     - 最终失败时生成默认数据")
                
        except json.JSONDecodeError:
            print("❌ API配置解析失败")
            
    def _analyze_best_practices(self):
        """分析最佳实践"""
        print("\n📍 5. 最佳实践评估")
        print("-" * 50)
        
        practices = {
            "✅ SOLID原则": [
                "单一职责: ConfigValidator独立验证配置",
                "开闭原则: APISchedulerConfig支持扩展",
                "依赖倒置: 通过config模块解耦"
            ],
            "✅ 并发设计": [
                "ThreadPoolExecutor管理线程池",
                "队列调度器处理大批量任务",
                "线程安全的结果收集"
            ],
            "✅ 容错处理": [
                "多级重试机制",
                "API失败自动切换",
                "默认数据生成保证服务可用"
            ],
            "⚠️  潜在改进": [
                "缺少API健康检查",
                "没有动态负载调整",
                "缺少详细性能监控"
            ]
        }
        
        for category, items in practices.items():
            print(f"\n{category}:")
            for item in items:
                print(f"  • {item}")
                
    def run_live_test(self):
        """运行实时测试"""
        print("\n" + "=" * 80)
        print("🧪 实时均衡测试")
        print("=" * 80)
        
        try:
            # 导入并测试
            from src.config import config
            from src.keyword_api_multi import MultiAPIKeywordManager
            
            print(f"\n📊 当前配置:")
            print(f"  API数量: {len(config.keywords_api_urls)}")
            print(f"  API地址:")
            for i, url in enumerate(config.keywords_api_urls):
                print(f"    {i+1}. {url}")
                
            # 创建管理器
            manager = MultiAPIKeywordManager()
            
            # 测试关键词
            test_keywords = ["python", "javascript", "react", "vue", "angular", "nodejs"]
            
            print(f"\n🎯 测试关键词: {test_keywords}")
            print(f"关键词数量: {len(test_keywords)}")
            
            # 模拟分片
            if len(config.keywords_api_urls) > 1:
                print(f"\n📊 分片分配预览:")
                for i, keyword in enumerate(test_keywords):
                    api_index = i % len(config.keywords_api_urls)
                    api_url = config.keywords_api_urls[api_index]
                    print(f"  {keyword} -> API_{api_index + 1} ({api_url})")
            else:
                print(f"\n📊 单API模式: 所有关键词使用同一API")
                
        except Exception as e:
            print(f"❌ 实时测试失败: {e}")
            import traceback
            traceback.print_exc()

def main():
    """主函数"""
    analyzer = CallChainAnalyzer()
    
    # 检查环境变量
    if not os.environ.get('KEYWORDS_API_URLS') and not os.environ.get('KEYWORDS_API_URL'):
        print("⚠️  未设置API配置环境变量，请设置KEYWORDS_API_URLS或KEYWORDS_API_URL")
        print("示例:")
        print('export KEYWORDS_API_URLS=\'["https://api1.com/keywords?keyword=", "https://api2.com/keywords?keyword="]\'')
        return
        
    # 运行分析
    analyzer.analyze_full_chain()
    analyzer.run_live_test()
    
    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)

if __name__ == "__main__":
    main() 