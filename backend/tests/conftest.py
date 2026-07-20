"""从仓库根目录运行测试时的 Pytest 路径设置。"""

import os
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 单元测试不得依赖开发机上的 MySQL 服务或污染真实用户/任务数据。
os.environ.setdefault("TESTING", "True")
