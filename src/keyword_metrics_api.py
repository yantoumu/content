#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词指标批量 API 交互模块
遵循单一职责：仅负责与 /api/v1/keyword-metrics/batch 通讯。
大部分实现复用自 sitemap_api，并做结构精简，保持 <300 行。
"""

from __future__ import annotations

import gzip
import json
import logging
from typing import Any, Dict, List, Callable, Tuple

import requests

from src.config import config

logger = logging.getLogger("content_watcher.keyword_metrics_api")


class KeywordMetricsAPI:
    """负责提交关键词指标批量数据"""

    def __init__(self) -> None:
        self.batch_api_url: str = config.metrics_batch_api_url
        self.api_key: str = config.sitemap_api_key  # 继续复用同一 Key
        self.enabled: bool = config.metrics_api_enabled
        self.max_batch_size: int = 100  # 新接口限制
        self.use_gzip: bool = True

        if self.enabled:
            logger.info("KeywordMetricsAPI 初始化完成，已启用")
        else:
            logger.warning("KeywordMetricsAPI 未启用，提交将被跳过")

    # ---------- 静态工具 ----------
    @staticmethod
    def _compress_json_data(data: Any) -> bytes:
        """gzip 压缩 JSON，可接受 list/dict"""
        json_bytes = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return gzip.compress(json_bytes, compresslevel=9)

    @staticmethod
    def _handle_response(resp: requests.Response) -> Tuple[bool, str]:
        """基础响应处理：200->success, 429/5xx->retry, 其他->fail"""
        status = resp.status_code
        if status == 200:
            return True, "success"
        if status in {429, 500, 502, 503, 504}:
            logger.warning(f"服务器暂不可用({status})，建议重试")
            logger.warning(f"失败的API URL: {resp.url}")
            return False, "retry"
        logger.error(f"请求失败({status})，不重试")
        logger.error(f"失败的API URL: {resp.url}")
        return False, "fail"

    @staticmethod
    def _execute_with_retry(request_func: Callable[[int], requests.Response], max_retries: int = 2) -> bool:
        for retry in range(max_retries + 1):
            try:
                resp = request_func(retry)
                ok, reason = KeywordMetricsAPI._handle_response(resp)
                if ok:
                    return True
                if reason != "retry":
                    return False
            except requests.exceptions.RequestException as e:
                if retry >= max_retries:
                    logger.error(f"请求异常且超出重试次数: {e}")
                    logger.error(f"异常的API URL: {config.metrics_batch_api_url}")
                    return False
                wait = 2 ** retry
                logger.warning(f"请求异常({e})，{wait}s 后重试 {retry+1}/{max_retries}")
                logger.warning(f"异常的API URL: {config.metrics_batch_api_url}")
                import time
                time.sleep(wait)
        return False

    # ---------- 业务方法 ----------
    def prepare_update_data(self, url: str, keywords: List[str], keyword_data: Dict[str, Any]) -> Dict[str, Any]:
        """将旧结构转换为新接口所需结构。取首关键词与 metrics。"""
        keyword = keywords[0] if keywords and keywords[0] else ""

        # 默认指标占位，确保 monthly_searches 非空，使用新JSON格式
        metrics: Dict[str, Any] = {
            "avg_monthly_searches": 0,
            "competition": "LOW",
            "competition_index": 0,
            "monthly_searches": []
        }

        # 若存在有效数据则覆盖默认
        if keyword_data and keyword_data.get("data"):
            first_item = keyword_data["data"][0]
            if isinstance(first_item, dict) and "metrics" in first_item:
                metrics = first_item["metrics"]

        # 转换新JSON格式的中文字段为sitemap API期望的英文字段
        metrics = self._convert_monthly_searches_format(metrics)

        # 确保 monthly_searches 至少有 1 条记录
        if not metrics.get("monthly_searches"):
            import datetime
            now = datetime.datetime.now()
            metrics["monthly_searches"] = [{"year": str(now.year), "month": str(now.month), "searches": 0}]

        return {
            "keyword": keyword,
            "url": url,
            "metrics": metrics
        }

    def send_batch_updates(self, items: List[Dict[str, Any]], max_retries: int = 2) -> bool:
        """发送批量数据。items 直接是数组。"""
        if not self.enabled:
            logger.debug("API 未启用，跳过发送")
            return False
        if not items:
            logger.warning("空 items，跳过发送")
            return False
        if len(items) > self.max_batch_size:
            logger.warning(f"items 数量({len(items)}) 超过限制({self.max_batch_size})，将被截断")
            items = items[: self.max_batch_size]

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "Accept-Encoding": "gzip",
        }

        def do_request(retry_cnt: int) -> requests.Response:
            if retry_cnt == 0:
                logger.info(f"提交 {len(items)} 条关键词指标数据")
            else:
                logger.info(f"重试提交({retry_cnt}) 共 {len(items)} 条")

            if self.use_gzip:
                headers_local = dict(headers)
                headers_local["Content-Encoding"] = "gzip"
                data = self._compress_json_data(items)
                return requests.post(self.batch_api_url, headers=headers_local, data=data, timeout=80)
            return requests.post(self.batch_api_url, headers=headers, json=items, timeout=80)

        return self._execute_with_retry(do_request, max_retries)

    def _convert_monthly_searches_format(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """转换新JSON格式的中文字段为sitemap API期望的英文字段和字符串类型

        Args:
            metrics: 包含月度搜索数据的指标字典

        Returns:
            转换后的指标字典
        """
        if not metrics.get("monthly_searches"):
            return metrics

        converted_monthly_searches = []
        for month_data in metrics["monthly_searches"]:
            if not isinstance(month_data, dict):
                continue

            converted_item = {}

            # 转换年份字段：年 -> year，数字 -> 字符串，提供默认值
            year_value = None
            if "年" in month_data and month_data["年"] is not None:
                try:
                    year_value = str(month_data["年"])
                except (TypeError, ValueError):
                    year_value = "2024"  # 默认年份
            elif "year" in month_data and month_data["year"] is not None:
                try:
                    year_value = str(month_data["year"])
                except (TypeError, ValueError):
                    year_value = "2024"  # 默认年份
            else:
                year_value = "2024"  # 默认年份

            # 转换月份字段：月 -> month，数字 -> 字符串，提供默认值
            month_value = None
            if "月" in month_data and month_data["月"] is not None:
                try:
                    month_value = str(month_data["月"])
                except (TypeError, ValueError):
                    month_value = "1"  # 默认月份
            elif "month" in month_data and month_data["month"] is not None:
                try:
                    month_value = str(month_data["month"])
                except (TypeError, ValueError):
                    month_value = "1"  # 默认月份
            else:
                month_value = "1"  # 默认月份

            # 构建转换后的数据项
            converted_item = {
                "year": year_value,
                "month": month_value,
                "searches": month_data.get("searches", 0)  # 提供默认搜索量
            }

            converted_monthly_searches.append(converted_item)

        # 只在有转换时才拷贝数据，优化性能
        if converted_monthly_searches:
            metrics = metrics.copy()  # 避免修改原始数据
            metrics["monthly_searches"] = converted_monthly_searches

        return metrics


# 创建单例供全局使用
metrics_api = KeywordMetricsAPI()