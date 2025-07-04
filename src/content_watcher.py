#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容监控器 - 轻量级适配器实现
遵循SOLID原则，复用现有组件，零技术债务
"""

import logging
import time
from typing import Dict, Set, List, Any
from urllib.parse import urlparse

from src.site_data_collector import SiteDataCollector
from src.site_update_processor import SiteUpdateProcessor
from src.config import config

logger = logging.getLogger(__name__)


class ContentWatcher:
    """内容监控器 - 适配器模式实现
    
    职责：
    1. 编排网站监控流程
    2. 协调数据收集和处理组件
    3. 提供统一的监控接口
    
    遵循原则：
    - 单一职责：仅负责流程编排
    - 开闭原则：通过依赖注入支持扩展
    - 依赖倒置：依赖抽象接口而非具体实现
    """
    
    def __init__(self, test_mode: bool = False):
        """初始化监控器
        
        Args:
            test_mode: 是否在测试模式下运行
        """
        self.test_mode = test_mode
        
        # 依赖注入 - 符合依赖倒置原则
        self._site_collector = SiteDataCollector()
        self._update_processor = SiteUpdateProcessor()
        
        logger.info(f"ContentWatcher初始化完成 - 测试模式: {test_mode}")
    
    def run(self) -> None:
        """执行监控流程
        
        流程：
        1. 收集所有网站数据
        2. 查询关键词数据
        3. 处理和保存更新
        4. 显示统计信息
        """
        try:
            start_time = time.time()
            logger.info("开始执行内容监控")
            
            # 第一阶段：收集网站数据
            all_site_data = self._collect_all_sites_data()
            
            if not all_site_data:
                logger.info("没有发现任何网站更新")
                return
            
            # 第二阶段：查询关键词数据
            global_keyword_data = self._query_keywords_data(all_site_data)
            
            # 第三阶段：处理更新
            self._process_all_updates(all_site_data, global_keyword_data)
            
            # 第四阶段：显示统计
            self._display_statistics(all_site_data)
            
            elapsed_time = time.time() - start_time
            logger.info(f"内容监控完成，耗时: {elapsed_time:.2f}秒")
            
        except Exception as e:
            logger.error(f"内容监控执行失败: {e}")
            raise
    
    def _collect_all_sites_data(self) -> Dict[str, Dict[str, Any]]:
        """收集所有网站数据
        
        Returns:
            Dict[site_id, site_data]: 网站数据字典
        """
        all_site_data = {}
        
        logger.info(f"开始收集 {len(config.website_urls)} 个网站的数据")
        
        for index, url in enumerate(config.website_urls):
            try:
                logger.info(f"处理网站 {index + 1}/{len(config.website_urls)}: {self._mask_url(url)}")
                
                site_id, site_data = self._site_collector.collect_site_data(url, index)
                
                if site_data.get('updated_urls'):
                    all_site_data[site_id] = site_data
                    logger.info(f"网站 {site_id} 发现 {len(site_data['updated_urls'])} 个更新")
                else:
                    logger.info(f"网站 {site_id} 没有发现更新")
                    
            except Exception as e:
                logger.error(f"收集网站数据失败: {self._mask_url(url)}, 错误: {e}")
                continue
        
        logger.info(f"数据收集完成，{len(all_site_data)} 个网站有更新")
        return all_site_data
    
    def _query_keywords_data(self, all_site_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """查询关键词数据
        
        Args:
            all_site_data: 所有网站数据
            
        Returns:
            Dict[keyword, data]: 关键词数据字典
        """
        # 收集所有关键词
        all_keywords = set()
        for site_data in all_site_data.values():
            all_keywords.update(site_data.get('keywords', []))
        
        if not all_keywords:
            logger.info("没有需要查询的关键词")
            return {}
        
        logger.info(f"开始查询 {len(all_keywords)} 个关键词的数据")
        
        try:
            from src.keyword_api_multi import multi_api_manager
            global_keyword_data = multi_api_manager.batch_query_keywords_parallel(list(all_keywords))
            
            success_count = len([k for k, v in global_keyword_data.items() if v])
            logger.info(f"关键词查询完成: {success_count}/{len(all_keywords)} 成功")
            
            return global_keyword_data
            
        except Exception as e:
            logger.error(f"关键词查询失败: {e}")
            return {}
    
    def _process_all_updates(self, all_site_data: Dict[str, Dict[str, Any]], 
                           global_keyword_data: Dict[str, Any]) -> None:
        """处理所有网站更新
        
        Args:
            all_site_data: 所有网站数据
            global_keyword_data: 全局关键词数据
        """
        logger.info("开始处理网站更新")
        
        total_processed = 0
        
        for site_id, site_data in all_site_data.items():
            try:
                url_keywords_map = site_data.get('url_keywords_map', {})
                
                processed_urls = self._update_processor.process_site_updates(
                    site_id, site_data, url_keywords_map, global_keyword_data
                )
                
                total_processed += len(processed_urls)
                logger.info(f"网站 {site_id} 处理了 {len(processed_urls)} 个URL")
                
            except Exception as e:
                logger.error(f"处理网站 {site_id} 更新失败: {e}")
                continue
        
        logger.info(f"更新处理完成，总计处理 {total_processed} 个URL")
    
    def _display_statistics(self, all_site_data: Dict[str, Dict[str, Any]]) -> None:
        """显示统计信息
        
        Args:
            all_site_data: 所有网站数据
        """
        logger.info("=" * 50)
        logger.info("监控统计信息")
        logger.info("=" * 50)
        
        total_sites = len(config.website_urls)
        updated_sites = len(all_site_data)
        total_urls = sum(len(site_data.get('updated_urls', [])) for site_data in all_site_data.values())
        total_keywords = len(set().union(*(site_data.get('keywords', []) for site_data in all_site_data.values())))
        
        logger.info(f"总网站数: {total_sites}")
        logger.info(f"有更新的网站数: {updated_sites}")
        logger.info(f"总更新URL数: {total_urls}")
        logger.info(f"总关键词数: {total_keywords}")
        
        if self.test_mode:
            logger.info("测试模式运行完成")
    
    def _mask_url(self, url: str) -> str:
        """遮蔽URL敏感信息
        
        Args:
            url: 原始URL
            
        Returns:
            str: 遮蔽后的URL（仅显示域名）
        """
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return "***"


# 向后兼容性支持
__all__ = ['ContentWatcher']
