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
        self.max_batch_size: int = config.metrics_api_max_batch_size  # 使用配置值而非硬编码
        self.use_gzip: bool = True

        if self.enabled:
            logger.info("KeywordMetricsAPI 初始化完成，已启用")
        else:
            logger.warning("KeywordMetricsAPI 未启用，提交将被跳过")

    # ---------- 静态工具 ----------
    @staticmethod
    def _compress_json_data(data: Any) -> bytes:
        """gzip 压缩 JSON，可接受 list/dict

        Args:
            data: 要压缩的数据

        Returns:
            压缩后的字节数据

        Raises:
            Exception: 压缩失败时抛出异常
        """
        try:
            json_bytes = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            compressed_data = gzip.compress(json_bytes, compresslevel=9)

            # 验证压缩效果
            if len(compressed_data) >= len(json_bytes):
                logger.warning(f"压缩效果不佳: 原始{len(json_bytes)}字节 -> 压缩{len(compressed_data)}字节")
            else:
                compression_ratio = (1 - len(compressed_data) / len(json_bytes)) * 100
                logger.debug(f"压缩成功: {len(json_bytes)}字节 -> {len(compressed_data)}字节 (压缩比{compression_ratio:.1f}%)")

            # 在调试模式下验证数据完整性
            if logger.isEnabledFor(logging.DEBUG):
                if not KeywordMetricsAPI._verify_compression_integrity(data, compressed_data):
                    raise ValueError("压缩数据完整性验证失败")
                logger.debug("压缩数据完整性验证通过")

            return compressed_data

        except Exception as e:
            logger.error(f"JSON压缩失败: {e}")
            raise

    @staticmethod
    def _verify_compression_integrity(original_data: Any, compressed_data: bytes) -> bool:
        """验证压缩数据的完整性

        Args:
            original_data: 原始数据
            compressed_data: 压缩后的数据

        Returns:
            bool: 数据完整性验证结果
        """
        try:
            # 解压数据
            decompressed_bytes = gzip.decompress(compressed_data)
            decompressed_json = decompressed_bytes.decode('utf-8')
            decompressed_data = json.loads(decompressed_json)

            # 比较数据
            original_json = json.dumps(original_data, ensure_ascii=False, separators=(",", ":"))
            reconstructed_json = json.dumps(decompressed_data, ensure_ascii=False, separators=(",", ":"))

            is_valid = original_json == reconstructed_json
            if not is_valid:
                logger.error("压缩数据完整性验证失败：解压后数据与原始数据不匹配")

            return is_valid

        except Exception as e:
            logger.error(f"压缩数据完整性验证异常: {e}")
            return False

    @staticmethod
    def _handle_response(resp: requests.Response) -> Tuple[bool, str]:
        """基础响应处理：200->success, 429/5xx->retry, 其他->fail"""
        status = resp.status_code
        if status == 200:
            return True, "success"
        if status in {429, 500, 502, 503, 504}:
            logger.warning(f"服务器暂不可用({status})，建议重试")
            from src.privacy_utils import PrivacyMasker
            masked_url = PrivacyMasker.mask_api_url(str(resp.url))
            logger.warning(f"失败的API URL: {masked_url}")
            return False, "retry"
        logger.error(f"请求失败({status})，不重试")
        from src.privacy_utils import PrivacyMasker
        masked_url = PrivacyMasker.mask_api_url(str(resp.url))
        logger.error(f"失败的API URL: {masked_url}")
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
                    from src.privacy_utils import PrivacyMasker
                    masked_url = PrivacyMasker.mask_api_url(config.metrics_batch_api_url)
                    logger.error(f"异常的API URL: {masked_url}")
                    return False
                wait = 2 ** retry
                logger.warning(f"请求异常({e})，{wait}s 后重试 {retry+1}/{max_retries}")
                from src.privacy_utils import PrivacyMasker
                masked_url = PrivacyMasker.mask_api_url(config.metrics_batch_api_url)
                logger.warning(f"异常的API URL: {masked_url}")
                import time
                time.sleep(wait)
        return False

    # ---------- 业务方法 ----------
    def prepare_update_data(self, url: str, keywords: List[str], keyword_data: Dict[str, Any]) -> Dict[str, Any]:
        """将旧结构转换为新接口所需结构。取首关键词与 metrics。

        注意：此方法只应该处理已验证的真实数据，不应该创建默认值。
        """
        keyword = keywords[0] if keywords and keywords[0] else ""

        # 验证输入数据的有效性
        if not keyword_data or not keyword_data.get("data"):
            raise ValueError(f"无效的关键词数据，无法为关键词 '{keyword}' 创建更新数据")

        first_item = keyword_data["data"][0]
        if not isinstance(first_item, dict) or "metrics" not in first_item:
            raise ValueError(f"关键词数据格式错误，无法为关键词 '{keyword}' 创建更新数据")

        # 使用真实的API数据
        metrics = first_item["metrics"]

        # 验证关键指标是否存在
        required_fields = ['avg_monthly_searches', 'competition', 'competition_index']
        for field in required_fields:
            if field not in metrics:
                from src.privacy_utils import PrivacyMasker
                masked_keyword = PrivacyMasker.mask_keyword(keyword)
                raise ValueError(f"关键词数据缺少必要字段 '{field}'，无法为关键词 '{masked_keyword}' 创建更新数据")

        # 转换新JSON格式的中文字段为sitemap API期望的英文字段
        metrics = self._convert_monthly_searches_format(metrics)

        # 确保 monthly_searches 字段存在（但不创建虚假数据）
        if not metrics.get("monthly_searches"):
            from src.privacy_utils import PrivacyMasker
            masked_keyword = PrivacyMasker.mask_keyword(keyword)
            logger.warning(f"关键词 '{masked_keyword}' 缺少月度搜索数据")
            # 如果没有月度数据，使用空数组而不是创建虚假数据
            metrics["monthly_searches"] = []

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

            # 尝试使用gzip压缩发送
            if self.use_gzip:
                try:
                    headers_local = dict(headers)
                    headers_local["Content-Encoding"] = "gzip"
                    # 注意：保持Content-Type为application/json，因为压缩的是JSON数据
                    data = self._compress_json_data(items)

                    logger.debug(f"使用gzip压缩发送数据，压缩后大小: {len(data)} 字节")
                    return requests.post(self.batch_api_url, headers=headers_local, data=data, timeout=80)

                except Exception as e:
                    logger.warning(f"gzip压缩失败，降级到非压缩模式: {e}")
                    # 压缩失败时降级到非压缩模式
                    return requests.post(self.batch_api_url, headers=headers, json=items, timeout=80)

            # 非压缩模式
            logger.debug(f"使用非压缩模式发送数据")
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

            # 转换年份字段：年 -> year，保持原始类型（数字或字符串），提供默认值
            year_value = None
            if "年" in month_data and month_data["年"] is not None:
                year_value = month_data["年"]  # 保持原始类型
            elif "year" in month_data and month_data["year"] is not None:
                year_value = month_data["year"]  # 保持原始类型
            else:
                year_value = 2024  # 默认年份（数字类型，与上游API一致）

            # 转换月份字段：月 -> month，保持原始类型（数字或字符串），提供默认值
            month_value = None
            if "月" in month_data and month_data["月"] is not None:
                month_value = month_data["月"]  # 保持原始类型
            elif "month" in month_data and month_data["month"] is not None:
                month_value = month_data["month"]  # 保持原始类型
            else:
                month_value = 1  # 默认月份（数字类型，与上游API一致）

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