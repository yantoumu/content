#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线程安全资源管理器
遵循SOLID原则的并发安全设计
"""

import threading
import queue
import time
import logging
from typing import Dict, Any, Optional, Protocol, TypeVar, Generic
from contextlib import contextmanager
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Interface Segregation Principle - 分离不同的接口职责
class IThreadSafeResource(Protocol[T]):
    """线程安全资源接口"""
    def acquire(self) -> T:
        """获取资源"""
        ...
    
    def release(self, resource: T) -> None:
        """释放资源"""
        ...

class IResourceFactory(Protocol[T]):
    """资源工厂接口"""
    def create_resource(self, key: str) -> T:
        """创建资源"""
        ...
    
    def destroy_resource(self, resource: T) -> None:
        """销毁资源"""
        ...

# Single Responsibility Principle - 每个类只负责一个职责
class ThreadSafeLock:
    """线程安全锁管理器 - 单一职责：管理锁"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._lock_count = 0
    
    @contextmanager
    def acquire_lock(self, timeout: Optional[float] = None):
        """安全获取锁的上下文管理器"""
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"无法在{timeout}秒内获取锁")
        
        try:
            self._lock_count += 1
            yield
        finally:
            self._lock_count -= 1
            self._lock.release()
    
    def get_lock_count(self) -> int:
        """获取当前锁计数"""
        return self._lock_count

class ThreadSafeResourcePool(Generic[T]):
    """线程安全资源池 - 单一职责：管理资源池"""
    
    def __init__(self, factory: IResourceFactory[T], max_size: int = 10):
        self._factory = factory
        self._max_size = max_size
        self._pool: queue.Queue[T] = queue.Queue(maxsize=max_size)
        self._created_resources: Dict[str, T] = {}
        self._lock = ThreadSafeLock()
        self._creation_count = 0
    
    @contextmanager
    def get_resource(self, key: str):
        """获取资源的上下文管理器"""
        resource = None
        try:
            resource = self._acquire_resource(key)
            yield resource
        finally:
            if resource:
                self._release_resource(resource)
    
    def _acquire_resource(self, key: str) -> T:
        """获取资源"""
        # 尝试从池中获取
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            # 池中没有资源，创建新的
            with self._lock.acquire_lock(timeout=5.0):
                if key not in self._created_resources:
                    if self._creation_count >= self._max_size:
                        # 等待资源释放
                        logger.warning("资源池已满，等待资源释放")
                        return self._pool.get(timeout=10.0)
                    
                    self._created_resources[key] = self._factory.create_resource(key)
                    self._creation_count += 1
                
                return self._created_resources[key]
    
    def _release_resource(self, resource: T) -> None:
        """释放资源回池中"""
        try:
            self._pool.put_nowait(resource)
        except queue.Full:
            # 池已满，销毁资源
            self._factory.destroy_resource(resource)
            with self._lock.acquire_lock():
                self._creation_count -= 1

class ConcurrentTaskManager:
    """并发任务管理器 - 单一职责：管理并发任务"""
    
    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers if max_workers is not None else 4
        self._active_threads: Dict[int, threading.Thread] = {}
        self._lock = ThreadSafeLock()
        self._shutdown = threading.Event()
    
    def submit_task(self, target, args=(), kwargs=None) -> threading.Thread:
        """提交任务到线程池"""
        if kwargs is None:
            kwargs = {}
        
        with self._lock.acquire_lock():
            if len(self._active_threads) >= self._max_workers:
                raise RuntimeError("线程池已满，无法提交新任务")
            
            thread = threading.Thread(
                target=self._task_wrapper,
                args=(target, args, kwargs)
            )
            thread.daemon = False  # 避免daemon线程问题
            thread.start()
            
            # 确保thread.ident不为None
            if thread.ident is not None:
                self._active_threads[thread.ident] = thread
            return thread
    
    def _task_wrapper(self, target, args, kwargs):
        """任务包装器"""
        try:
            target(*args, **kwargs)
        except Exception as e:
            logger.error(f"线程任务执行失败: {e}")
        finally:
            # 清理线程引用
            thread_id = threading.current_thread().ident
            if thread_id is not None:
                with self._lock.acquire_lock():
                    if thread_id in self._active_threads:
                        del self._active_threads[thread_id]
    
    def wait_all_tasks(self, timeout: Optional[float] = None):
        """等待所有任务完成"""
        start_time = time.time()
        
        while True:
            with self._lock.acquire_lock():
                active_threads = list(self._active_threads.values())
            
            if not active_threads:
                break
            
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"等待任务超时，仍有{len(active_threads)}个活跃线程")
                break
            
            # 等待最多1秒
            for thread in active_threads[:3]:  # 只等待前3个线程
                thread.join(timeout=1.0)
            
            time.sleep(0.1)
    
    def shutdown(self, timeout: float = 10.0):
        """优雅关闭任务管理器"""
        self._shutdown.set()
        self.wait_all_tasks(timeout)
        
        # 强制结束剩余线程
        with self._lock.acquire_lock():
            if self._active_threads:
                logger.warning(f"强制结束{len(self._active_threads)}个剩余线程")

class ThreadSafeCounter:
    """线程安全计数器 - 单一职责：管理计数"""
    
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.Lock()
    
    def increment(self, delta: int = 1) -> int:
        """增加计数"""
        with self._lock:
            self._value += delta
            return self._value
    
    def decrement(self, delta: int = 1) -> int:
        """减少计数"""
        with self._lock:
            self._value -= delta
            return self._value
    
    def get_value(self) -> int:
        """获取当前值"""
        with self._lock:
            return self._value
    
    def reset(self) -> int:
        """重置计数"""
        with self._lock:
            old_value = self._value
            self._value = 0
            return old_value

# Open/Closed Principle - 对扩展开放，对修改封闭
class ThreadSafeCache(Generic[T]):
    """线程安全缓存 - 单一职责：管理缓存"""
    
    def __init__(self, max_size: int = 100):
        self._cache: Dict[str, T] = {}
        self._access_order: queue.Queue[str] = queue.Queue()
        self._max_size = max_size
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        with self._lock:
            return self._cache.get(key)
    
    def put(self, key: str, value: T) -> None:
        """存储缓存值"""
        with self._lock:
            if key not in self._cache and len(self._cache) >= self._max_size:
                # LRU淘汰
                self._evict_oldest()
            
            if key not in self._cache:
                self._access_order.put(key)
            
            self._cache[key] = value
    
    def _evict_oldest(self) -> None:
        """淘汰最旧的缓存项"""
        try:
            oldest_key = self._access_order.get_nowait()
            if oldest_key in self._cache:
                del self._cache[oldest_key]
        except queue.Empty:
            pass
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            # 清空队列
            while not self._access_order.empty():
                try:
                    self._access_order.get_nowait()
                except queue.Empty:
                    break
    
    def size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)

# Dependency Inversion Principle - 依赖抽象而非具体实现
class ConcurrencyManager:
    """并发管理器 - 协调各种并发组件"""
    
    def __init__(self, max_workers: int = 4, max_cache_size: int = 100):
        self.task_manager = ConcurrentTaskManager(max_workers)
        self.cache = ThreadSafeCache(max_cache_size)
        self.counters: Dict[str, ThreadSafeCounter] = {}
        self._lock = threading.Lock()
    
    def get_counter(self, name: str) -> ThreadSafeCounter:
        """获取或创建计数器"""
        with self._lock:
            if name not in self.counters:
                self.counters[name] = ThreadSafeCounter()
            return self.counters[name]
    
    def shutdown(self, timeout: float = 10.0):
        """优雅关闭"""
        self.task_manager.shutdown(timeout)
        self.cache.clear()
        self.counters.clear()

# 全局实例 - 遵循单例模式但允许测试时替换
_concurrency_manager: Optional[ConcurrencyManager] = None

def get_concurrency_manager() -> ConcurrencyManager:
    """获取全局并发管理器实例"""
    global _concurrency_manager
    if _concurrency_manager is None:
        _concurrency_manager = ConcurrencyManager()
    return _concurrency_manager

def set_concurrency_manager(manager: ConcurrencyManager) -> None:
    """设置并发管理器实例（主要用于测试）"""
    global _concurrency_manager
    _concurrency_manager = manager 