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
from src.api_health_monitor import api_health_monitor

# 配置日志
logger = logging.getLogger('content_watcher.keyword_api_multi')

class APISchedulerConfig:
    """API调度器配置类 - 性能优化版本"""

    def __init__(self, batch_size: int = None, batch_interval: float = None,
                 api_safe_rate: int = 1, max_workers: int = 2):  # 根据seokey API限制调整为2
        # 使用配置中的批处理大小，如果没有指定则使用配置默认值
        self.batch_size = batch_size if batch_size is not None else config.keywords_batch_size
        self.batch_interval = batch_interval if batch_interval is not None else config.api_request_interval
        self.api_safe_rate = api_safe_rate  # 每个API安全频率（请求/秒）
        self.max_workers = max_workers  # 最大工作线程数
        # 动态计算队列超时时间
        base_timeout = getattr(config, 'queue_timeout', 300)
        self.queue_timeout = self._calculate_dynamic_timeout(base_timeout)

        # 根据seokey API特性优化配置
        if hasattr(config, 'enable_performance_mode') and config.enable_performance_mode:
            logger.info("启用seokey API优化模式")
            self.batch_size = 5  # seokey API支持最多5个关键词/请求
            self.batch_interval = max(self.batch_interval, 2.0)  # 确保至少2秒间隔
            self.max_workers = min(max_workers, 2)  # seokey API限制最多2个并发线程
            # 为seokey API计算更合理的超时时间
            self.queue_timeout = self._calculate_seokey_timeout()
            logger.info(f"seokey优化配置: batch_size={self.batch_size}, interval={self.batch_interval}, workers={self.max_workers}, timeout={self.queue_timeout}s")

        # 验证配置合理性 - 根据seokey API限制
        if self.batch_size < 1:
            logger.warning(f"批处理大小不合理({self.batch_size})，已重置为1")
            self.batch_size = 1
        elif self.batch_size > 5:  # seokey API最大支持5个关键词/请求
            logger.warning(f"批处理大小过大({self.batch_size})，已重置为5")
            self.batch_size = 5

    def _calculate_dynamic_timeout(self, base_timeout: int) -> int:
        """动态计算队列超时时间
        
        Args:
            base_timeout: 基础超时时间
            
        Returns:
            int: 调整后的超时时间
        """
        # 根据批次大小和间隔计算预期处理时间
        estimated_batch_time = self.batch_interval + 30  # 30秒缓冲时间
        
        # 考虑重试次数（最多2次重试）
        max_retry_time = estimated_batch_time * 3
        
        # 动态超时 = 基础超时 + 预估处理时间
        dynamic_timeout = max(base_timeout, max_retry_time)
        
        # 设置合理的上限（最多30分钟）
        return min(dynamic_timeout, 1800)

    def _calculate_seokey_timeout(self) -> int:
        """为seokey API计算专用超时时间
        
        Returns:
            int: seokey API专用超时时间
        """
        # seokey API响应时间约70秒
        single_request_time = 70
        
        # 考虑批次间隔和重试
        batch_processing_time = single_request_time + self.batch_interval
        
        # 为每个批次预留充足时间（包括3次重试）
        max_batch_time = batch_processing_time * 4  # 4倍缓冲
        
        # 最少5分钟，最多20分钟
        return max(300, min(max_batch_time, 1200))


class ThreadResourceManager:
    """线程资源管理器 - 单一职责：管理工作线程生命周期"""
    
    def __init__(self, max_workers: int, timeout: int):
        self.max_workers = max_workers
        self.timeout = timeout
        self.threads = []
        self.shutdown_event = threading.Event()
        self.logger = logging.getLogger('content_watcher.thread_manager')
    
    def create_workers(self, target_func, args_list):
        """创建工作线程
        
        Args:
            target_func: 工作线程执行的函数
            args_list: 传递给每个线程的参数列表
        """
        self.threads.clear()
        for i in range(min(self.max_workers, len(args_list))):
            args = args_list[i] if i < len(args_list) else args_list[0]
            thread = threading.Thread(
                target=self._worker_wrapper,
                args=(target_func, args, i),
                daemon=True  # 设置为守护线程
            )
            thread.start()
            self.threads.append(thread)
        
        self.logger.debug(f"创建了 {len(self.threads)} 个工作线程")
    
    def _worker_wrapper(self, target_func, args, worker_id):
        """工作线程包装器，添加异常处理和资源清理"""
        try:
            target_func(*args)
        except Exception as e:
            self.logger.error(f"工作线程 {worker_id} 异常退出: {e}")
        finally:
            self.logger.debug(f"工作线程 {worker_id} 正常结束")
    
    def shutdown_gracefully(self):
        """优雅关闭所有工作线程"""
        if not self.threads:
            return
        
        # 发送关闭信号
        self.shutdown_event.set()
        
        # 等待线程结束
        alive_threads = []
        for i, thread in enumerate(self.threads):
            thread.join(timeout=10)  # 最多等待10秒
            if thread.is_alive():
                alive_threads.append(i)
        
        if alive_threads:
            self.logger.warning(f"有 {len(alive_threads)} 个线程未能正常结束: {alive_threads}")
        
        self.threads.clear()
        self.shutdown_event.clear()


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
        
        # 初始化线程资源管理器
        self.thread_manager = ThreadResourceManager(
            max_workers=self.config.max_workers,
            timeout=self.config.queue_timeout
        )
        
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
                self.logger.error("没有配置可用的关键词API地址，跳过关键词查询")
                return {}

            # 根据API数量决定使用单API还是多API模式
            if len(config.keywords_api_urls) <= 1:
                if len(config.keywords_api_urls) == 1:
                    api_url = config.keywords_api_urls[0]
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.info(f"使用单API模式: {masked_url}")
                    api = KeywordAPI(api_url)
                    return api.batch_query_keywords(keywords_list, max_retries)
                else:
                    self.logger.error("没有配置任何关键词API地址，跳过关键词查询")
                    return {}

            # 基于性能测试结果，优先使用串行处理模式
            self.logger.info(f"使用优化串行处理模式: {len(keywords_list)} 个关键词")

            # 尝试使用优化的串行处理器
            try:
                from src.optimized_serial_processor import get_optimized_processor
                processor = get_optimized_processor()

                result = processor.process_keywords_optimized(keywords_list)
                return result.get('results', {})

            except ImportError:
                self.logger.warning("优化串行处理器不可用，降级到原有模式")

                # 降级策略：大批量使用队列，小批量使用并发
                if len(keywords_list) > 100:
                    self.logger.info(f"降级到队列调度模式: {len(keywords_list)} 个关键词")
                    return self._batch_query_with_queue_scheduler(keywords_list, max_retries)
                else:
                    self.logger.info(f"降级到直接并发模式: {len(keywords_list)} 个关键词")
                    return self._batch_query_direct_parallel(keywords_list, max_retries)

        except Exception as e:
            self.logger.error(f"并发关键词查询失败: {e}")
            return {}

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
        # 关键词去重 - 使用统一规范化函数
        from src.keyword_extractor import keyword_extractor
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
        self._ensure_workers_initialized()
        threads = []
        for i in range(self.max_queue_workers):
            thread = threading.Thread(
                target=self._queue_worker,
                args=(task_queue, results, results_lock, max_retries, i)
            )
            thread.start()
            threads.append(thread)
        
        # 使用智能等待机制替代task_queue.join() - 解决队列阻塞问题
        start_time = time.time()
        max_wait_time = min(self.config.queue_timeout, 120)  # 最大等待120秒
        check_interval = 0.5  # 检查间隔500ms，减少CPU占用

        while not task_queue.empty():
            elapsed_time = time.time() - start_time
            if elapsed_time > max_wait_time:
                remaining_tasks = task_queue.qsize()
                self.logger.warning(f"队列处理超时({max_wait_time}秒)，剩余任务: {remaining_tasks}，强制结束")
                break

            # 检查工作线程状态
            alive_threads = sum(1 for t in threads if t.is_alive())
            if alive_threads == 0 and not task_queue.empty():
                self.logger.warning("所有工作线程已结束但队列仍有任务，强制结束")
                break

            time.sleep(check_interval)

        # 优雅停止工作线程
        self.logger.debug("发送停止信号给所有工作线程")
        for _ in threads:
            try:
                task_queue.put(None, timeout=1)  # 1秒超时避免阻塞
            except queue.Full:
                self.logger.warning("队列已满，无法发送停止信号")
                break

        # 等待线程结束，设置合理超时
        thread_timeout = 15  # 减少到15秒
        for i, thread in enumerate(threads):
            thread.join(timeout=thread_timeout)
            if thread.is_alive():
                self.logger.warning(f"工作线程 {i} 未能在{thread_timeout}秒内正常结束，可能存在阻塞")

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
                
                # 智能批次大小验证和调整
                max_batch_size = self._get_adaptive_batch_size(api_url)
                if len(batch) > max_batch_size:
                    self.logger.warning(f"工作线程 {worker_id} 收到超大批次({len(batch)})，"
                                      f"最大允许: {max_batch_size}，可能导致API错误")
                
                # 处理批次
                start_time = time.time()
                try:
                    batch_result = api_client.batch_query_keywords(batch, max_retries)
                    
                    # 更新结果
                    with results_lock:
                        results.update(batch_result)
                    
                    # 计算处理时间和需要的间隔 - 根据seokey API特性优化
                    process_time = time.time() - start_time
                    # 确保至少2秒间隔，考虑seokey API的限制
                    base_interval = max(self.config.batch_interval, 2.0)
                    required_interval = max(base_interval, base_interval - process_time)

                    self.logger.debug(f"工作线程 {worker_id} 完成批次 {len(batch)} 个关键词，"
                                    f"耗时 {process_time:.2f}s，休息 {required_interval:.2f}s")

                    # 总是休眠以减少API压力，确保符合seokey API限制
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

    def _get_api_client(self, api_url: str) -> KeywordAPI:
        """获取或创建API客户端实例（线程安全）"""
        with self._api_clients_lock:
            if api_url not in self._api_clients:
                self._api_clients[api_url] = KeywordAPI(api_url)
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(api_url)
                self.logger.debug(f"创建新的API客户端: {masked_url}")
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
                    # 不进行故障转移，让失败的关键词在下次运行时重新尝试
                    self.logger.info(f"API {api_index} 失败的 {len(shard)} 个关键词将在下次运行时重新尝试")
        
        return final_results

    def _get_adaptive_batch_size(self, api_url: str) -> int:
        """根据API健康状态获取自适应批次大小 - 根据seokey API限制

        Args:
            api_url: API地址

        Returns:
            推荐的批次大小（最大为5）
        """
        # 根据seokey API限制，最大支持5个关键词/请求
        # 可以根据API健康状态动态调整
        if api_health_monitor.is_api_available(api_url):
            health_summary = api_health_monitor.get_health_summary().get(api_url, {})
            success_rate = health_summary.get('success_rate', 1.0)

            if success_rate > 0.9:
                return 5  # 健康状态良好，使用最大批次
            elif success_rate > 0.7:
                return 4  # 健康状态一般，减少批次
            else:
                return 3  # 健康状态较差，进一步减少批次
        else:
            return 3  # API不可用时使用较小批次

    def _handle_api_failure(self, failed_keywords: List[str], failed_api_index: int, max_retries: int) -> Dict[str, Dict[str, Any]]:
        """处理API失败，尝试用其他API重新查询"""
        if len(config.keywords_api_urls) == 1:
            # 只有一个API，记录失败但不创建虚假数据
            self.logger.warning(f"单API模式下查询失败，跳过 {len(failed_keywords)} 个关键词")
            return {}

        # 尝试用其他API查询
        for api_index, api_url in enumerate(config.keywords_api_urls):
            if api_index != failed_api_index:
                try:
                    api_client = self._get_api_client(api_url)
                    result = api_client.batch_query_keywords(failed_keywords, max_retries)
                    if result:  # 确保有有效结果
                        self.logger.info(f"故障转移成功，API {api_index} 处理了 {len(result)} 个关键词")
                        return result
                except (requests.exceptions.RequestException, ValueError, TypeError) as e:
                    self.logger.warning(f"故障转移到API {api_index} 失败: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"故障转移到API {api_index} 时发生未预期错误: {e}")
                    continue

        # 所有API都失败，记录失败但不创建虚假数据
        self.logger.warning(f"所有API都失败，跳过 {len(failed_keywords)} 个关键词")
        return {}

    def close(self):
        """关闭所有API客户端连接和线程资源"""
        # 优雅关闭线程资源
        try:
            self.thread_manager.shutdown_gracefully()
        except Exception as e:
            self.logger.warning(f"关闭线程资源时出错: {e}")
        
        # 关闭API客户端连接
        with self._api_clients_lock:
            for api_url, client in self._api_clients.items():
                try:
                    if hasattr(client, 'close'):
                        client.close()
                        from src.privacy_utils import PrivacyMasker
                        masked_url = PrivacyMasker.mask_api_url(api_url)
                        self.logger.debug(f"关闭API客户端连接: {masked_url}")
                except Exception as e:
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(api_url)
                    self.logger.warning(f"关闭API客户端连接时出错 {masked_url}: {e}")
            self._api_clients.clear()

    def __del__(self):
        """析构函数，确保资源清理"""
        try:
            self.close()
        except Exception:
            # 析构函数中不应抛出异常
            pass



# 创建全局多API管理器实例
multi_api_manager = MultiAPIKeywordManager() 