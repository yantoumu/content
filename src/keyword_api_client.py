#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词API客户端模块
处理与关键词API的交互
"""

import json
import logging
import time
from typing import Dict, List, Any, Union, Optional

import requests

from src.config import config

class KeywordAPIClient:
    """处理与关键词API的交互"""

    def __init__(self, api_url=None, headers=None, timeout=80):
        """初始化API客户端

        Args:
            api_url: API基础URL，如果为None则从配置中获取
            headers: 请求头，默认为None
            timeout: 请求超时时间，默认为80秒
        """
        self.api_url = api_url or config.keywords_api_url
        self.headers = headers or {}
        self.timeout = timeout
        self.logger = logging.getLogger('content_watcher.keyword_api')

        # 创建一个会话对象，用于复用连接
        self.session = requests.Session()
        # 设置默认请求头
        self.session.headers.update(self.headers)

    def get_keyword_data(self, keywords: Union[str, List[str]], max_retries: int = 2) -> Dict[str, Any]:
        """获取关键词数据

        Args:
            keywords: 关键词字符串或列表
            max_retries: 最大重试次数

        Returns:
            关键词数据字典
        """
        # 如果输入是列表，转换为逗号分隔的字符串
        if isinstance(keywords, list):
            keywords = ",".join(keywords)

        # 如果没有关键词或API URL，返回空结果
        if not keywords or not self.api_url:
            return self._create_empty_result(keywords)

        # 尝试从API获取数据
        result = self._fetch_from_api(keywords, max_retries)

        # 如果API调用失败，创建默认数据
        if not result or result.get('status') != 'success':
            self.logger.warning(f"无法从API获取关键词数据: {keywords}")
            return self._create_empty_result(keywords)

        return result

    def batch_query_keywords(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """批量查询关键词信息

        Args:
            keywords_list: 关键词列表
            max_retries: 最大重试次数

        Returns:
            关键词数据字典，键为关键词，值为API返回的数据
        """
        if not keywords_list or not self.api_url:
            return {}

        # 对关键词列表进行去重，避免重复查询
        # 使用字典而不是列表来存储关键词，提高查找效率
        unique_keywords = {}
        for kw in keywords_list:
            unique_keywords[kw.lower()] = kw  # 使用小写作为键，原始关键词作为值

        self.logger.debug(f"关键词去重: 原始数量 {len(keywords_list)}, 去重后数量 {len(unique_keywords)}")

        keyword_data = {}
        batch_size = 10  # 增加批处理大小以提高效率

        # 使用队列来管理关键词批次，便于失败重试
        from collections import deque
        keyword_queue = deque()

        # 将关键词分批加入队列
        unique_kw_list = list(unique_keywords.values())
        for i in range(0, len(unique_kw_list), batch_size):
            batch = unique_kw_list[i:i + batch_size]
            keyword_queue.append(batch)

        # 记录失败的关键词批次，用于最终报告
        failed_batches = []

        # 处理队列中的所有批次
        while keyword_queue:
            batch = keyword_queue.popleft()
            combined_keywords = ",".join(batch)

            # 获取批次数据
            batch_result = self.get_keyword_data(combined_keywords, max_retries)

            if batch_result and 'data' in batch_result:
                # 处理返回的数据
                for item in batch_result.get('data', []):
                    keyword = item.get('keyword', '')
                    if not keyword:
                        continue

                    # 标准化月份名称，确保匹配一致性
                    if 'metrics' in item and 'monthly_searches' in item['metrics']:
                        for month_data in item['metrics']['monthly_searches']:
                            if 'month' in month_data:
                                # 如果月份是字符串，转换为大写
                                if isinstance(month_data['month'], str):
                                    month_data['month'] = month_data['month'].upper()
                                # 如果是整数，保持不变

                    # 记录关键词数据 - 直接使用API返回的数据，不需要额外过滤
                    if keyword in keyword_data:
                        # 如果关键词已存在，更新数据
                        keyword_data[keyword].update(item)
                        # 只在调试级别输出成功日志
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(f"更新关键词数据: {keyword}")
                    else:
                        keyword_data[keyword] = item
                        # 只在调试级别输出成功日志
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(f"新增关键词数据: {keyword}")

                    # 记录月度数据数量 - 只在调试级别输出
                    monthly_searches = item.get('metrics', {}).get('monthly_searches', [])
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(f"成功获取关键词数据: {keyword}, 包含 {len(monthly_searches)} 个月度数据")
            else:
                # 批次处理失败，记录失败信息
                self.logger.warning(f"批次处理失败: {combined_keywords}")
                failed_batches.append(batch)

                # 为失败的关键词创建默认数据
                for kw in batch:
                    if kw not in keyword_data:
                        keyword_data[kw] = {
                            'keyword': kw,
                            'metrics': {
                                'avg_monthly_searches': 0,
                                'competition': 'LOW',
                                'competition_index': '0',
                                'monthly_searches': []
                            }
                        }
                        self.logger.info(f"为关键词创建默认数据: {kw}")

        # 如果有失败的批次，记录总结信息
        if failed_batches:
            failed_count = sum(len(batch) for batch in failed_batches)
            self.logger.warning(f"共有 {len(failed_batches)} 个批次 ({failed_count} 个关键词) 查询失败")

        return keyword_data

    def _fetch_from_api(self, keywords: str, max_retries: int) -> Optional[Dict[str, Any]]:
        """从API获取数据，处理重试逻辑

        Args:
            keywords: 关键词字符串
            max_retries: 最大重试次数

        Returns:
            API响应数据或None
        """
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # 构建请求URL
                request_url = f"{self.api_url}{keywords}"
                # 不输出完整URL，避免敏感信息泄露
                domain_part = self.api_url.split('/')[2] if '/' in self.api_url else '***'
                self.logger.debug(f"请求关键词API，域名: {domain_part}, 关键词数量: {len(keywords.split(','))}")

                # 使用session发送请求，复用连接
                response = self.session.get(
                    request_url,
                    timeout=self.timeout
                )

                # 处理响应
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        self.logger.error(f"API返回非JSON数据: {keywords}")
                        return None
                elif self._should_retry(response.status_code):
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = self._calculate_wait_time(retry_count)
                        self.logger.warning(f"API请求返回{response.status_code}，将在{wait_time}秒后重试")
                        time.sleep(wait_time)
                        continue

                self.logger.error(f"API请求失败: {response.status_code}")
                return None

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = self._calculate_wait_time(retry_count)
                    self.logger.warning(f"API请求异常: {e.__class__.__name__}，将在{wait_time}秒后重试")
                    time.sleep(wait_time)
                    continue

                self.logger.error(f"API请求异常，重试次数超过上限: {e}")
                return None
            except Exception as e:
                self.logger.error(f"API请求发生未预期的异常: {e}")
                return None

        return None

    def _should_retry(self, status_code: int) -> bool:
        """判断是否应该重试请求

        Args:
            status_code: HTTP状态码

        Returns:
            布尔值，表示是否应该重试
        """
        return status_code in [429, 500, 502, 503, 504]

    def _calculate_wait_time(self, retry_count: int) -> int:
        """计算重试等待时间

        Args:
            retry_count: 当前重试次数

        Returns:
            等待时间（秒）
        """
        return 2 ** retry_count  # 指数退避: 2, 4, 8...

    def _create_empty_result(self, keywords: Union[str, List[str]]) -> Dict[str, Any]:
        """创建空的结果数据

        Args:
            keywords: 关键词字符串或列表

        Returns:
            包含空数据的结果字典
        """
        # 如果输入是字符串，拆分为列表
        if isinstance(keywords, str):
            keywords_list = [k.strip() for k in keywords.split(',') if k.strip()]
        else:
            keywords_list = keywords

        # 创建结果数据
        result = {
            'status': 'error',
            'data': []
        }

        # 为每个关键词创建空数据
        for keyword in keywords_list:
            result['data'].append({
                'keyword': keyword,
                'metrics': {
                    'avg_monthly_searches': 0,
                    'competition': 'LOW',
                    'competition_index': '0',
                    'monthly_searches': []
                }
            })

        return result

    def close(self):
        """关闭会话连接

        在不再需要使用API客户端时调用此方法
        """
        if hasattr(self, 'session') and self.session:
            self.logger.debug("关闭API客户端会话")
            self.session.close()

    def __del__(self):
        """析构函数，确保在对象被垃圾回收时关闭会话"""
        self.close()

# 创建API客户端实例
keyword_api_client = KeywordAPIClient()
