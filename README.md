#试卷系统
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version          # 确认显示 3.12.x
python -m pip install --upgrade pip
pip install -r requirements.txt

python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

更新：pip freeze > requirements.txt


├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置（DB路径、输出目录）
│   ├── database.py             # SQLAlchemy + SQLite
│   ├── models/                 # 数据模型
│   │   ├── word.py             # WordBook + Word
│   │   ├── problem_type.py     # ProblemCategory + ProblemType
│   │   └── exam.py             # ExamRecord
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── routers/                # API 路由
│   │   ├── words.py            # 单词CRUD + CSV/Excel导入
│   │   ├── math.py             # 题型管理 + 题目生成
│   │   └── exam.py             # 试卷生成 + 下载
│   ├── services/               # 业务逻辑
│   │   ├── math_generator.py   # 24个题型生成器（注册表模式）
│   │   ├── english_generator.py # 听写/选择/翻译/词组句
│   │   ├── docx_service.py     # Word文档输出
│   │   └── init_data.py        # 种子数据（首次启动自动导入）
│   └── data/
│       └── words_primary_school.csv  # 1860个小学单词（PEP 3-6年级）
├── requirements.txt
├── run.py                      # 启动入口
└── primary_school.db           # SQLite（自动生成）
启动方式：


cd PrimarySchoolExam
pip install -r requirements.txt
python run.py