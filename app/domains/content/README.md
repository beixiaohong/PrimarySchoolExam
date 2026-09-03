# D2 内容与教研域

词库/词组/句子、语法、古诗文、知识点树、教材版本、网课、阅读素材；题库采集与解析。

- 数据归属：words word_books phrases sentences grammar_points classical_texts knowledge_points reading_passages papers paper_questions 等
- 迁入代码：words.py phrases.py grammar.py classical/ knowledge.py textbook.py courses.py reading.py + 内容类 admin + init_data/ paper_crawler.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
