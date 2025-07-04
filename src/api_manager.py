#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API管理器 - 遵循SOLID原则的API调用管理
解决批量大小过大、缺少健康检查和重试机制问题
"""

import time
import asyncio
import logging
import requests
from typing import Any, Dict, List, Optional, Callable, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, Future
import queue

from src.config_manager import get_config, get_int_config, get_bool_config, get_list_config
from src.error_handler import ErrorSeverity, get_error_manager, handle_errors, error_context
from src.resource_manager import managed_session

logger = logging.getLogger(__name__)

# Interface Segregation Principle - 分离API接口
class IAPIHealthChecker(ABC):
    """API健康检查器接口"""
    
    @abstractmethod
    def check_health(self, api_url: str) -> bool:
        """检查API健康状态"""
        pass
    
    @abstractmethod
    def get_health_score(self, api_url: str) -> float:
        """获取API健康分数"""
        pass

class IRetryStrategy(ABC):
    """重试策略接口"""
    
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        pass
    
    @abstractmethod
    def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟时间"""
        pass

class IBatchProcessor(ABC):
    """批处理器接口"""
    
    @abstractmethod
    def process_batch(self, items: List[Any], processor: Callable) -> Dict[str, Any]:
        """处理批次"""
        pass

# Single Responsibility Principle - API健康状态
class APIHealthStatus(Enum):
    """API健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class APIHealth:
    """API健康信息"""
    url: str
    status: APIHealthStatus = APIHealthStatus.UNKNOWN
    response_time: float = 0.0
    success_rate: float = 0.0
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    error_message: str = ""
    
    def update_success(self, response_time: float):
        """更新成功状态"""
        self.status = APIHealthStatus.HEALTHY
        self.response_time = response_time
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_check = datetime.now()
        self.error_message = ""
    
    def update_failure(self, error_message: str):
        """更新失败状态"""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_check = datetime.now()
        self.error_message = error_message
        
        # 根据连续失败次数更新状态
        if self.consecutive_failures >= 3:
            self.status = APIHealthStatus.UNHEALTHY
        elif self.consecutive_failures >= 1:
            self.status = APIHealthStatus.DEGRADED
    
    def get_health_score(self) -> float:
        """获取健康分数 (0-1)"""
        if self.status == APIHealthStatus.HEALTHY:
            base_score = 1.0
        elif self.status == APIHealthStatus.DEGRADED:
            base_score = 0.6
        elif self.status == APIHealthStatus.UNHEALTHY:
            base_score = 0.1
        else:
            base_score = 0.5
        
        # 根据响应时间调整分数
        if self.response_time > 0:
            time_penalty = min(self.response_time / 10.0, 0.3)  # 最多扣0.3分
            base_score -= time_penalty
        
        return max(0.0, min(1.0, base_score))

# Single Responsibility Principle - 具体实现类
class HTTPHealthChecker(IAPIHealthChecker):
    """HTTP健康检查器 - 单一职责：检查HTTP API健康状态"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self._health_cache: Dict[str, APIHealth] = {}
        self._cache_timeout = 60  # 缓存60秒
    
    def check_health(self, api_url: str) -> bool:
        """检查API健康状态"""
        health_info = self._get_or_create_health_info(api_url)
        
        # 检查缓存是否过期
        if (health_info.last_check and 
            datetime.now() - health_info.last_check < timedelta(seconds=self._cache_timeout)):
            return health_info.status in [APIHealthStatus.HEALTHY, APIHealthStatus.DEGRADED]
        
        # 执行健康检查
        try:
            with managed_session() as session:
                start_time = time.time()
                
                # 构造健康检查URL（通常是基础URL）
                health_url = self._get_health_check_url(api_url)
                
                response = session.get(health_url, timeout=self.timeout)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    health_info.update_success(response_time)
                    return True
                else:
                    health_info.update_failure(f"HTTP {response.status_code}")
                    return False
        
        except Exception as e:
            health_info.update_failure(str(e))
            return False
    
    def get_health_score(self, api_url: str) -> float:
        """获取API健康分数"""
        health_info = self._get_or_create_health_info(api_url)
        return health_info.get_health_score()
    
    def _get_or_create_health_info(self, api_url: str) -> APIHealth:
        """获取或创建健康信息"""
        if api_url not in self._health_cache:
            self._health_cache[api_url] = APIHealth(url=api_url)
        return self._health_cache[api_url]
    
    def _get_health_check_url(self, api_url: str) -> str:
        """获取健康检查URL"""
        # 简单处理：移除查询参数，用于健康检查
        if '?' in api_url:
            base_url = api_url.split('?')[0]
            return base_url.rstrip('/') + '/health'
        return api_url.rstrip('/') + '/health'
    
    def get_all_health_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有API的健康状态"""
        result = {}
        for url, health in self._health_cache.items():
            result[url] = {
                'status': health.status.value,
                'response_time': health.response_time,
                'success_rate': health.success_rate,
                'consecutive_failures': health.consecutive_failures,
                'last_check': health.last_check.isoformat() if health.last_check else None,
                'health_score': health.get_health_score()
            }
        return result

class ExponentialBackoffRetry(IRetryStrategy):
    """指数退避重试策略 - 单一职责：管理重试逻辑"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        
        # 某些错误不应该重试
        non_retryable_errors = (
            ValueError,
            TypeError,
            KeyError,
            AttributeError
        )
        
        if isinstance(error, non_retryable_errors):
            return False
        
        return True
    
    def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟时间（指数退避）"""
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)

class AdaptiveBatchProcessor(IBatchProcessor):
    """自适应批处理器 - 单一职责：管理批处理逻辑"""
    
    def __init__(self, min_batch_size: int = 1, max_batch_size: int = 10):
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.current_batch_size = min_batch_size
        self._success_count = 0
        self._failure_count = 0
    
    def process_batch(self, items: List[Any], processor: Callable) -> Dict[str, Any]:
        """处理批次"""
        if not items:
            return {'results': {}, 'success_count': 0, 'failure_count': 0}
        
        # 调整批处理大小
        batch_size = self._get_adaptive_batch_size(len(items))
        results = {}
        success_count = 0
        failure_count = 0
        
        # 分批处理
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_start_time = time.time()
            
            try:
                with error_context("batch_processing", batch_size=len(batch)):
                    batch_results = processor(batch)
                    results.update(batch_results)
                    success_count += len(batch_results)
                    
                    # 记录成功
                    self._record_success(time.time() - batch_start_time)
                    
            except Exception as e:
                failure_count += len(batch)
                self._record_failure()
                logger.error(f"批处理失败 (批次大小: {len(batch)}): {e}")
        
        return {
            'results': results,
            'success_count': success_count,
            'failure_count': failure_count,
            'batch_size_used': batch_size
        }
    
    def _get_adaptive_batch_size(self, total_items: int) -> int:
        """获取自适应批处理大小"""
        # 根据成功率调整批处理大小
        if self._success_count + self._failure_count > 10:
            success_rate = self._success_count / (self._success_count + self._failure_count)
            
            if success_rate > 0.9:
                # 成功率高，增加批处理大小
                self.current_batch_size = min(self.current_batch_size + 1, self.max_batch_size)
            elif success_rate < 0.7:
                # 成功率低，减少批处理大小
                self.current_batch_size = max(self.current_batch_size - 1, self.min_batch_size)
        
        return min(self.current_batch_size, total_items)
    
    def _record_success(self, processing_time: float):
        """记录成功"""
        self._success_count += 1
        # 限制历史记录大小
        if self._success_count > 1000:
            self._success_count = 500
            self._failure_count = max(0, self._failure_count - 500)
    
    def _record_failure(self):
        """记录失败"""
        self._failure_count += 1
        # 限制历史记录大小
        if self._failure_count > 1000:
            self._failure_count = 500
            self._success_count = max(0, self._success_count - 500)

# Dependency Inversion Principle - 综合API管理器
class SmartAPIManager:
    """智能API管理器 - 协调健康检查、重试和批处理"""
    
    def __init__(self):
        self.health_checker: IAPIHealthChecker = HTTPHealthChecker(
            timeout=get_int_config('REQUEST_TIMEOUT', 30)
        )
        self.retry_strategy: IRetryStrategy = ExponentialBackoffRetry(
            max_retries=get_int_config('MAX_RETRIES', 3)
        )
        self.batch_processor: IBatchProcessor = AdaptiveBatchProcessor(
            min_batch_size=1,
            max_batch_size=get_int_config('BATCH_SIZE', 5)
        )
        
        self._api_urls = get_list_config('KEYWORDS_API_URLS', [])
        self._health_check_interval = get_int_config('HEALTH_CHECK_INTERVAL', 60)
        self._last_health_check = datetime.min
        self._lock = threading.RLock()
    
    def get_healthy_apis(self) -> List[str]:
        """获取健康的API列表"""
        with self._lock:
            self._ensure_health_check()
            
            healthy_apis = []
            for api_url in self._api_urls:
                if self.health_checker.check_health(api_url):
                    healthy_apis.append(api_url)
            
            # 按健康分数排序
            healthy_apis.sort(
                key=lambda url: self.health_checker.get_health_score(url),
                reverse=True
            )
            
            return healthy_apis
    
    def call_api_with_retry(self, api_url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """带重试机制的API调用"""
        last_error = None
        
        for attempt in range(self.retry_strategy.max_retries + 1):
            try:
                with managed_session() as session:
                    timeout = get_int_config('REQUEST_TIMEOUT', 30)
                    
                    if 'keyword=' in api_url:
                        # GET请求
                        response = session.get(api_url, timeout=timeout)
                    else:
                        # POST请求
                        response = session.post(api_url, json=payload, timeout=timeout)
                    
                    response.raise_for_status()
                    return response.json()
            
            except Exception as e:
                last_error = e
                
                if not self.retry_strategy.should_retry(attempt, e):
                    break
                
                if attempt < self.retry_strategy.max_retries:
                    delay = self.retry_strategy.get_retry_delay(attempt)
                    logger.warning(f"API调用失败，{delay}秒后重试 (尝试 {attempt + 1}/{self.retry_strategy.max_retries + 1}): {e}")
                    time.sleep(delay)
        
        # 所有重试都失败了
        if last_error:
            error_manager = get_error_manager()
            error_manager.handle_error(last_error, {
                'api_url': api_url,
                'payload': payload,
                'attempts': attempt + 1
            })
        
        return None
    
    def batch_process_with_failover(self, items: List[str], item_processor: Callable) -> Dict[str, Any]:
        """带故障转移的批处理"""
        healthy_apis = self.get_healthy_apis()
        
        if not healthy_apis:
            logger.error("没有可用的健康API")
            return {'results': {}, 'success_count': 0, 'failure_count': len(items)}
        
        # 使用最健康的API
        primary_api = healthy_apis[0]
        from src.privacy_utils import PrivacyMasker
        masked_api = PrivacyMasker.mask_api_url(primary_api)
        logger.info(f"使用主API: {masked_api}")
        
        try:
            return self.batch_processor.process_batch(items, item_processor)
        except Exception as e:
            logger.error(f"主API批处理失败: {e}")
            
            # 故障转移到备用API
            if len(healthy_apis) > 1:
                backup_api = healthy_apis[1]
                from src.privacy_utils import PrivacyMasker
                masked_backup = PrivacyMasker.mask_api_url(backup_api)
                logger.info(f"故障转移到备用API: {masked_backup}")
                try:
                    return self.batch_processor.process_batch(items, item_processor)
                except Exception as backup_error:
                    logger.error(f"备用API也失败: {backup_error}")
            
            return {'results': {}, 'success_count': 0, 'failure_count': len(items)}
    
    def _ensure_health_check(self):
        """确保健康检查是最新的"""
        now = datetime.now()
        if (now - self._last_health_check).total_seconds() > self._health_check_interval:
            self._perform_health_check()
            self._last_health_check = now
    
    def _perform_health_check(self):
        """执行健康检查"""
        logger.debug("执行API健康检查...")
        
        # 并发检查所有API
        with ThreadPoolExecutor(max_workers=min(len(self._api_urls), 5)) as executor:
            futures = []
            for api_url in self._api_urls:
                future = executor.submit(self.health_checker.check_health, api_url)
                futures.append((api_url, future))
            
            # 收集结果
            for api_url, future in futures:
                try:
                    is_healthy = future.result(timeout=10)
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    logger.debug(f"API {masked_url} 健康状态: {'健康' if is_healthy else '不健康'}")
                except Exception as e:
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    logger.warning(f"健康检查失败 {masked_url}: {e}")
    
    def get_api_statistics(self) -> Dict[str, Any]:
        """获取API统计信息"""
        if hasattr(self.health_checker, 'get_all_health_status'):
            health_status = self.health_checker.get_all_health_status()
        else:
            health_status = {}
        
        return {
            'api_count': len(self._api_urls),
            'healthy_apis': len(self.get_healthy_apis()),
            'health_status': health_status,
            'current_batch_size': getattr(self.batch_processor, 'current_batch_size', 'N/A'),
            'last_health_check': self._last_health_check.isoformat()
        }

# 全局API管理器实例  
_api_manager: Optional[SmartAPIManager] = None

def get_api_manager() -> SmartAPIManager:
    """获取全局API管理器实例"""
    global _api_manager
    if _api_manager is None:
        _api_manager = SmartAPIManager()
    return _api_manager

# 便捷函数
@handle_errors(severity=ErrorSeverity.HIGH, re_raise=False)
def call_api_safely(api_url: str, payload: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """安全的API调用函数"""
    manager = get_api_manager()
    return manager.call_api_with_retry(api_url, payload or {})

@handle_errors(severity=ErrorSeverity.MEDIUM, re_raise=False, default_return={})
def batch_process_items(items: List[Any], processor: Callable) -> Dict[str, Any]:
    """批处理项目的便捷函数"""
    manager = get_api_manager()
    return manager.batch_process_with_failover(items, processor) 