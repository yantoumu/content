#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线程资源管理模块
处理工作线程的创建、监控和优雅关闭
"""

import logging
import threading
from typing import Callable, List, Any


class ThreadResourceManager:
    """线程资源管理器 - 单一职责：管理工作线程生命周期"""
    
    def __init__(self, max_workers: int, timeout: int):
        """初始化线程资源管理器
        
        Args:
            max_workers: 最大工作线程数
            timeout: 线程超时时间
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.threads = []
        self.shutdown_event = threading.Event()
        self.logger = logging.getLogger('content_watcher.thread_manager')
    
    def create_workers(self, target_func: Callable, args_list: List[Any]) -> None:
        """创建工作线程
        
        Args:
            target_func: 工作线程执行的函数
            args_list: 传递给每个线程的参数列表
        """
        self.threads.clear()
        actual_workers = min(self.max_workers, len(args_list))
        
        for i in range(actual_workers):
            args = args_list[i] if i < len(args_list) else args_list[0]
            thread = threading.Thread(
                target=self._worker_wrapper,
                args=(target_func, args, i),
                daemon=True,  # 设置为守护线程
                name=f"KeywordWorker-{i}"
            )
            thread.start()
            self.threads.append(thread)
        
        self.logger.debug(f"创建了 {len(self.threads)} 个工作线程")
    
    def _worker_wrapper(self, target_func: Callable, args: Any, worker_id: int) -> None:
        """工作线程包装器，添加异常处理和资源清理
        
        Args:
            target_func: 目标函数
            args: 函数参数
            worker_id: 工作线程ID
        """
        try:
            self.logger.debug(f"工作线程 {worker_id} 开始执行")
            target_func(*args)
        except Exception as e:
            self.logger.error(f"工作线程 {worker_id} 异常退出: {e}")
            # 可以在这里添加异常回调处理
        finally:
            self.logger.debug(f"工作线程 {worker_id} 正常结束")
    
    def shutdown_gracefully(self) -> None:
        """优雅关闭所有工作线程"""
        if not self.threads:
            self.logger.debug("没有工作线程需要关闭")
            return
        
        # 发送关闭信号
        self.shutdown_event.set()
        self.logger.debug(f"发送关闭信号给 {len(self.threads)} 个工作线程")
        
        # 等待线程结束
        alive_threads = []
        for i, thread in enumerate(self.threads):
            thread.join(timeout=10)  # 最多等待10秒
            if thread.is_alive():
                alive_threads.append(i)
        
        if alive_threads:
            self.logger.warning(f"有 {len(alive_threads)} 个线程未能正常结束: {alive_threads}")
        else:
            self.logger.debug("所有工作线程已正常关闭")
        
        self.threads.clear()
        self.shutdown_event.clear()
    
    def get_thread_status(self) -> dict:
        """获取线程状态信息
        
        Returns:
            dict: 线程状态统计
        """
        alive_count = sum(1 for thread in self.threads if thread.is_alive())
        return {
            'total_threads': len(self.threads),
            'alive_threads': alive_count,
            'dead_threads': len(self.threads) - alive_count,
            'shutdown_requested': self.shutdown_event.is_set()
        }
    
    def is_shutdown_requested(self) -> bool:
        """检查是否已请求关闭
        
        Returns:
            bool: 是否已请求关闭
        """
        return self.shutdown_event.is_set()