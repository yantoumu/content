#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隐私保护工具模块
提供统一的敏感信息脱敏功能
"""

import re
from urllib.parse import urlparse
from typing import Optional


class PrivacyMasker:
    """隐私脱敏器 - 单一职责：敏感信息脱敏"""

    @staticmethod
    def mask_domain(domain: str) -> str:
        """脱敏域名，保留调试价值但隐藏敏感信息

        Args:
            domain: 原始域名

        Returns:
            脱敏后的域名

        Examples:
            example.com -> ex*****.com
            subdomain.example.com -> ex*****.com
            very-long-domain.co.uk -> ve*****.co.uk
        """
        if not domain or len(domain) < 3:
            return "***"

        # 分离域名和后缀
        parts = domain.split('.')
        if len(parts) >= 2:
            # 获取主域名部分（去掉子域名，保留主域名）
            if len(parts) > 2:
                # 对于 subdomain.example.com，取 example
                name_part = parts[-2]
                suffix_part = '.'.join(parts[-1:])
            else:
                # 对于 example.com，取 example
                name_part = parts[0]
                suffix_part = '.'.join(parts[1:])

            # 脱敏域名部分
            if len(name_part) <= 2:
                masked_name = "*" * len(name_part)
            else:
                masked_name = name_part[:2] + "*" * 5  # 固定5个星号，更一致

            return f"{masked_name}.{suffix_part}"

        # 简单域名处理（无点号）
        if len(domain) <= 2:
            return "*" * len(domain)
        else:
            return domain[:2] + "*" * 5

    @staticmethod
    def mask_url(url: str) -> str:
        """脱敏URL，保留协议和域名脱敏，隐藏路径
        
        Args:
            url: 原始URL
            
        Returns:
            脱敏后的URL
            
        Examples:
            https://example.com/path/to/page -> https://ex*****.com/***
            http://subdomain.example.com/api/v1 -> http://su*****.com/***
        """
        if not url:
            return "***"
        
        try:
            parsed = urlparse(url)
            masked_domain = PrivacyMasker.mask_domain(parsed.netloc)
            
            # 构建脱敏URL
            scheme = parsed.scheme or "***"
            path_indicator = "/***" if parsed.path and parsed.path != "/" else ""
            
            return f"{scheme}://{masked_domain}{path_indicator}"
        except Exception:
            return "***"

    @staticmethod
    def mask_api_url(api_url: str) -> str:
        """脱敏API URL，特别处理API地址
        
        Args:
            api_url: 原始API URL
            
        Returns:
            脱敏后的API URL
            
        Examples:
            https://api.example.com/v1/keywords -> https://ap*****.com/***
            https://k2.seokey.vip/api/keywords -> https://k2*****.vip/***
        """
        return PrivacyMasker.mask_url(api_url)

    @staticmethod
    def mask_site_identifier(site_url: str) -> str:
        """为网站创建安全的标识符用于日志

        Args:
            site_url: 网站URL

        Returns:
            安全的网站标识符

        Examples:
            https://example.com -> ex*****.com
            https://subdomain.example.com -> su*****.com
        """
        try:
            parsed = urlparse(site_url)
            return PrivacyMasker.mask_domain(parsed.netloc)
        except Exception:
            return "***"

    @staticmethod
    def extract_domain_safely(url: str) -> str:
        """安全地提取URL的域名部分，用于日志记录

        Args:
            url: 原始URL

        Returns:
            域名部分，如果提取失败返回 '***'

        Examples:
            https://example.com/path -> example.com
            invalid-url -> ***
        """
        try:
            if not url:
                return '***'
            parsed = urlparse(url)
            return parsed.netloc if parsed.netloc else '***'
        except Exception:
            return '***'

    @staticmethod
    def mask_keyword(keyword: str) -> str:
        """脱敏关键词，保留调试价值但隐藏敏感内容

        Args:
            keyword: 原始关键词

        Returns:
            脱敏后的关键词

        Examples:
            "几何破折号海晶石" -> "几何***"
            "tits and zombies" -> "ti***"
            "持枪向导" -> "持***"
            "game" -> "ga***"
            "a" -> "***"
        """
        if not keyword or not isinstance(keyword, str):
            return "***"

        # 去除首尾空格
        keyword = keyword.strip()

        if len(keyword) <= 1:
            return "***"
        elif len(keyword) == 2:
            return keyword[:1] + "***"
        elif len(keyword) == 3:
            return keyword[:2] + "***"
        else:
            return keyword[:2] + "***"

    @staticmethod
    def mask_keywords_list(keywords: list) -> str:
        """脱敏关键词列表，用于日志输出

        Args:
            keywords: 关键词列表

        Returns:
            脱敏后的关键词列表字符串

        Examples:
            ["game", "action"] -> "[ga***, ac***]"
            ["几何破折号海晶石"] -> "[几何***]"
        """
        if not keywords:
            return "[]"

        masked_keywords = [PrivacyMasker.mask_keyword(kw) for kw in keywords]
        return f"[{', '.join(masked_keywords)}]"

    @staticmethod
    def safe_log_format(message: str, url: Optional[str] = None, 
                       domain: Optional[str] = None, api_url: Optional[str] = None) -> str:
        """安全的日志格式化，自动脱敏敏感信息
        
        Args:
            message: 日志消息模板
            url: 可选的URL参数
            domain: 可选的域名参数  
            api_url: 可选的API URL参数
            
        Returns:
            脱敏后的日志消息
        """
        formatted_message = message
        
        if url:
            masked_url = PrivacyMasker.mask_url(url)
            formatted_message = formatted_message.replace("{url}", masked_url)
        
        if domain:
            masked_domain = PrivacyMasker.mask_domain(domain)
            formatted_message = formatted_message.replace("{domain}", masked_domain)
            
        if api_url:
            masked_api = PrivacyMasker.mask_api_url(api_url)
            formatted_message = formatted_message.replace("{api_url}", masked_api)
        
        return formatted_message


# 创建全局脱敏器实例
privacy_masker = PrivacyMasker()
