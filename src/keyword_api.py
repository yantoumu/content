#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词API交互模块
处理与关键词API的交互
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional, Union
from collections import deque

import requests

from src.config import config
from src.data_manager import data_manager
from src.api_health_monitor import api_health_monitor

# 配置日志
logger = logging.getLogger('content_watcher.keyword_api')

class KeywordAPI:
    """处理与关键词API的交互

    合并了KeywordAPI和KeywordAPIClient的功能，提供统一的API交互接口
    """

    def __init__(self, api_url=None, headers=None, timeout=None):
        """初始化API交互器

        Args:
            api_url: API基础URL，如果为None则从配置中获取第一个
            headers: 请求头，默认为None
            timeout: 请求超时时间，默认使用配置值
        """
        self.api_url = api_url or (config.keywords_api_urls[0] if config.keywords_api_urls and len(config.keywords_api_urls) > 0 else '')
        self.headers = headers or {}
        # 添加gzip压缩头
        if 'Accept-Encoding' not in self.headers:
            self.headers['Accept-Encoding'] = 'gzip, deflate'
        self.timeout = timeout or config.keyword_query_timeout  # 使用配置的超时时间
        self.logger = logging.getLogger('content_watcher.keyword_api')

        # API健康状态跟踪 - 新增
        self.consecutive_failures = 0
        self.last_success_time = time.time()
        self.is_circuit_open = False
        self.circuit_open_time = None

        # 创建一个会话对象，用于复用连接
        self.session = requests.Session()
        # 设置默认请求头
        self.session.headers.update(self.headers)

        # 注册到健康监控器
        if self.api_url:
            api_health_monitor.register_api(self.api_url)

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

        # 如果没有关键词或API URL，返回None表示无法查询
        if not keywords or not self.api_url:
            self.logger.warning("缺少关键词或API URL，跳过查询")
            return None

        # 尝试从API获取数据
        result = self._fetch_from_api(keywords, max_retries)

        # 如果API调用失败，返回None而不是创建虚假数据
        if not result or result.get('status') != 'success':
            from src.privacy_utils import PrivacyMasker
            masked_keywords = PrivacyMasker.mask_keyword(keywords)
            self.logger.warning(f"无法从API获取关键词数据，跳过: {masked_keywords}")
            return None

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
        from src.keyword_extractor import keyword_extractor
        unique_keywords = {}
        for kw in keywords_list:
            normalized_kw = keyword_extractor.normalize_keyword(kw)
            if normalized_kw:  # 只处理有效的关键词
                unique_keywords[normalized_kw] = kw  # 使用规范化关键词作为键，原始关键词作为值

        self.logger.debug(f"关键词去重: 原始数量 {len(keywords_list)}, 去重后数量 {len(unique_keywords)}")

        keyword_data = {}
        # 使用配置中的批处理大小，而不是硬编码
        batch_size = config.keywords_batch_size
        
        # 记录批处理配置信息（仅调试级别）
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"使用批处理大小: {batch_size}")

        # 使用队列来管理关键词批次，便于失败重试
        keyword_queue = deque()

        # 将关键词分批加入队列
        unique_kw_list = list(unique_keywords.values())
        for i in range(0, len(unique_kw_list), batch_size):
            batch = unique_kw_list[i:i + batch_size]
            keyword_queue.append(batch)

        # 记录批次信息（仅调试级别）
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"创建 {len(keyword_queue)} 个批次，每批最多 {batch_size} 个关键词")

        # 记录失败的关键词批次，用于最终报告
        failed_batches = []

        # 处理队列中的所有批次
        while keyword_queue:
            batch = keyword_queue.popleft()
            combined_keywords = ",".join(batch)

            # 验证批次大小是否符合配置
            if len(batch) > config.keywords_batch_size:
                self.logger.warning(f"批次大小({len(batch)})超过配置限制({config.keywords_batch_size})")

            # 获取批次数据
            batch_result = self.get_keyword_data(combined_keywords, max_retries)

            if batch_result and batch_result.get('status') == 'success' and 'data' in batch_result:
                # 处理返回的数据
                for item in batch_result.get('data', []):
                    keyword = item.get('keyword', '')
                    if not keyword:
                        continue

                    # 直接使用API返回的新JSON格式数据

                    # 记录关键词数据 - 直接使用API返回的数据，不需要额外过滤
                    if keyword in keyword_data:
                        # 如果关键词已存在，更新数据
                        keyword_data[keyword].update(item)
                        # 只在调试级别输出成功日志
                        if self.logger.isEnabledFor(logging.DEBUG):
                            from src.privacy_utils import PrivacyMasker
                            masked_keyword = PrivacyMasker.mask_keyword(keyword)
                            self.logger.debug(f"更新关键词数据: {masked_keyword}")
                    else:
                        keyword_data[keyword] = item
                        # 只在调试级别输出成功日志
                        if self.logger.isEnabledFor(logging.DEBUG):
                            from src.privacy_utils import PrivacyMasker
                            masked_keyword = PrivacyMasker.mask_keyword(keyword)
                            self.logger.debug(f"新增关键词数据: {masked_keyword}")

                    # 记录月度数据数量 - 只在调试级别输出
                    monthly_searches = item.get('metrics', {}).get('monthly_searches', [])
                    if self.logger.isEnabledFor(logging.DEBUG):
                        from src.privacy_utils import PrivacyMasker
                        masked_keyword = PrivacyMasker.mask_keyword(keyword)
                        self.logger.debug(f"成功获取关键词数据: {masked_keyword}, 包含 {len(monthly_searches)} 个月度数据")
            else:
                # 批次处理失败，记录失败信息
                if batch_result is None:
                    self.logger.warning(f"批次查询返回None，跳过: {len(batch)} 个关键词")
                else:
                    self.logger.warning(f"批次查询失败，跳过: {len(batch)} 个关键词")
                failed_batches.append(batch)

                # 记录失败的关键词，但不创建虚假数据
                self.logger.warning(f"跳过 {len(batch)} 个查询失败的关键词")

        # 如果有失败的批次，记录总结信息
        if failed_batches:
            failed_count = sum(len(batch) for batch in failed_batches)
            self.logger.warning(f"共有 {len(failed_batches)} 个批次 ({failed_count} 个关键词) 查询失败")

        return keyword_data

    def _fetch_from_api(self, keywords: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
        """从API获取数据，处理重试逻辑 - 针对API 500错误优化

        Args:
            keywords: 关键词字符串
            max_retries: 最大重试次数，默认使用配置值

        Returns:
            API响应数据或None
        """
        # 检查API是否可用
        if not api_health_monitor.is_api_available(self.api_url):
            from src.privacy_utils import PrivacyMasker
            masked_url = PrivacyMasker.mask_api_url(self.api_url)
            self.logger.warning(f"API不可用，跳过请求: {masked_url}")
            return None

        max_retries = max_retries or config.api_retry_max
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # 构建请求URL
                request_url = f"{self.api_url}{keywords}"
                keyword_count = len(keywords.split(','))
                self.logger.debug(f"请求关键词API，关键词数量: {keyword_count}")

                # 使用自适应批处理大小验证
                adaptive_batch_size = api_health_monitor.get_adaptive_batch_size(self.api_url)
                if keyword_count > adaptive_batch_size:
                    self.logger.warning(f"单次请求关键词数量({keyword_count})超出自适应限制({adaptive_batch_size})")

                # 记录请求开始时间
                request_start_time = time.time()

                # 使用session发送请求，复用连接
                response = self.session.get(
                    request_url,
                    timeout=self.timeout
                )

                # 计算响应时间
                response_time = time.time() - request_start_time

                # 处理响应
                if response.status_code == 200:
                    try:
                        result = response.json()
                        # 记录成功请求到健康监控器
                        api_health_monitor.record_request(self.api_url, True, response_time)
                        return result
                    except json.JSONDecodeError:
                        from src.privacy_utils import PrivacyMasker
                        masked_keywords = PrivacyMasker.mask_keyword(keywords)
                        self.logger.error(f"API返回非JSON数据: {masked_keywords}")
                        # 记录失败请求到健康监控器
                        api_health_monitor.record_request(self.api_url, False, response_time)
                        return None
                elif self._should_retry(response.status_code):
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = self._calculate_wait_time(retry_count)
                        # 显示关键词信息用于调试，但不输出完整关键词内容
                        from src.privacy_utils import PrivacyMasker
                        masked_keywords = PrivacyMasker.mask_keyword(keywords)
                        self.logger.warning(f"API请求返回{response.status_code}，将在{wait_time:.1f}秒后重试")
                        self.logger.warning(f"请求的关键词: {masked_keywords} (共{keyword_count}个)")

                        # 记录失败请求到健康监控器
                        api_health_monitor.record_request(self.api_url, False, response_time)

                        # 使用自适应间隔以减少API压力
                        adaptive_interval = api_health_monitor.get_adaptive_interval(self.api_url)
                        time.sleep(wait_time + adaptive_interval)
                        continue

                # 显示失败信息，但不输出完整关键词内容
                from src.privacy_utils import PrivacyMasker
                masked_keywords = PrivacyMasker.mask_keyword(keywords)
                self.logger.error(f"API请求失败: {response.status_code}")
                self.logger.error(f"请求的关键词: {masked_keywords} (共{keyword_count}个)")
                # 记录失败请求到健康监控器
                api_health_monitor.record_request(self.api_url, False, response_time)
                return None

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = self._calculate_wait_time(retry_count)
                    from src.privacy_utils import PrivacyMasker
                    masked_keywords = PrivacyMasker.mask_keyword(keywords)
                    self.logger.warning(f"API请求异常: {e.__class__.__name__}，将在{wait_time}秒后重试")
                    masked_url = PrivacyMasker.mask_api_url(request_url)
                    self.logger.warning(f"异常的API URL: {masked_url}")
                    self.logger.warning(f"请求的关键词: {masked_keywords} (共{keyword_count}个)")
                    time.sleep(wait_time)
                    continue

                from src.privacy_utils import PrivacyMasker
                masked_keywords = PrivacyMasker.mask_keyword(keywords)
                self.logger.error(f"API请求异常，重试次数超过上限: {e}")
                masked_url = PrivacyMasker.mask_api_url(request_url)
                self.logger.error(f"异常的API URL: {masked_url}")
                self.logger.error(f"请求的关键词: {masked_keywords} (共{keyword_count}个)")
                return None

            except Exception as e:
                from src.privacy_utils import PrivacyMasker
                masked_keywords = PrivacyMasker.mask_keyword(keywords)
                self.logger.error(f"API请求发生未预期的异常: {e}")
                masked_url = PrivacyMasker.mask_api_url(request_url)
                self.logger.error(f"异常的API URL: {masked_url}")
                self.logger.error(f"请求的关键词: {masked_keywords} (共{keyword_count}个)")
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

    def _calculate_wait_time(self, retry_count: int) -> float:
        """计算重试等待时间 - 性能优化：使用线性增长减少等待时间

        Args:
            retry_count: 当前重试次数

        Returns:
            等待时间（秒）
        """
        # 使用线性增长而非指数增长，减少总等待时间
        # 第1次重试: 3秒, 第2次: 6秒, 第3次: 12秒
        wait_times = [3, 6, 12]
        if retry_count <= len(wait_times):
            return wait_times[retry_count - 1]
        else:
            return 15  # 超过3次重试时固定15秒

    def _check_circuit_breaker(self) -> bool:
        """检查熔断器状态"""
        if not self.is_circuit_open:
            return False

        # 检查是否应该尝试恢复
        if time.time() - self.circuit_open_time > config.api_health_check_interval:
            from src.privacy_utils import PrivacyMasker
            masked_url = PrivacyMasker.mask_api_url(self.api_url)
            self.logger.info(f"尝试恢复API连接: {masked_url}")
            self.is_circuit_open = False
            self.circuit_open_time = None
            return False

        return True

    def _update_api_health(self, success: bool):
        """更新API健康状态"""
        if success:
            self.consecutive_failures = 0
            self.last_success_time = time.time()
            if self.is_circuit_open:
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(self.api_url)
                self.logger.info(f"API恢复正常: {masked_url}")
                self.is_circuit_open = False
                self.circuit_open_time = None
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= config.api_circuit_breaker_threshold:
                if not self.is_circuit_open:
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(self.api_url)
                    self.logger.warning(f"API熔断器开启: {masked_url} (连续失败{self.consecutive_failures}次)")
                    self.is_circuit_open = True
                    self.circuit_open_time = time.time()



    def close(self):
        """关闭会话"""
        try:
            if hasattr(self, 'session') and self.session:
                self.session.close()
                self.logger.debug("关闭关键词API会话")
        except (AttributeError, OSError) as e:
            self.logger.warning(f"关闭关键词API会话时出错: {e}")
        except Exception as e:
            self.logger.error(f"关闭关键词API会话时发生未预期错误: {e}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，确保资源释放"""
        self.close()

    def __del__(self):
        """析构函数，确保会话被关闭"""
        self.close()


# 创建全局API交互器实例
keyword_api = KeywordAPI()
