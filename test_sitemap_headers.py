#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试sitemap请求头和API配置
诊断403和500错误问题
"""

import os
import json
import requests
import logging
from urllib.parse import urlparse
from typing import Dict, List

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_sitemap_headers():
    """测试sitemap请求头配置"""
    print("🔍 测试Sitemap请求头配置")
    print("=" * 60)
    
    # 测试网站列表（一些常见的游戏网站）
    test_urls = [
        "https://pokerogue.io/sitemap.xml",
        "https://www.play-games.com/sitemap.xml", 
        "https://superkidgames.com/sitemap.xml",
        "https://www.brightestgames.com/games-sitemap.xml"
    ]
    
    # 原始请求头（可能导致403）
    basic_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 增强请求头（更完整的浏览器模拟）
    enhanced_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }
    
    for url in test_urls:
        domain = urlparse(url).netloc
        print(f"\n🌐 测试域名: {domain}")
        
        # 添加Referer头
        referer_url = f"https://{domain}/"
        enhanced_headers['Referer'] = referer_url
        
        # 测试基础请求头
        print("  📡 基础请求头测试...")
        try:
            response = requests.get(url, headers=basic_headers, timeout=10)
            print(f"    ✅ 状态码: {response.status_code}")
        except Exception as e:
            print(f"    ❌ 失败: {e}")
        
        # 测试增强请求头
        print("  🚀 增强请求头测试...")
        try:
            response = requests.get(url, headers=enhanced_headers, timeout=10)
            print(f"    ✅ 状态码: {response.status_code}")
            if response.status_code == 200:
                content_length = len(response.content)
                print(f"    📄 内容长度: {content_length} bytes")
        except Exception as e:
            print(f"    ❌ 失败: {e}")

def test_api_configuration():
    """测试API配置问题"""
    print("\n🔧 测试API配置")
    print("=" * 60)
    
    # 检查环境变量
    keywords_api_urls = os.environ.get('KEYWORDS_API_URLS', '')
    keywords_api_url = os.environ.get('KEYWORDS_API_URL', '')
    
    print(f"📋 环境变量检查:")
    print(f"  KEYWORDS_API_URLS: {'已设置' if keywords_api_urls else '未设置'}")
    print(f"  KEYWORDS_API_URL: {'已设置' if keywords_api_url else '未设置'}")
    
    if keywords_api_urls:
        try:
            urls = json.loads(keywords_api_urls)
            print(f"  ✅ 多API配置: {len(urls)} 个API")
            for i, url in enumerate(urls):
                domain = urlparse(url).netloc
                print(f"    API {i+1}: {domain}")
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON解析失败: {e}")
    elif keywords_api_url:
        domain = urlparse(keywords_api_url).netloc
        print(f"  ⚠️  单API配置: {domain}")
        print("  💡 建议升级为KEYWORDS_API_URLS以启用多API并发")
    else:
        print("  ❌ 未配置任何关键词API")
        return
    
    # 测试API连通性
    print(f"\n🔗 API连通性测试:")
    
    if keywords_api_urls:
        try:
            urls = json.loads(keywords_api_urls)
            for i, api_url in enumerate(urls):
                domain = urlparse(api_url).netloc
                print(f"  🌐 测试API {i+1}: {domain}")
                test_keyword_api(api_url, f"API_{i+1}")
        except json.JSONDecodeError:
            print("  ❌ API配置解析失败")
    elif keywords_api_url:
        domain = urlparse(keywords_api_url).netloc
        print(f"  🌐 测试单API: {domain}")
        test_keyword_api(keywords_api_url, "单API")

def test_keyword_api(api_url: str, api_name: str):
    """测试单个关键词API"""
    try:
        # 构造测试请求
        test_keyword = "test"
        test_url = f"{api_url}{test_keyword}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        response = requests.get(test_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"    ✅ {api_name}: 连接正常")
            try:
                data = response.json()
                print(f"    📊 返回数据: {type(data).__name__}")
            except:
                print(f"    📄 返回文本: {len(response.text)} 字符")
        elif response.status_code == 500:
            print(f"    ❌ {api_name}: 服务器错误 (500)")
            print(f"    💡 可能原因: API服务不稳定或过载")
        else:
            print(f"    ⚠️  {api_name}: 状态码 {response.status_code}")
            
    except requests.exceptions.Timeout:
        print(f"    ⏰ {api_name}: 请求超时")
    except requests.exceptions.ConnectionError:
        print(f"    🔌 {api_name}: 连接失败")
    except Exception as e:
        print(f"    ❌ {api_name}: 错误 - {e}")

def test_config_loading():
    """测试配置加载逻辑"""
    print("\n⚙️  测试配置加载逻辑")
    print("=" * 60)
    
    try:
        # 模拟配置加载
        from src.config import config
        
        print(f"📊 配置状态:")
        print(f"  关键词API数量: {len(config.keywords_api_urls)}")
        print(f"  网站地图API启用: {config.sitemap_api_enabled}")
        print(f"  网站数量: {len(config.website_urls)}")
        
        # 检查是否会使用多API模式
        if len(config.keywords_api_urls) > 1:
            print(f"  🎯 预期模式: 多API并发模式")
            print(f"  📝 日志前缀应为: content_watcher.keyword_api_multi")
        else:
            print(f"  🎯 预期模式: 单API模式")
            print(f"  📝 日志前缀应为: content_watcher.keyword_api")
            
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")

def analyze_log_patterns():
    """分析日志模式"""
    print("\n📋 日志模式分析")
    print("=" * 60)
    
    print("🔍 从用户日志观察到的问题:")
    print("  1. ❌ 大量403错误 - sitemap访问被拒绝")
    print("     - pokerogue.io, play-games.com, superkidgames.com等")
    print("     - 可能原因: 请求头不够完整，被识别为爬虫")
    
    print("  2. ❌ 重复500错误 - 关键词API失败")
    print("     - 日志前缀: content_watcher.keyword_api")
    print("     - 说明仍在使用单API模式，而非多API模式")
    
    print("  3. ⚠️  配置警告信息")
    print("     - '建议升级为KEYWORDS_API_URLS以启用多API并发'")
    print("     - 说明环境变量配置可能有问题")
    
    print("\n💡 建议修复方案:")
    print("  1. 🔧 增强sitemap请求头")
    print("     - 添加更完整的浏览器模拟头部")
    print("     - 包含sec-ch-ua, Sec-Fetch-* 等现代浏览器特征")
    
    print("  2. 🔄 确保多API配置生效")
    print("     - 检查KEYWORDS_API_URLS环境变量格式")
    print("     - 确保JSON数组格式正确")
    
    print("  3. 🛡️  API负载均衡")
    print("     - 启用多API模式分散请求压力")
    print("     - 减少单API的500错误频率")

def main():
    """主函数"""
    print("🚀 Sitemap和API诊断工具")
    print("=" * 80)
    
    # 1. 测试sitemap请求头
    test_sitemap_headers()
    
    # 2. 测试API配置
    test_api_configuration()
    
    # 3. 测试配置加载
    test_config_loading()
    
    # 4. 分析日志模式
    analyze_log_patterns()
    
    print("\n" + "=" * 80)
    print("✅ 诊断完成")

if __name__ == "__main__":
    main() 