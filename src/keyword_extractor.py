#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词提取模块
从URL中提取关键词
"""

import logging
import re
from urllib.parse import urlparse

# 配置日志
logger = logging.getLogger('content_watcher.keyword_extractor')

class KeywordExtractor:
    """从URL中提取关键词"""

    def __init__(self):
        """初始化提取器"""
        pass

    @staticmethod
    def extract_keywords_from_url(url: str) -> str:
        """从URL中提取关键词

        Args:
            url: 待提取关键词的URL

        Returns:
            提取出的关键词字符串，如果无法提取则返回空字符串
        """
        try:
            # 解析URL获取路径
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')

            # 如果路径为空则返回空字符串
            if not path_parts:
                return ""

            # 1. 检查是否为纯数字路径（如 /sitemap/games/33）
            if path_parts[-1].isdigit():
                # logger.debug(f"URL路径以纯数字结尾，跳过关键词提取: {url}")
                return ""

            # 检查路径的最后部分是否以.games结尾
            if path_parts[-1].endswith('.games'):
                # logger.debug(f"URL路径以.games结尾，跳过关键词提取: {url}")
                return ""

            # 2. 检查网站特定结构
            # 例如: /game/territory-war 中，提取 territory-war 作为关键词
            if len(path_parts) >= 2 and path_parts[-2] == "game":
                keywords = path_parts[-1].replace('-', ' ')
                # logger.debug(f"从游戏URL提取关键词: {keywords}")
                return keywords

            # 3. 其他情况：一般页面提取最后一部分作为关键词
            # 如果最后部分看起来像是 ID 或太短（少于3个字符），则尝试使用前一部分
            last_part = path_parts[-1]
            if len(last_part) < 3 or last_part.isdigit() or re.match(r'^[a-f0-9]+$', last_part):
                # 如果路径只有一部分则返回空字符串
                if len(path_parts) < 2:
                    return ""
                # 否则使用倒数第二部分
                last_part = path_parts[-2]

            # 将连字符替换为空格
            keywords = last_part.replace('-', ' ')

            # 如果关键词看起来很不合理（例如太长或太短），记录日志但仍返回
            if len(keywords) < 3 or len(keywords) > 50:
                pass  # 不做任何操作，只是为了保持缩进结构
                # logger.debug(f"提取的关键词可能不合理: {keywords}, URL: {url}")

            return keywords

        except Exception as e:
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.error(f"提取关键词时出错: {e}, 域名: {domain_part}")
            return ""

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """计算两个字符串的相似度，使用简单的Jaccard相似度

        Args:
            str1: 第一个字符串
            str2: 第二个字符串

        Returns:
            相似度得分，范围0-1，1表示完全相同
        """
        # 转换为集合
        set1 = set(str1.split())
        set2 = set(str2.split())

        # 计算交集大小
        intersection = len(set1.intersection(set2))
        # 计算并集大小
        union = len(set1.union(set2))

        # 如果并集为空，返回0
        if union == 0:
            return 0

        # 返回Jaccard相似度
        return intersection / union

# 创建全局提取器实例
keyword_extractor = KeywordExtractor()
