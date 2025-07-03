#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词提取模块
从URL中提取关键词
"""

import logging
import re
from typing import Callable, List, Dict, Any
from urllib.parse import urlparse
from src.privacy_utils import PrivacyMasker

# 配置日志
logger = logging.getLogger('content_watcher.keyword_extractor')

class URLFilter:
    """URL过滤器，用于确定URL是否应被排除处理"""
    
    def __init__(self):
        """初始化过滤器并注册所有过滤规则"""
        # 过滤规则字典，包含名称和对应的过滤函数
        # 每个过滤函数接收ParseResult对象，如果URL应被排除则返回True
        self.filters: Dict[str, Callable] = {
            # 域名过滤规则
            "domain_games_suffix": self._filter_domain_games_suffix,
            
            # 路径过滤规则
            "path_tag": self._filter_path_tag,
            
            # 网站地图过滤规则
            "sitemap_xml_extension": self._filter_sitemap_xml_extension,
            "sitemap_path_keyword": self._filter_sitemap_path_keyword,
            "sitemap_filename_keyword": self._filter_sitemap_filename_keyword,
        }
    
    def should_exclude(self, parsed_url) -> bool:
        """检查URL是否应该被排除
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果URL应该被排除，返回True；否则返回False
        """
        # 遍历所有过滤规则
        for filter_name, filter_func in self.filters.items():
            try:
                if filter_func(parsed_url):
                    # 调试日志，记录匹配的过滤规则
                    if logger.isEnabledFor(logging.DEBUG):
                        domain = parsed_url.netloc
                        logger.debug(f"URL被过滤规则'{filter_name}'排除: {domain}")
                    return True
            except Exception as e:
                # 过滤规则执行出错，记录日志但不中断处理
                logger.error(f"执行过滤规则'{filter_name}'时出错: {e}")
        
        # 所有过滤规则都通过，URL不应被排除
        return False
    
    # ===== 域名过滤规则 =====
    
    def _filter_domain_games_suffix(self, parsed_url) -> bool:
        """过滤.games后缀的域名
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果域名以.games结尾，返回True；否则返回False
        """
        return parsed_url.netloc.endswith('.games')
    
    # ===== 路径过滤规则 =====
    
    def _filter_path_tag(self, parsed_url) -> bool:
        """过滤包含/tag/的路径
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果路径包含/tag/，返回True；否则返回False
        """
        return '/tag/' in parsed_url.path
    
    # ===== 网站地图过滤规则 =====
    
    def _filter_sitemap_xml_extension(self, parsed_url) -> bool:
        """过滤XML格式的网站地图
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果路径以.xml或.xml.gz结尾，返回True；否则返回False
        """
        path = parsed_url.path.lower()
        return path.endswith('.xml') or path.endswith('.xml.gz')
    
    def _filter_sitemap_path_keyword(self, parsed_url) -> bool:
        """过滤路径中包含sitemap关键词的URL
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果路径中含有sitemap关键词，返回True；否则返回False
        """
        path = parsed_url.path.lower()
        return '/sitemap' in path or 'sitemap.' in path or '/sitemaps/' in path
    
    def _filter_sitemap_filename_keyword(self, parsed_url) -> bool:
        """过滤文件名包含sitemap关键词的URL
        
        Args:
            parsed_url: 解析后的URL对象
            
        Returns:
            如果文件名包含sitemap关键词，返回True；否则返回False
        """
        path_parts = parsed_url.path.strip('/').split('/')
        if not path_parts:
            return False
            
        filename = path_parts[-1].lower()
        return ('sitemap' in filename or 
                filename.startswith('sm-') or 
                (len(path_parts) > 1 and 'sitemap' in ''.join(path_parts[-2:])))

    # ===== 注册新的过滤规则 =====
    
    def register_filter(self, name: str, filter_func: Callable) -> None:
        """注册新的过滤规则
        
        Args:
            name: 过滤规则名称
            filter_func: 过滤函数，接收ParseResult对象，返回布尔值
        """
        if name in self.filters:
            logger.warning(f"过滤规则'{name}'已存在，将被覆盖")
        
        self.filters[name] = filter_func
        logger.info(f"已注册新的过滤规则: {name}")


class KeywordExtractor:
    """从URL中提取关键词"""

    def __init__(self):
        """初始化提取器"""
        # 创建URL过滤器
        self.url_filter = URLFilter()

    def extract_keywords_from_url(self, url: str) -> str:
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
            
            # 预处理：检查URL是否应该被排除
            if self.url_filter.should_exclude(parsed_url):
                return ""

            # 如果路径为空则返回空字符串
            if not path_parts:
                return ""

            # 1. 检查是否为纯数字路径（如 /sitemap/games/33）
            if path_parts[-1].isdigit():
                # 路径以纯数字结尾，跳过关键词提取
                return ""

            # 检查路径的最后部分是否以.games结尾
            if path_parts[-1].endswith('.games'):
                # 路径以.games结尾，跳过关键词提取
                return ""

            # 2.a 新规则: 匹配 /game/[id]/[name].html 格式
            if len(path_parts) >= 3 and path_parts[0] == "game" and path_parts[1].isdigit():
                # 移除文件扩展名
                base_name = path_parts[2]
                if "." in base_name:
                    base_name = base_name.split('.')[0]  # 移除扩展名
                keywords = base_name.replace('-', ' ')
                # logger.debug(f"从带ID的游戏URL提取关键词: {keywords}")
                return keywords

            # 2.b 检查网站特定结构
            # 例如: /game/territory-war 中，提取 territory-war 作为关键词
            elif len(path_parts) >= 2 and path_parts[-2] == "game":
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
            
            # 移除文件扩展名
            if "." in last_part:
                last_part = last_part.split('.')[0]  # 移除扩展名

            # 将连字符和下划线替换为空格，并清理多余空格
            keywords = last_part.replace('-', ' ').replace('_', ' ')
            # 清理连续的空格，确保关键词格式规范
            keywords = ' '.join(keywords.split())

            # 如果关键词看起来很不合理（例如太长或太短），记录日志但仍返回
            if len(keywords) < 3 or len(keywords) > 50:
                pass  # 不做任何操作，只是为了保持缩进结构
                # logger.debug(f"提取的关键词可能不合理: {keywords}, URL: {url}")

            return keywords

        except Exception as e:
            # 不输出完整URL，避免敏感信息泄露
            domain_part = PrivacyMasker.extract_domain_safely(url)
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

    @staticmethod
    def normalize_keyword(keyword: str) -> str:
        """统一的关键词规范化函数 - 增强版本，符合seokey API要求

        Args:
            keyword: 原始关键词

        Returns:
            规范化后的关键词，如果无效则返回空字符串
        """
        if not keyword or not isinstance(keyword, str):
            return ""

        # 基本清理
        normalized = keyword.strip().lower()

        # 检查是否为空或只有空格
        if not normalized or normalized.isspace():
            return ""

        # 移除多余的空格和换行符
        normalized = ' '.join(normalized.split())

        # 检查是否包含非英文字符（seokey API主要支持英文）
        import re
        if re.search(r'[^\x00-\x7F]', normalized):
            # 包含非ASCII字符，可能不被API支持
            return ""

        # 移除特殊字符，但保留一些游戏常用的字符
        # 保留：字母、数字、空格、连字符、单引号（如papa's）
        normalized = re.sub(r'[^\w\s\-\']', ' ', normalized)

        # 再次清理多余空格
        normalized = ' '.join(normalized.split())

        # 检查长度限制
        if len(normalized) < 2:  # 太短的关键词可能无意义
            return ""
        elif len(normalized) > 80:  # 太长的关键词可能导致API问题
            normalized = normalized[:80].strip()

        # 检查是否只包含停用词
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = normalized.split()
        meaningful_words = [w for w in words if w not in stop_words]

        if not meaningful_words:  # 只包含停用词
            return ""

        return normalized

# 创建全局提取器实例
keyword_extractor = KeywordExtractor()
