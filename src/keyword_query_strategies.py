#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词查询策略模块
实现不同的关键词查询策略：直接并发、队列调度等
"""

import logging
import time
import queue
import threading
import concurrent.futures
from typing import Dict, List, Any
from abc import ABC, abstractmethod

from src.config import config
from src.keyword_api import KeywordAPI
from src.api_health_monitor import api_health_monitor
from src.keyword_extractor import keyword_extractor


class KeywordQueryStrategy(ABC):
    """关键词查询策略抽象基类"""
    
    def __init__(self, api_clients: dict, logger: logging.Logger):
        self.api_clients = api_clients
        self.logger = logger
    
    @abstractmethod
    def execute_query(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """执行关键词查询
        
        Args:
            keywords_list: 关键词列表
            max_retries: 最大重试次数
            
        Returns:
            关键词数据字典
        """
        pass


class DirectParallelStrategy(KeywordQueryStrategy):
    """直接并发查询策略 - 适用于小批量关键词"""
    
    def execute_query(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """执行直接并发查询"""
        self.logger.info(f"使用直接并发模式: {len(keywords_list)} 个关键词")
        
        # 关键词去重
        unique_keywords = {}
        for kw in keywords_list:
            unique_keywords[kw.lower()] = kw
        unique_kw_list = list(unique_keywords.values())
        
        # 根据API数量分片关键词
        num_apis = len(config.keywords_api_urls)
        keyword_shards = self._shard_keywords(unique_kw_list, num_apis)
        
        # 并发查询所有API
        return self._execute_parallel_queries(keyword_shards, max_retries)
    
    def _shard_keywords(self, keywords: List[str], num_apis: int) -> List[List[str]]:
        """将关键词分片到不同API - 基于健康状态优化分配"""
        keyword_shards = [[] for _ in range(num_apis)]

        # 获取API健康状态，优先分配给健康的API
        api_health_scores = []
        for i, api_url in enumerate(config.keywords_api_urls[:num_apis]):
            if api_health_monitor.is_api_available(api_url):
                # 健康的API获得更高权重
                health_summary = api_health_monitor.get_health_summary().get(api_url, {})
                success_rate = health_summary.get('success_rate', 1.0)
                api_health_scores.append((i, success_rate))
            else:
                api_health_scores.append((i, 0.0))  # 不健康的API权重为0

        # 按健康分数排序
        api_health_scores.sort(key=lambda x: x[1], reverse=True)

        # 智能分配：优先分配给健康的API
        for i, keyword in enumerate(keywords):
            if api_health_scores:
                # 选择最健康的可用API
                best_api_index = api_health_scores[i % len(api_health_scores)][0]
                keyword_shards[best_api_index].append(keyword)
            else:
                # 如果没有健康的API，使用轮询
                api_index = i % num_apis
                keyword_shards[api_index].append(keyword)

        return keyword_shards
    
    def _execute_parallel_queries(self, keyword_shards: List[List[str]], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """执行并发查询"""
        num_apis = len(config.keywords_api_urls)
        final_results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_apis) as executor:
            # 为每个API创建查询任务
            future_to_api = {}
            for api_index, shard in enumerate(keyword_shards):
                if shard:  # 只处理非空分片
                    # 防护检查：确保API索引有效
                    if api_index >= len(config.keywords_api_urls):
                        self.logger.error(f"API索引({api_index})超出范围，跳过此分片")
                        continue
                        
                    api_url = config.keywords_api_urls[api_index]
                    api_client = self._get_api_client(api_url)
                    future = executor.submit(api_client.batch_query_keywords, shard, max_retries)
                    future_to_api[future] = (api_index, shard)
            
            # 收集所有结果
            for future in concurrent.futures.as_completed(future_to_api):
                api_index, shard = future_to_api[future]
                try:
                    result = future.result(timeout=120)  # 总超时2分钟
                    final_results.update(result)
                    self.logger.debug(f"API {api_index} 查询完成，返回 {len(result)} 个关键词数据")
                except Exception as e:
                    self.logger.error(f"API {api_index} 查询失败: {e}")
                    # 不进行故障转移，让失败的关键词在下次运行时重新尝试
                    self.logger.info(f"API {api_index} 失败的 {len(shard)} 个关键词将在下次运行时重新尝试")
        
        return final_results
    
    def _get_api_client(self, api_url: str) -> KeywordAPI:
        """获取或创建API客户端实例"""
        if api_url not in self.api_clients:
            self.api_clients[api_url] = KeywordAPI(api_url)
            self.logger.debug(f"创建新的API客户端")
        return self.api_clients[api_url]


class QueueSchedulerStrategy(KeywordQueryStrategy):
    """队列调度查询策略 - 适用于大批量关键词"""
    
    def __init__(self, api_clients: dict, logger: logging.Logger, scheduler_config):
        super().__init__(api_clients, logger)
        self.config = scheduler_config
        self.max_queue_workers = max(1, min(self.config.max_workers, len(config.keywords_api_urls)))
    
    def execute_query(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """使用智能队列调度器处理大批量请求"""
        # 关键词去重 - 使用统一规范化函数
        unique_keywords = {}
        for kw in keywords_list:
            normalized_kw = keyword_extractor.normalize_keyword(kw)
            if normalized_kw:  # 只处理有效的关键词
                unique_keywords[normalized_kw] = kw
        unique_kw_list = list(unique_keywords.values())
        
        total_keywords = len(unique_kw_list)
        self.logger.info(f"启动智能队列调度器，处理 {total_keywords} 个关键词")
        
        # 创建结果收集器
        results = {}
        results_lock = threading.Lock()
        
        # 创建任务队列
        task_queue = queue.Queue()
        
        # 将关键词分批加入队列
        keyword_batches = self._create_keyword_batches(unique_kw_list)
        for batch in keyword_batches:
            task_queue.put(batch)
        
        # 创建队列处理工作线程
        from src.thread_resource_manager import ThreadResourceManager
        thread_manager = ThreadResourceManager(
            max_workers=self.max_queue_workers,
            timeout=self.config.queue_timeout
        )
        
        # 准备工作线程参数
        worker_args = []
        for i in range(self.max_queue_workers):
            args = (task_queue, results, results_lock, max_retries, i)
            worker_args.append(args)
        
        # 创建并启动工作线程
        thread_manager.create_workers(self._queue_worker, worker_args)
        
        # 使用智能等待机制
        self._wait_for_completion(task_queue, thread_manager)
        
        # 优雅关闭线程
        thread_manager.shutdown_gracefully()
        
        self.logger.info(f"队列调度完成，共处理 {len(results)} 个关键词")
        return results
    
    def _create_keyword_batches(self, keywords: List[str]) -> List[List[str]]:
        """将关键词列表分割成批次"""
        batches = []
        batch_size = self.config.batch_size
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            batches.append(batch)
        
        # 记录批次创建信息（仅调试级别）
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"创建 {len(batches)} 个批次，每批最多 {batch_size} 个关键词")
        
        return batches
    
    def _queue_worker(self, task_queue: queue.Queue, results: Dict, results_lock: threading.Lock, 
                      max_retries: int, worker_id: int):
        """队列工作线程"""
        # 防护检查：确保API地址列表不为空
        if not config.keywords_api_urls:
            self.logger.error(f"工作线程 {worker_id} 启动失败：没有可用的API地址")
            return
            
        api_index = worker_id % len(config.keywords_api_urls)
        api_url = config.keywords_api_urls[api_index]
        api_client = self._get_api_client(api_url)
        
        self.logger.debug(f"队列工作线程 {worker_id} 启动，使用API {api_index}")
        
        while True:
            try:
                # 获取任务，超时1秒
                batch = task_queue.get(timeout=1)
                if batch is None:  # 停止信号
                    break
                
                # 处理批次
                start_time = time.time()
                try:
                    batch_result = api_client.batch_query_keywords(batch, max_retries)
                    
                    # 更新结果
                    with results_lock:
                        results.update(batch_result)
                    
                    # 计算处理时间和需要的间隔
                    process_time = time.time() - start_time
                    base_interval = max(self.config.batch_interval, 2.0)
                    required_interval = max(base_interval, base_interval - process_time)

                    self.logger.debug(f"工作线程 {worker_id} 完成批次 {len(batch)} 个关键词，"
                                    f"耗时 {process_time:.2f}s，休息 {required_interval:.2f}s")

                    # 总是休眠以减少API压力
                    time.sleep(required_interval)
                        
                except Exception as e:
                    self.logger.error(f"工作线程 {worker_id} 处理批次失败: {e}")
                    # 记录失败的关键词，但不创建虚假数据
                    self.logger.warning(f"跳过 {len(batch)} 个查询失败的关键词")
                
                finally:
                    task_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"队列工作线程 {worker_id} 异常: {e}")
                break
        
        self.logger.debug(f"队列工作线程 {worker_id} 结束")
    
    def _wait_for_completion(self, task_queue: queue.Queue, thread_manager):
        """等待队列处理完成"""
        start_time = time.time()
        max_wait_time = min(self.config.queue_timeout, 120)  # 最大等待120秒
        check_interval = 0.5  # 检查间隔500ms

        while not task_queue.empty():
            elapsed_time = time.time() - start_time
            if elapsed_time > max_wait_time:
                remaining_tasks = task_queue.qsize()
                self.logger.warning(f"队列处理超时({max_wait_time}秒)，剩余任务: {remaining_tasks}，强制结束")
                break

            # 检查工作线程状态
            thread_status = thread_manager.get_thread_status()
            if thread_status['alive_threads'] == 0 and not task_queue.empty():
                self.logger.warning("所有工作线程已结束但队列仍有任务，强制结束")
                break

            time.sleep(check_interval)

        # 发送停止信号给所有工作线程
        self.logger.debug("发送停止信号给所有工作线程")
        for _ in range(self.max_queue_workers):
            try:
                task_queue.put(None, timeout=1)  # 1秒超时避免阻塞
            except queue.Full:
                self.logger.warning("队列已满，无法发送停止信号")
                break
    
    def _get_api_client(self, api_url: str) -> KeywordAPI:
        """获取或创建API客户端实例"""
        if api_url not in self.api_clients:
            self.api_clients[api_url] = KeywordAPI(api_url)
            self.logger.debug(f"创建新的API客户端")
        return self.api_clients[api_url]