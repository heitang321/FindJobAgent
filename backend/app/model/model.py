from langchain_openai import ChatOpenAI

import os
from pathlib import Path
from dotenv import load_dotenv

# 定位项目根目录的 .env 文件（相对于 model.py 的位置：app/ai/model/model.py → 向上4层到项目根）
project_root = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=project_root / ".env")
# 定义一个类
class MyModel:
    # 定义类变量
    _model = None
    # 定义静态方法
    @staticmethod
    def get_model():
        if MyModel._model is None:
            MyModel._model = ChatOpenAI(model = os.getenv("MODEL_NAME"),streaming =True )
        return MyModel._model


if __name__ == "__main__":
    model=MyModel.get_model()
    rs=model.invoke("你好")
    print(rs.content)