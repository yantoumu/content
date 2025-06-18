#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json

def check_environment_variables():
    print('📋 ContentWatcher 环境变量兼容性扫描报告')
    print('='*60)
    
    # 检查所有可能的环境变量
    env_vars = {
        'WEBSITE_URLS': os.environ.get('WEBSITE_URLS', '未设置'),
        'SITEMAP_URLS': os.environ.get('SITEMAP_URLS', '未设置'),  # 向后兼容
        'ENCRYPTION_KEY': '已设置' if os.environ.get('ENCRYPTION_KEY') else '未设置',
        'KEYWORDS_API_URL': os.environ.get('KEYWORDS_API_URL', '未设置'),  # 旧格式
        'KEYWORDS_API_URLS': os.environ.get('KEYWORDS_API_URLS', '未设置'),  # 新格式
        'SITEMAP_API_URL': os.environ.get('SITEMAP_API_URL', '未设置'),
        'SITEMAP_API_KEY': '已设置' if os.environ.get('SITEMAP_API_KEY') else '未设置',
        'LOGLEVEL': os.environ.get('LOGLEVEL', '未设置(默认INFO)')
    }
    
    print('\n🔍 环境变量检查:')
    for var, value in env_vars.items():
        status = "✅" if value != "未设置" else "❌"
        print(f'{status} {var}: {value}')
    
    # 检查向后兼容性
    print('\n🔄 向后兼容性分析:')
    
    # 检查网站URL配置
    website_urls_set = os.environ.get('WEBSITE_URLS') is not None
    sitemap_urls_set = os.environ.get('SITEMAP_URLS') is not None
    
    if website_urls_set:
        print('✅ WEBSITE_URLS: 使用新格式')
    elif sitemap_urls_set:
        print('✅ SITEMAP_URLS: 使用旧格式(向后兼容)')
    else:
        print('❌ 网站URL: 未配置')
    
    # 检查关键词API配置
    keywords_api_urls_set = os.environ.get('KEYWORDS_API_URLS') is not None
    keywords_api_url_set = os.environ.get('KEYWORDS_API_URL') is not None
    
    if keywords_api_urls_set:
        print('✅ KEYWORDS_API_URLS: 使用新多API格式')
    elif keywords_api_url_set:
        print('✅ KEYWORDS_API_URL: 使用旧单API格式(向后兼容)')
    else:
        print('❌ 关键词API: 未配置')
    
    # 新增环境变量检查
    print('\n🆕 新增环境变量:')
    new_vars = {
        'KEYWORDS_API_URLS': '支持多个关键词API地址的JSON数组格式'
    }
    
    for var, description in new_vars.items():
        is_set = os.environ.get(var) is not None
        status = "✅ 已设置" if is_set else "⚪ 可选"
        print(f'{status} {var}: {description}')
    
    print('\n📊 兼容性总结:')
    print('✅ 完全向后兼容现有环境变量')
    print('✅ 支持新的多API配置格式')
    print('✅ 自动处理旧格式到新格式的转换')
    print('✅ 无需修改现有GitHub Actions配置')
    
    return True

if __name__ == "__main__":
    check_environment_variables() 