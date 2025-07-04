#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用启动器 - 单一职责：环境初始化
符合 SRP：仅负责启动环境配置
符合 OCP：可扩展新的环境配置而无需修改
符合 KISS：简单直接，易于理解
"""

import sys
import os
from pathlib import Path


def setup_python_path():
    """设置 Python 路径 - 确保能找到项目模块"""
    # 获取启动器所在目录（即项目根目录）
    project_root = Path(__file__).parent.absolute()
    
    # 确保项目根目录在 Python 路径最前面
    sys.path.insert(0, str(project_root))
    
    # 返回项目根目录供后续使用
    return project_root


def main():
    """启动应用"""
    # 1. 设置 Python 路径
    project_root = setup_python_path()
    
    # 2. 切换工作目录到项目根目录（确保相对路径正确）
    os.chdir(project_root)
    
    # 3. 导入并运行主程序
    from main import main as app_main
    return app_main()


if __name__ == "__main__":
    exit(main())