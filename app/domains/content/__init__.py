"""D2 内容与教研域（content）

职责：词库/词组/句子、语法、古诗文、知识点树、教材版本、网课、阅读素材；题库采集与解析。

边界纪律（S1-R）：
- 数据归属：words word_books phrases sentences grammar_points classical_texts knowledge_points reading_passages papers paper_questions 等
- 迁入代码：words.py phrases.py grammar.py classical/ knowledge.py textbook.py courses.py reading.py + 内容类 admin + init_data/ paper_crawler.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
