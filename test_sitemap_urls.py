#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试SITEMAP_URLS环境变量的解析
"""

import os
import json
import sys

# 尝试解析SITEMAP_URLS
try:
    urls_json = os.environ.get('SITEMAP_URLS', '')
    print(f"原始SITEMAP_URLS值: {urls_json}")
    print(f"字符数: {len(urls_json)}")
    print(f"ASCII码: {[ord(c) for c in urls_json[:20]]}")
    
    # 尝试解析
    urls = json.loads(urls_json)
    print(f"\n成功解析! 包含 {len(urls)} 个URL:")
    for i, url in enumerate(urls):
        print(f"{i+1}. {url}")
except json.JSONDecodeError as e:
    print(f"JSON解析错误: {e}")
    print(f"错误位置: 第{e.lineno}行, 第{e.colno}列, 字符位置 {e.pos}")
    
    # 显示错误周围的字符
    if e.pos < len(urls_json):
        start = max(0, e.pos - 10)
        end = min(len(urls_json), e.pos + 10)
        context = urls_json[start:end]
        pointer = ' ' * (min(10, e.pos - start)) + '^'
        print(f"错误上下文: ...{context}...")
        print(f"              {pointer}")
except Exception as e:
    print(f"其他错误: {e}") 