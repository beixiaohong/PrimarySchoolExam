"""数据模型包：统一导出全部 ORM 模型类，供 `Base.metadata` 建表与各模块 import。

新增模型三步：
1. 在 `models/<x>.py` 定义类（继承 `database.Base`）；
2. 在本文件 `from .<x> import <类名>` 导出（否则建表时会漏表）；
3. 新增 `app/migrations/versions/0NN_*.py` 幂等建表脚本。`create_all` 会自动建新表，
   但生产环境仍建议显式写迁移，便于回滚与审计。

注意：MySQL 的 TEXT / MEDIUMTEXT 列**不允许 DEFAULT**，跨方言加列请用
`database._ensure_column()`；大文本用 `paper.py` 的 `_longtext()` 做方言自适应。
"""
from .word import Word, WordBook
from .phrase import Phrase, Sentence
from .problem_type import ProblemType, ProblemCategory
from .exam import ExamRecord, Question, WrongRecord, ExamAttempt, AttemptAnswer
from .vocab import VocabProgress, VocabDailyLog
from .classical import ClassicalText, ClassicalProgress, ClassicalDailyLog
from .grammar import GrammarPoint, GrammarExercise
from .study_error import StudyError
from .user import User, VipUser
from .auth import AuthCode
from .admin import Admin, AdminOperationLog, SystemConfig
from .diamond import DiamondAccount, DiamondLedger
from .makeup_card import MakeupCard, MakeupUsageLog
from .custom_task import CustomTask
from .daily_task import DailyTask
from .parent import ParentPassword, ExamMinCount, ParentMessage, ParentTaskSettings
from .appeal import AnswerAppeal
from .reward import RewardCoupon, WishItem, GoalItem
from .pet import CoinLedger, PetProfile
from .badge import BadgeEarned
from .focus import FocusSession
from .mood import MoodCheckin
from .ai_usage import AIUsageLog, WeeklyReport, AiQa
from .metrics import MetricDaily
from .sprint4 import ChallengeRecord, TeachingRecord
from .middle import MiddleQuestion, TeachingProgress
from .paper import Paper, PaperQuestion
from .sync import SyncQuizLog
from .essay import EssayGrade
from .reading import ReadingPassage
from .content_review import ContentReview
from .parent_custom_task import ParentCustomTask
from .task_confirm import TaskConfirm
from .ledger import Bill, Account, Location, Merchant, Person, Project, Category, NotificationLog, UserReportSettings, RecurringTransaction
from .im import Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt
from .announcement import Announcement
from .judge_review import JudgeReviewIssue
from .textbook import TextbookVersion, UserTextbookPref
from .online_course import OnlineCourse
from .knowledge import KnowledgePoint
from .kp_map import QuestionKpMap
from .mastery import MasteryRecord, MasterySnapshot
from .learning_goal import LearningGoal, LearningCheckin, LearningWeeklyReview

__all__ = [
    "Word", "WordBook",
    "Phrase", "Sentence",
    "ProblemType", "ProblemCategory",
    "ExamRecord", "Question", "WrongRecord",
    "ExamAttempt", "AttemptAnswer",
    "VocabProgress", "VocabDailyLog",
    "ClassicalText", "ClassicalProgress", "ClassicalDailyLog",
    "GrammarPoint", "GrammarExercise",
    "StudyError",
    "User", "VipUser",
    "AuthCode",
    "Admin", "AdminOperationLog", "SystemConfig", "AdminPermission", "AdminRolePermission",
    "DiamondAccount", "DiamondLedger",
    "MakeupCard", "MakeupUsageLog",
    "CustomTask",
    "DailyTask",
    "ParentPassword", "ExamMinCount", "ParentMessage", "ParentTaskSettings",
    "AnswerAppeal",
    "RewardCoupon", "WishItem", "GoalItem",
    "CoinLedger", "PetProfile",
    "BadgeEarned",
    "FocusSession",
    "MoodCheckin",
    "AIUsageLog", "WeeklyReport", "AiQa",
    "MetricDaily",
    "ChallengeRecord", "TeachingRecord",
    "MiddleQuestion", "TeachingProgress",
    "Paper", "PaperQuestion",
    "SyncQuizLog",
    "EssayGrade",
    "ReadingPassage",
    "ContentReview",
    "ParentCustomTask",
    "TaskConfirm",
    "Bill", "Account", "Location", "Merchant", "Person", "Project", "Category",
    "NotificationLog", "UserReportSettings", "RecurringTransaction",
    "Chat", "Message", "Friendship", "GroupMember", "RedPacket", "RedPacketClaim", "ReadReceipt",
    "Announcement",
    "JudgeReviewIssue",
    "TextbookVersion", "UserTextbookPref",
    "OnlineCourse",
    "KnowledgePoint",
    "MasteryRecord", "MasterySnapshot",
    "Product", "ProductBenefit", "Order", "PayTransaction",
    "LearningGoal", "LearningCheckin", "LearningWeeklyReview",
]
