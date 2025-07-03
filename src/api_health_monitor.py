#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API健康监控模块
监控API状态，实现自适应调整和熔断机制
"""

import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from threading import Lock

from src.config import config

logger = logging.getLogger('content_watcher.api_health_monitor')


@dataclass
class APIHealthStatus:
    """API健康状态数据类"""
    url: str
    consecutive_failures: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    last_success_time: float = 0
    last_failure_time: float = 0
    is_circuit_open: bool = False
    circuit_open_time: Optional[float] = None
    average_response_time: float = 0
    recent_response_times: List[float] = None

    def __post_init__(self):
        if self.recent_response_times is None:
            self.recent_response_times = []
        if self.last_success_time == 0:
            self.last_success_time = time.time()

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def is_healthy(self) -> bool:
        """判断API是否健康"""
        return (not self.is_circuit_open and 
                self.consecutive_failures < config.api_circuit_breaker_threshold and
                self.success_rate > 0.5)


class APIHealthMonitor:
    """API健康监控器"""

    def __init__(self):
        self.api_status: Dict[str, APIHealthStatus] = {}
        self.lock = Lock()
        self.logger = logging.getLogger('content_watcher.api_health_monitor')

    def register_api(self, api_url: str):
        """注册API进行监控"""
        with self.lock:
            if api_url not in self.api_status:
                self.api_status[api_url] = APIHealthStatus(url=api_url)
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(api_url)
                self.logger.debug(f"注册API监控: {masked_url}")

    def record_request(self, api_url: str, success: bool, response_time: float = 0):
        """记录API请求结果"""
        with self.lock:
            if api_url not in self.api_status:
                self.register_api(api_url)
            
            status = self.api_status[api_url]
            status.total_requests += 1
            
            if success:
                status.successful_requests += 1
                status.consecutive_failures = 0
                status.last_success_time = time.time()
                
                # 记录响应时间
                if response_time > 0:
                    status.recent_response_times.append(response_time)
                    # 只保留最近10次的响应时间
                    if len(status.recent_response_times) > 10:
                        status.recent_response_times.pop(0)
                    status.average_response_time = sum(status.recent_response_times) / len(status.recent_response_times)
                
                # 如果熔断器开启，尝试恢复
                if status.is_circuit_open:
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.info(f"API恢复正常，关闭熔断器: {masked_url}")
                    status.is_circuit_open = False
                    status.circuit_open_time = None
            else:
                status.consecutive_failures += 1
                status.last_failure_time = time.time()
                
                # 检查是否需要开启熔断器
                if (status.consecutive_failures >= config.api_circuit_breaker_threshold and 
                    not status.is_circuit_open):
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.warning(f"API连续失败{status.consecutive_failures}次，开启熔断器: {masked_url}")
                    status.is_circuit_open = True
                    status.circuit_open_time = time.time()

    def is_api_available(self, api_url: str) -> bool:
        """检查API是否可用 - 针对seokey API优化"""
        with self.lock:
            if api_url not in self.api_status:
                return True  # 未知API默认可用

            status = self.api_status[api_url]

            # 如果熔断器开启，检查是否可以尝试恢复 - 缩短恢复时间
            if status.is_circuit_open:
                recovery_interval = min(config.api_health_check_interval, 15)  # 最多15秒后尝试恢复
                if (time.time() - status.circuit_open_time > recovery_interval):
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.info(f"尝试恢复seokey API: {masked_url}")
                    # 重置熔断器状态
                    status.is_circuit_open = False
                    status.consecutive_failures = 0
                    return True  # 允许一次尝试
                return False

            return status.is_healthy

    def get_best_api(self, api_urls: List[str]) -> Optional[str]:
        """获取最佳API地址"""
        available_apis = []
        
        with self.lock:
            for api_url in api_urls:
                if self.is_api_available(api_url):
                    status = self.api_status.get(api_url)
                    if status:
                        # 根据成功率和响应时间评分
                        score = status.success_rate * 100 - status.average_response_time
                        available_apis.append((api_url, score))
                    else:
                        available_apis.append((api_url, 100))  # 新API给高分
        
        if not available_apis:
            return None
        
        # 返回评分最高的API
        available_apis.sort(key=lambda x: x[1], reverse=True)
        return available_apis[0][0]

    def get_health_summary(self) -> Dict[str, Dict]:
        """获取健康状态摘要"""
        summary = {}
        with self.lock:
            for api_url, status in self.api_status.items():
                summary[api_url] = {
                    'is_healthy': status.is_healthy,
                    'success_rate': status.success_rate,
                    'consecutive_failures': status.consecutive_failures,
                    'total_requests': status.total_requests,
                    'is_circuit_open': status.is_circuit_open,
                    'average_response_time': status.average_response_time
                }
        return summary

    def reset_api_status(self, api_url: str):
        """重置API状态"""
        with self.lock:
            if api_url in self.api_status:
                self.api_status[api_url] = APIHealthStatus(url=api_url)
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(api_url)
                self.logger.info(f"重置API状态: {masked_url}")

    def get_adaptive_batch_size(self, api_url: str) -> int:
        """根据API健康状态获取自适应批处理大小 - 根据seokey API限制"""
        with self.lock:
            # 根据seokey API限制，最大支持5个关键词/请求
            if api_url not in self.api_status:
                return 5  # 默认使用最大批次

            status = self.api_status[api_url]

            # 根据健康状态动态调整批次大小
            if status.success_rate > 0.9:
                return 5  # 健康状态良好
            elif status.success_rate > 0.7:
                return 4  # 健康状态一般
            elif status.success_rate > 0.5:
                return 3  # 健康状态较差
            else:
                return 2  # 健康状态很差，使用最小批次

    def get_adaptive_interval(self, api_url: str) -> float:
        """根据API健康状态获取自适应请求间隔 - 根据seokey API特性调整"""
        with self.lock:
            base_interval = max(config.api_request_interval, 2.0)  # 确保至少2秒间隔

            if api_url not in self.api_status:
                return base_interval

            status = self.api_status[api_url]

            # 根据连续失败次数调整间隔，特别针对500错误
            if status.consecutive_failures > 0:
                # 对于seokey API，500错误时需要更长的等待时间
                multiplier = min(status.consecutive_failures + 1, 4)  # 最多4倍间隔
                return base_interval * multiplier
            elif status.success_rate > 0.95:
                return base_interval  # 成功率很高时保持基础间隔
            elif status.success_rate > 0.8:
                return base_interval * 1.2  # 成功率较高时稍微增加间隔
            else:
                return base_interval * 1.5  # 成功率较低时增加间隔


# 创建全局健康监控器实例
api_health_monitor = APIHealthMonitor()
