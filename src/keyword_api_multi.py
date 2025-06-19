#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多API关键词查询管理器
处理多个关键词API的并发查询和负载均衡
支持智能队列调度和渐进式批次处理
"""

import logging
import time
from typing import Dict, List, Any
import concurrent.futures
from collections import deque
import queue
import threading

from src.config import config
from src.keyword_api import KeywordAPI

# 配置日志
logger = logging.getLogger('content_watcher.keyword_api_multi')

class APISchedulerConfig:
    """API调度器配置类 - 符合单一职责原则"""
    
    def __init__(self, batch_size: int = None, batch_interval: float = 0.5, 
                 api_safe_rate: int = 2, max_workers: int = 3):
        # 使用配置中的批处理大小，如果没有指定则使用配置默认值
        self.batch_size = batch_size if batch_size is not None else config.keywords_batch_size
        self.batch_interval = batch_interval  # 批次间间隔（秒）
        self.api_safe_rate = api_safe_rate  # 每个API安全频率（请求/秒）
        self.max_workers = max_workers  # 最大工作线程数
        
        # 验证配置合理性
        if self.batch_size < 1:
            logger.warning(f"批处理大小不合理({self.batch_size})，已重置为1")
            self.batch_size = 1
        elif self.batch_size > 10:
            logger.warning(f"批处理大小过大({self.batch_size})，已重置为10")
            self.batch_size = 10


class MultiAPIKeywordManager:
    """多API关键词查询管理器，支持智能队列调度"""

    def __init__(self, scheduler_config: APISchedulerConfig = None):
        """初始化多API管理器"""
        self.logger = logging.getLogger('content_watcher.keyword_api_multi')
        self._api_clients = {}  # 缓存API客户端实例
        self._api_clients_lock = threading.RLock()  # 线程安全锁
        
        # 使用配置对象而非硬编码
        self.config = scheduler_config or APISchedulerConfig()
        self._workers_initialized = False
        
        # 记录实际使用的批处理大小
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"多API管理器初始化，批处理大小: {self.config.batch_size}")

    def _ensure_workers_initialized(self):
        """确保工作线程数已正确初始化"""
        if not self._workers_initialized:
            api_count = len(config.keywords_api_urls) if config.keywords_api_urls else 1
            self.max_queue_workers = max(1, min(self.config.max_workers, api_count))
            self._workers_initialized = True
            self.logger.debug(f"初始化队列工作线程数: {self.max_queue_workers}")

    def batch_query_keywords_parallel(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """并发查询关键词信息，使用多个API地址
        
        Args:
            keywords_list: 关键词列表
            max_retries: 最大重试次数
            
        Returns:
            关键词数据字典，键为关键词，值为API返回的数据
        """
        if not keywords_list:
            return {}
        
        try:
            # 防护检查：确保有可用的API地址
            if not config.keywords_api_urls:
                self.logger.error("没有配置可用的关键词API地址")
                return self._create_default_keyword_data(keywords_list)
            
            # 根据API数量决定使用单API还是多API模式
            if len(config.keywords_api_urls) <= 1:
                if len(config.keywords_api_urls) == 1:
                    api_url = config.keywords_api_urls[0]
                    self.logger.info(f"使用单API模式: {api_url}")
                    api = KeywordAPI(api_url)
                    return api.batch_query_keywords(keywords_list, max_retries)
                else:
                    self.logger.error("没有配置任何关键词API地址")
                    return self._create_default_keyword_data(keywords_list)
            
            # 多API模式：根据关键词数量选择处理策略
            self.logger.info(f"使用多API并发模式: {len(config.keywords_api_urls)} 个API地址")
            
            # 大批量处理使用智能队列调度
            if len(keywords_list) > 100:
                self.logger.info(f"大批量处理模式: {len(keywords_list)} 个关键词，使用队列调度")
                return self._batch_query_with_queue_scheduler(keywords_list, max_retries)
            
            # 小批量处理使用直接并发方法
            self.logger.info(f"小批量处理模式: {len(keywords_list)} 个关键词，使用直接并发")
            return self._batch_query_direct_parallel(keywords_list, max_retries)
            
        except Exception as e:
            self.logger.error(f"并发关键词查询失败: {e}")
            return self._create_default_keyword_data(keywords_list)

    def _batch_query_direct_parallel(self, keywords_list: List[str], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """直接并发查询（原有方法，适用于小批量）"""
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

    def _batch_query_with_queue_scheduler(self, keywords_list: List[str], max_retries: int) -> Dict[str, Dict[str, Any]]:
        """使用智能队列调度器处理大批量请求"""
        # 关键词去重
        unique_keywords = {}
        for kw in keywords_list:
            unique_keywords[kw.lower()] = kw
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
        self._ensure_workers_initialized()
        threads = []
        for i in range(self.max_queue_workers):
            thread = threading.Thread(
                target=self._queue_worker,
                args=(task_queue, results, results_lock, max_retries, i)
            )
            thread.start()
            threads.append(thread)
        
        # 等待所有任务完成
        task_queue.join()
        
        # 停止工作线程
        for _ in threads:
            task_queue.put(None)  # 发送停止信号
        
        for thread in threads:
            thread.join()
        
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
        
        # 防护检查：确保除数不为零
        if len(config.keywords_api_urls) == 0:
            self.logger.error(f"工作线程 {worker_id} 启动失败：API地址列表为空")
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
                
                # 验证批次大小
                if len(batch) > config.keywords_batch_size:
                    self.logger.warning(f"工作线程 {worker_id} 收到超大批次({len(batch)})，可能导致API错误")
                
                # 处理批次
                start_time = time.time()
                try:
                    batch_result = api_client.batch_query_keywords(batch, max_retries)
                    
                    # 更新结果
                    with results_lock:
                        results.update(batch_result)
                    
                    # 计算处理时间和需要的间隔
                    process_time = time.time() - start_time
                    required_interval = max(0, self.config.batch_interval - process_time)
                    
                    self.logger.debug(f"工作线程 {worker_id} 完成批次 {len(batch)} 个关键词，"
                                    f"耗时 {process_time:.2f}s，休息 {required_interval:.2f}s")
                    
                    if required_interval > 0:
                        time.sleep(required_interval)
                        
                except Exception as e:
                    self.logger.error(f"工作线程 {worker_id} 处理批次失败: {e}")
                    # 创建默认数据
                    default_data = self._create_default_keyword_data(batch)
                    with results_lock:
                        results.update(default_data)
                
                finally:
                    task_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"队列工作线程 {worker_id} 异常: {e}")
                break
        
        self.logger.debug(f"队列工作线程 {worker_id} 结束")

    def _shard_keywords(self, keywords: List[str], num_apis: int) -> List[List[str]]:
        """将关键词分片到不同API"""
        keyword_shards = [[] for _ in range(num_apis)]
        
        # 轮询分配关键词到不同API
        for i, keyword in enumerate(keywords):
            api_index = i % num_apis
            keyword_shards[api_index].append(keyword)
        
        return keyword_shards

    def _get_api_client(self, api_url: str) -> KeywordAPI:
        """获取或创建API客户端实例（线程安全）"""
        with self._api_clients_lock:
            if api_url not in self._api_clients:
                self._api_clients[api_url] = KeywordAPI(api_url)
                self.logger.debug(f"创建新的API客户端: {api_url}")
            return self._api_clients[api_url]

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
                    # 故障转移：将失败的关键词分配给其他API
                    fallback_result = self._handle_api_failure(shard, api_index, max_retries)
                    final_results.update(fallback_result)
        
        return final_results

    def _handle_api_failure(self, failed_keywords: List[str], failed_api_index: int, max_retries: int) -> Dict[str, Dict[str, Any]]:
        """处理API失败，尝试用其他API重新查询"""
        if len(config.keywords_api_urls) == 1:
            # 只有一个API，创建默认数据
            return self._create_default_keyword_data(failed_keywords)
        
        # 尝试用其他API查询
        for api_index, api_url in enumerate(config.keywords_api_urls):
            if api_index != failed_api_index:
                try:
                    api_client = self._get_api_client(api_url)
                    result = api_client.batch_query_keywords(failed_keywords, max_retries)
                    self.logger.info(f"故障转移成功，API {api_index} 处理了 {len(result)} 个关键词")
                    return result
                except Exception as e:
                    self.logger.warning(f"故障转移到API {api_index} 失败: {e}")
                    continue
        
        # 所有API都失败，创建默认数据
        return self._create_default_keyword_data(failed_keywords)

    def close(self):
        """关闭所有API客户端连接"""
        with self._api_clients_lock:
            for api_url, client in self._api_clients.items():
                try:
                    if hasattr(client, 'close'):
                        client.close()
                        self.logger.debug(f"关闭API客户端连接: {api_url}")
                except Exception as e:
                    self.logger.warning(f"关闭API客户端连接时出错 {api_url}: {e}")
            self._api_clients.clear()

    def __del__(self):
        """析构函数，确保资源清理"""
        self.close()

    def _create_default_keyword_data(self, keywords: List[str]) -> Dict[str, Dict[str, Any]]:
        """为失败的关键词创建默认数据"""
        default_data = {}
        for kw in keywords:
            default_data[kw] = {
                'keyword': kw,
                'metrics': {
                    'avg_monthly_searches': 0,
                    'competition': 'LOW',
                    'competition_index': '0',
                    'monthly_searches': []
                }
            }
        return default_data

# 创建全局多API管理器实例
multi_api_manager = MultiAPIKeywordManager() 