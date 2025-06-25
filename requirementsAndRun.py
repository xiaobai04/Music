"""在启动应用程序前安装缺失依赖的工具脚本。"""

import subprocess
import pkg_resources
import sys
import os

def install_missing_packages(requirements_file: str):
    """根据 requirements 文件安装缺少的 Python 包。"""
    # 解析 requirements.txt
    with open(requirements_file, "r", encoding="utf-8") as f:
        required = list(pkg_resources.parse_requirements(f))

    installed = {pkg.key for pkg in pkg_resources.working_set}
    # 过滤已安装的包，得到缺失的列表
    missing = [
        str(r)
        for r in required
        if str(r).lower().split("==")[0] not in installed
    ]

    if missing:
        print("检测到未安装的依赖，正在安装：", missing)
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    else:
        print("所有依赖已安装。")

# 当脚本被直接执行时安装依赖并退出
if __name__ == "__main__":
    req_file = "requirements.txt"
    if not os.path.exists(req_file):
        print("未找到 requirements.txt")
        sys.exit(1)

    install_missing_packages(req_file)
