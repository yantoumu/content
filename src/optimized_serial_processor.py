#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化的串行批次处理器
基于测试结果实现的高性能串行处理方案
"""

import time
import logging
import requests
import queue
import threading
from typing import Dict, List, Any, Optional
from src.config import config
from src.keyword_api import KeywordAPI
from src.api_health_monitor import api_health_monitor

logger = logging.getLogger(__name__)

class OptimizedSerialProcessor:
    """优化的串行批次处理器
    
    基于性能测试结果，实现最佳的串行处理策略：
    - 连接池复用
    - 智能间隔控制
    - 动态批次大小调整
    - 异步队列缓冲
    """
    
    def __init__(self, api_urls: List[str], batch_size: int = 5, batch_interval: float = 2.0):
        self.api_urls = api_urls
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.logger = logger
        
        # 创建优化的API客户端
        self.api_client = None
        self._init_api_client()

        # 异步队列缓冲
        self.request_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.processing_thread = None
        self.is_running = False

    def _init_api_client(self):
        """初始化优化的API客户端"""
        if self.api_urls:
            self.api_client = KeywordAPI(
                api_urls=self.api_urls,
                timeout=getattr(config, 'keyword_query_timeout', 80),
                max_retries=getattr(config, 'api_retry_max', 2)
            )
            
            # 启用连接池优化
            if hasattr(self.api_client, 'session'):
                self.api_client.session.headers.update({
                    'Connection': 'keep-alive',
                    'Keep-Alive': 'timeout=30, max=100'
                })
                
                # 配置连接池
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=1,
                    pool_maxsize=10,
                    max_retries=0  # 我们自己处理重试
                )
                self.api_client.session.mount('http://', adapter)
                self.api_client.session.mount('https://', adapter)
    
    def process_keywords_optimized(self, keywords: List[str]) -> Dict[str, Any]:
        """优化的串行关键词处理"""
        self.logger.info(f"🚀 开始优化串行处理 {len(keywords)} 个关键词")
        
        if not keywords:
            return {}
        
        # 创建批次
        batches = self._create_adaptive_batches(keywords)
        results = {}
        
        start_time = time.time()
        
        # 串行处理每个批次
        for i, batch in enumerate(batches, 1):
            self.logger.info(f"📦 处理批次 {i}/{len(batches)} ({len(batch)} 个关键词)")
            
            batch_start = time.time()
            
            # 处理单个批次
            batch_result = self._process_single_batch_optimized(batch)
            if batch_result:
                results.update(batch_result)
            
            batch_time = time.time() - batch_start
            success_count = len(batch_result) if batch_result else 0
            
            self.logger.info(f"  ✅ 批次 {i} 完成，耗时 {batch_time:.2f}s，成功 {success_count}/{len(batch)} 个")
            
            # 智能间隔控制（除了最后一个批次）
            if i < len(batches):
                wait_time = self._calculate_optimal_wait_time(batch_time)
                if wait_time > 0:
                    self.logger.debug(f"  ⏱️  智能等待 {wait_time:.2f}s")
                    time.sleep(wait_time)
        
        total_time = time.time() - start_time
        success_rate = (len(results) / len(keywords)) * 100
        
        self.logger.info(f"🎯 优化串行处理完成:")
        self.logger.info(f"  - 总耗时: {total_time:.2f}s")
        self.logger.info(f"  - 成功率: {success_rate:.1f}% ({len(results)}/{len(keywords)})")
        self.logger.info(f"  - 平均每个关键词: {total_time/len(keywords):.2f}s")
        self.logger.info(f"  - 处理速度: {len(keywords)/total_time:.2f} 关键词/秒")
        
        return {
            'results': results,
            'total_time': total_time,
            'success_rate': success_rate,
            'avg_time_per_keyword': total_time / len(keywords),
            'throughput': len(keywords) / total_time
        }
    
    def _create_adaptive_batches(self, keywords: List[str]) -> List[List[str]]:
        """创建自适应批次"""
        batches = []
        
        # 根据API健康状态动态调整批次大小
        if self.api_urls:
            api_url = self.api_urls[0]
            if api_health_monitor.is_api_available(api_url):
                health_summary = api_health_monitor.get_health_summary().get(api_url, {})
                success_rate = health_summary.get('success_rate', 1.0)
                
                # 根据成功率调整批次大小
                if success_rate > 0.95:
                    adaptive_batch_size = self.batch_size  # 使用最大批次
                elif success_rate > 0.8:
                    adaptive_batch_size = max(3, self.batch_size - 1)  # 稍微减少
                else:
                    adaptive_batch_size = max(2, self.batch_size - 2)  # 显著减少
            else:
                adaptive_batch_size = 2  # API不健康时使用最小批次
        else:
            adaptive_batch_size = self.batch_size
        
        self.logger.debug(f"自适应批次大小: {adaptive_batch_size}")
        
        # 创建批次
        for i in range(0, len(keywords), adaptive_batch_size):
            batch = keywords[i:i + adaptive_batch_size]
            batches.append(batch)
        
        return batches
    
    def _process_single_batch_optimized(self, batch: List[str]) -> Dict[str, Any]:
        """优化的单批次处理"""
        if not batch or not self.api_client:
            return {}
        
        try:
            # 使用优化的API客户端处理批次
            batch_result = self.api_client.batch_query_keywords(batch, max_retries=2)
            
            # 更新API健康状态
            if self.api_urls:
                api_url = self.api_urls[0]
                if batch_result:
                    api_health_monitor.record_success(api_url)
                else:
                    api_health_monitor.record_failure(api_url, "batch_processing_failed")
            
            return batch_result if batch_result else {}
            
        except Exception as e:
            self.logger.error(f"批次处理异常: {e}")
            
            # 记录API失败
            if self.api_urls:
                api_health_monitor.record_failure(self.api_urls[0], str(e))
            
            return {}
    
    def _calculate_optimal_wait_time(self, batch_time: float) -> float:
        """计算最优等待时间"""
        base_interval = max(self.batch_interval, 2.0)
        
        # 如果批次处理时间已经很长，减少等待时间
        if batch_time >= base_interval:
            return 0.5  # 最小间隔，避免API压力
        elif batch_time >= base_interval * 0.8:
            return base_interval - batch_time  # 补足到基础间隔
        else:
            return base_interval - batch_time  # 正常间隔控制
    
    def start_async_processing(self):
        """启动异步处理模式"""
        if self.is_running:
            return
        
        self.is_running = True
        self.processing_thread = threading.Thread(target=self._async_processing_worker)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        self.logger.info("🔄 异步处理模式已启动")
    
    def stop_async_processing(self):
        """停止异步处理模式"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 发送停止信号
        self.request_queue.put(None)
        
        # 等待处理线程结束
        if self.processing_thread:
            self.processing_thread.join(timeout=10)
        
        self.logger.info("🛑 异步处理模式已停止")
    
    def _async_processing_worker(self):
        """异步处理工作线程"""
        self.logger.info("🔧 异步处理工作线程启动")
        
        try:
            while self.is_running:
                try:
                    # 获取请求
                    request = self.request_queue.get(timeout=1)
                    if request is None:  # 停止信号
                        break
                    
                    keywords, callback = request
                    
                    # 处理关键词
                    result = self.process_keywords_optimized(keywords)
                    
                    # 回调结果
                    if callback:
                        callback(result)
                    else:
                        self.result_queue.put(result)
                    
                    self.request_queue.task_done()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"异步处理工作线程异常: {e}")
                    
        finally:
            self.logger.info("🔧 异步处理工作线程结束")
    
    def submit_async_request(self, keywords: List[str], callback: Optional[callable] = None):
        """提交异步请求"""
        if not self.is_running:
            self.start_async_processing()
        
        self.request_queue.put((keywords, callback))
    
    def get_async_result(self, timeout: float = None) -> Optional[Dict[str, Any]]:
        """获取异步处理结果"""
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_queue_status(self) -> Dict[str, int]:
        """获取队列状态"""
        return {
            'pending_requests': self.request_queue.qsize(),
            'pending_results': self.result_queue.qsize(),
            'is_running': self.is_running
        }
    
    def close(self):
        """关闭处理器"""
        self.stop_async_processing()
        
        if self.api_client:
            self.api_client.close()
        
        self.logger.info("🔒 优化串行处理器已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# 全局实例
_optimized_processor = None

def get_optimized_processor() -> OptimizedSerialProcessor:
    """获取全局优化处理器实例"""
    global _optimized_processor
    
    if _optimized_processor is None:
        _optimized_processor = OptimizedSerialProcessor(
            api_urls=config.keywords_api_urls,
            batch_size=config.keywords_batch_size,
            batch_interval=config.api_request_interval
        )
    
    return _optimized_processor
