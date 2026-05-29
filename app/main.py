# 统一导入所有需要的模块（遵循PEP8，集中在顶部）
from sqlalchemy import create_engine, Column, String, Integer, Float, Enum, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import enum
from fastapi import FastAPI, Body, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from openai import OpenAI
import bcrypt
import jwt
from datetime import datetime, timedelta
import os
from typing import Any, List, Optional, Union
import re
import copy

load_dotenv()

# 配置项（生产环境建议用.env文件）
SQLALCHEMY_DATABASE_URL = "sqlite:///./ap_project.db"
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "ap-planner-dev-secret-key-change-in-production-202405",
)  # 环境变量优先
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*").split(",")  # 生产环境配置具体域名
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 数据库初始化
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 枚举定义
class GradeTermEnum(str, enum.Enum):
    G9_UPPER = "9年级上"
    G9_LOWER = "9年级下"
    G10_UPPER = "10年级上"
    G10_LOWER = "10年级下"
    G11_UPPER = "11年级上"
    G11_LOWER = "11年级下"
    G12_UPPER = "12年级上"
    G12_LOWER = "12年级下"

class StandardTestTypeEnum(str, enum.Enum):
    TOEFL = "托福"
    IELTS = "雅思"
    DUOLINGO = "多邻国"

class SatActTypeEnum(str, enum.Enum):
    SAT = "SAT"
    ACT = "ACT"

# 数据库模型定义
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # 存储加密后的密码
    email = Column(String, nullable=True)
    name = Column(String)
    role = Column(String)
    current_grade_term = Column(Enum(GradeTermEnum))

class GPA(Base):
    __tablename__ = "gpas"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    grade_term = Column(Enum(GradeTermEnum))
    weighted_gpa = Column(Float, nullable=True)
    unweighted_gpa = Column(Float, nullable=True)

class APPlan(Base):
    __tablename__ = "ap_plans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    course = Column(String)
    score = Column(Integer)  # 0-5分，接口层需校验

class StandardTest(Base):
    __tablename__ = "standard_tests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    test_type = Column(Enum(StandardTestTypeEnum))
    score = Column(Float)

class SatAct(Base):
    __tablename__ = "sat_act"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    test_type = Column(Enum(SatActTypeEnum))
    score = Column(Integer)

class BackgroundProject(Base):
    __tablename__ = "background_projects"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    project_type = Column(String)
    project_name = Column(String, nullable=True)
    description = Column(String, nullable=True)

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    data = Column(JSON)

class AIPlanHistory(Base):
    __tablename__ = "ai_plan_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question = Column(String)
    answer = Column(String)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic 请求/响应模型（提前定义，避免接口找不到类）
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    code: int
    msg: str
    token: str

class UserInfoResponse(BaseModel):
    code: int
    data: dict | None = None
    msg: str = ""

class ProfileRequest(BaseModel):
    grade: Optional[str] = Field(None, description="当前年级")
    targetCountry: Optional[str] = Field(None, description="目标国家")
    major: Optional[str] = Field(None, description="目标专业")
    weightedGpa: Optional[Union[str, float]] = Field(None, description="加权GPA")
    unweightedGpa: Optional[Union[str, float]] = Field(None, description="未加权GPA")
    apCourses: List[dict[str, Any]] = Field(default_factory=list, description="AP课程")
    satAct: dict[str, Any] = Field(default_factory=dict, description="SAT/ACT成绩")
    languageTest: dict[str, Any] = Field(default_factory=dict, description="语言成绩")
    activity: dict[str, Any] = Field(default_factory=dict, description="活动背景")

class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="用户问题")

class UserSettingsRequest(BaseModel):
    email: Optional[str] = Field(None, description="邮箱")
    name: str = Field(..., min_length=1, description="真实姓名")
    current_grade_term: str = Field(..., pattern="^(9|10|11|12)年级(上|下)$", description="当前就读年级+学期")

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, description="旧密码")
    new_password: str = Field(..., min_length=8, description="新密码")

# ===================== 注册请求体模型 =====================
# GPA子模型（单学期GPA）
class GPARequest(BaseModel):
    grade_term: str = Field(..., description="年级学期（如9年级上）")
    weighted_gpa: Optional[float] = Field(None, ge=0, le=4, description="加权GPA（0-4）")
    unweighted_gpa: Optional[float] = Field(None, ge=0, le=4, description="未加权GPA（0-4）")

    # 校验：加权/未加权GPA不能全为空
    @validator("weighted_gpa", "unweighted_gpa", always=True)
    def check_gpa_not_empty(cls, v, values):
        if values.get("weighted_gpa") is None and values.get("unweighted_gpa") is None:
            raise ValueError("加权GPA和未加权GPA不能同时为空")
        return v

# AP课程成绩子模型
class APPlanRequest(BaseModel):
    course: str = Field(..., description="AP课程名称")
    score: int = Field(..., ge=0, le=5, description="AP成绩（0-5分）")

# 标化成绩子模型
class StandardTestRequest(BaseModel):
    test_type: str = Field(..., pattern="^(托福|雅思|多邻国)$", description="标化考试类型")
    score: float = Field(..., description="标化成绩")

    # 按考试类型校验成绩范围
    @validator("score")
    def check_standard_score(cls, v, values):
        test_type = values.get("test_type")
        if test_type == "托福" and not (0 <= v <= 120):
            raise ValueError("托福成绩范围为0-120")
        elif test_type == "雅思" and not (0 <= v <= 9):
            raise ValueError("雅思成绩范围为0-9")
        elif test_type == "多邻国" and not (0 <= v <= 160):
            raise ValueError("多邻国成绩范围为0-160")
        return v

# SAT/ACT成绩子模型
class SatActRequest(BaseModel):
    test_type: str = Field(..., pattern="^(SAT|ACT)$", description="SAT/ACT")
    score: int = Field(..., description="SAT/ACT成绩")

    # 校验成绩范围
    @validator("score")
    def check_sat_act_score(cls, v, values):
        test_type = values.get("test_type")
        if test_type == "SAT" and not (0 <= v <= 1600):
            raise ValueError("SAT成绩范围为0-1600")
        elif test_type == "ACT" and not (0 <= v <= 36):
            raise ValueError("ACT成绩范围为0-36")
        return v

# 背景提升项目子模型（预留）
class BackgroundProjectRequest(BaseModel):
    project_type: str = Field(..., pattern="^(竞赛|夏校|科研项目|学术项目|课外活动)$", description="项目类型")
    project_name: Optional[str] = Field(None, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")

# 主注册请求体模型
class RegisterRequest(BaseModel):
    # 基础信息
    username: str = Field(..., min_length=6, max_length=20, description="用户名（6-20位）")
    password: str = Field(..., min_length=8, description="密码（至少8位）")
    email: Optional[str] = Field(None, description="邮箱")
    name: str = Field(..., description="真实姓名")
    current_grade_term: str = Field(..., pattern="^(9|10|11|12)年级(上|下)$", description="当前就读年级+学期")
    
    # 升学资料注册后可在Profile页面继续完善
    gpa_list: List[GPARequest] = Field(default_factory=list, description="各学期GPA列表")
    
    # AP课程成绩
    ap_plans: List[APPlanRequest] = Field(default_factory=list, description="AP课程+成绩")
    
    # 标化成绩
    standard_tests: List[StandardTestRequest] = Field(default_factory=list, description="标化成绩")
    
    # SAT/ACT
    sat_act: Optional[SatActRequest] = Field(None, description="SAT/ACT成绩")
    
    # 背景提升（预留，可选）
    background_projects: Optional[List[BackgroundProjectRequest]] = Field(None, description="背景提升项目")

    # 校验GPA列表：根据当前年级校验必填学期
    @validator("gpa_list")
    def check_gpa_terms(cls, v, values):
        current_term = values.get("current_grade_term")
        if not current_term or not v:
            return v
        
        # 提取当前年级（9/10/11/12）和学期（上/下）
        grade = int(current_term.split("年级")[0])
        term = current_term.split("年级")[1]
        
        # 定义各年级需填写的学期
        required_terms = []
        if grade == 9:
            # 9年级（上/下）：仅当前学期必填（选填）
            pass
        elif grade == 10:
            # 10年级：9年级上下（选填）+10年级上（必填）
            required_terms = ["9年级上", "9年级下", "10年级上"]
        elif grade == 11:
            # 11年级：9年级上下（选填）+10年级上下+11年级上（必填）
            required_terms = ["10年级上", "10年级下", "11年级上"]
        elif grade == 12:
            # 12年级：9-11年级所有学期+12年级上（必填）
            required_terms = ["9年级上", "9年级下", "10年级上", "10年级下", "11年级上", "11年级下", "12年级上"]
        
        # 校验必填学期是否存在
        submitted_terms = [item.grade_term for item in v]
        for req_term in required_terms:
            if req_term not in submitted_terms:
                raise ValueError(f"当前为{current_term}，必须填写{req_term}的GPA")
        
        return v

def truncate_password_for_bcrypt(password: str) -> str:
    """按UTF-8字节截断到bcrypt支持的72字节。"""
    password_bytes = password.encode("utf-8")[:72]
    return password_bytes.decode("utf-8", errors="ignore")

def get_password_hash(password: str) -> str:
    """加密密码(处理bcrypt 72字节限制)"""
    password_bytes = truncate_password_for_bcrypt(password).encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = truncate_password_for_bcrypt(plain_password).encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))

# JWT 工具函数
def create_access_token(data: dict) -> str:
    """生成JWT Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def parse_token(token: str) -> int:
    """解析Token获取用户ID，失败则抛异常"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")

        if sub is None:
            raise HTTPException(status_code=401, detail="Token无效")

        return int(sub)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token已过期")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail="Token格式错误")

def get_user_id_from_authorization(authorization: str | None) -> tuple[Optional[int], Optional[dict]]:
    """统一解析Authorization，返回用户ID或接口风格错误响应。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None, {"code": 401, "msg": "缺少Token", "data": None}

    token = authorization.replace("Bearer ", "")

    try:
        return parse_token(token), None
    except HTTPException as e:
        return None, {"code": e.status_code, "msg": e.detail, "data": None}

def is_admission_related(message: str) -> bool:
    """本地判断问题是否属于升学规划范围，明显无关时不调用模型。"""
    text = message.lower()
    keywords = [
        "ap", "gpa", "sat", "act", "toefl", "ielts", "duolingo",
        "托福", "雅思", "多邻国", "标化", "绩点", "课程", "选课",
        "申请", "升学", "规划", "大学", "院校", "学校", "专业",
        "文书", "推荐信", "活动", "竞赛", "科研", "夏校", "背景",
        "留学", "美国", "英国", "加拿大", "香港", "计算机", "商科",
        "工程", "生物", "医学", "经济", "统计", "物理", "化学"
    ]
    return any(keyword in text for keyword in keywords)

AP_OFFICIAL_COURSES = [
    "AP 2-D Art and Design",
    "AP 3-D Art and Design",
    "AP Art History",
    "AP Drawing",
    "AP Music Theory",
    "AP English Language and Composition",
    "AP English Literature and Composition",
    "AP African American Studies",
    "AP Comparative Government and Politics",
    "AP European History",
    "AP Human Geography",
    "AP Macroeconomics",
    "AP Microeconomics",
    "AP Psychology",
    "AP United States Government and Politics",
    "AP United States History",
    "AP World History: Modern",
    "AP Calculus AB",
    "AP Calculus BC",
    "AP Computer Science A",
    "AP Computer Science Principles",
    "AP Precalculus",
    "AP Statistics",
    "AP Biology",
    "AP Chemistry",
    "AP Environmental Science",
    "AP Physics 1: Algebra-Based",
    "AP Physics 2: Algebra-Based",
    "AP Physics C: Electricity and Magnetism",
    "AP Physics C: Mechanics",
    "AP Chinese Language and Culture",
    "AP French Language and Culture",
    "AP German Language and Culture",
    "AP Italian Language and Culture",
    "AP Japanese Language and Culture",
    "AP Latin",
    "AP Spanish Language and Culture",
    "AP Spanish Literature and Culture",
    "AP Seminar",
    "AP Research",
    "AP Business with Personal Finance",
    "AP Cybersecurity",
]

COURSE_RECOMMENDATION_RULES = {
    "计算机": {
        "core": ["AP Calculus BC", "AP Computer Science A", "AP Statistics"],
        "support": ["AP Computer Science Principles", "AP Physics C: Mechanics"],
        "balance": ["AP English Language and Composition", "AP United States History", "AP Psychology"],
        "reason": "计算机方向需要数学、编程和数据能力，同时用一门写作或社科课程避免课程画像过度单一。",
    },
    "工程": {
        "core": ["AP Calculus BC", "AP Physics C: Mechanics", "AP Chemistry"],
        "support": ["AP Physics C: Electricity and Magnetism", "AP Statistics"],
        "balance": ["AP English Language and Composition", "AP Human Geography"],
        "reason": "工程方向重点看微积分、物理和自然科学强度，但仍需要沟通写作或社会议题理解来平衡申请画像。",
    },
    "商科": {
        "core": ["AP Microeconomics", "AP Macroeconomics", "AP Statistics"],
        "support": ["AP Calculus AB", "AP Calculus BC", "AP Business with Personal Finance"],
        "balance": ["AP English Language and Composition", "AP Psychology"],
        "reason": "商科/经济方向需要经济学、数据和数学基础，再用写作或心理学补足表达和人群理解。",
    },
    "生物医学": {
        "core": ["AP Biology", "AP Chemistry", "AP Statistics"],
        "support": ["AP Psychology", "AP Calculus AB"],
        "balance": ["AP English Language and Composition", "AP Human Geography"],
        "reason": "生物医学方向需要生物、化学和统计支撑，同时保留写作或社科课程体现医学人文意识。",
    },
    "人文社科": {
        "core": ["AP English Language and Composition", "AP United States History", "AP Psychology"],
        "support": ["AP Comparative Government and Politics", "AP World History: Modern"],
        "balance": ["AP Statistics", "AP Environmental Science"],
        "reason": "人文社科方向重点看阅读、写作、史料和社会分析能力，再用统计或环境科学补充数据视角。",
    },
    "艺术": {
        "core": ["AP 2-D Art and Design", "AP Drawing", "AP Art History"],
        "support": ["AP Music Theory", "AP 3-D Art and Design"],
        "balance": ["AP English Language and Composition", "AP Psychology"],
        "reason": "艺术方向需要作品集和艺术史理解，同时用写作或心理学强化表达、叙事和观众理解。",
    },
}

HUMANITIES_COURSE_HINTS = [
    "english", "history", "government", "psychology", "human geography",
    "art history", "language", "literature", "seminar", "research"
]

def to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def get_grade_number(grade: Optional[str]) -> Optional[int]:
    if not grade:
        return None

    match = re.search(r"(9|10|11|12)", grade)
    return int(match.group(1)) if match else None

def infer_major_track(major: Optional[str]) -> str:
    text = (major or "").lower()
    if any(keyword in text for keyword in ["计算机", "computer", "cs", "data", "数据", "ai", "人工智能", "软件"]):
        return "计算机"
    if any(keyword in text for keyword in ["工程", "engineer", "物理", "机械", "电子", "电气", "材料"]):
        return "工程"
    if any(keyword in text for keyword in ["商", "经济", "金融", "business", "econ", "finance", "management"]):
        return "商科"
    if any(keyword in text for keyword in ["生物", "医学", "医", "bio", "medicine", "health", "neuro"]):
        return "生物医学"
    if any(keyword in text for keyword in ["艺术", "设计", "音乐", "art", "design", "music", "architecture"]):
        return "艺术"
    if any(keyword in text for keyword in ["历史", "政治", "心理", "社会", "传媒", "文学", "教育", "human", "social"]):
        return "人文社科"
    return "未确定"

def get_language_status(profile_data: dict) -> dict:
    language = profile_data.get("languageTest") or {}
    test_type = language.get("type") or language.get("test_type") or ""
    score = to_float(language.get("score"))

    if score is None:
        return {"status": "missing", "label": "未填写", "score": None}

    if test_type == "托福":
        stable = score >= 100
        strong = score >= 105
    elif test_type == "雅思":
        stable = score >= 7
        strong = score >= 7.5
    elif test_type == "多邻国":
        stable = score >= 125
        strong = score >= 135
    else:
        stable = score >= 100
        strong = score >= 110

    if strong:
        status = "strong"
    elif stable:
        status = "stable"
    else:
        status = "weak"

    return {"status": status, "label": f"{test_type}{score:g}", "score": score}

def get_gpa_status(profile_data: dict) -> dict:
    weighted = to_float(profile_data.get("weightedGpa"))
    unweighted = to_float(profile_data.get("unweightedGpa"))
    anchor = unweighted if unweighted is not None else weighted

    if anchor is None:
        return {"status": "missing", "label": "未填写", "score": None}

    if unweighted is not None:
        if unweighted >= 3.8:
            status = "strong"
        elif unweighted >= 3.55:
            status = "stable"
        else:
            status = "weak"
    else:
        if weighted >= 4.15:
            status = "strong"
        elif weighted >= 3.85:
            status = "stable"
        else:
            status = "weak"

    label_parts = []
    if weighted is not None:
        label_parts.append(f"加权{weighted:g}")
    if unweighted is not None:
        label_parts.append(f"未加权{unweighted:g}")
    return {"status": status, "label": " / ".join(label_parts), "score": anchor}

def get_existing_ap_courses(profile_data: dict) -> list[dict]:
    courses = profile_data.get("apCourses") or []
    return [item for item in courses if isinstance(item, dict) and item.get("course")]

def get_course_interests(profile_data: dict) -> list[str]:
    interests = profile_data.get("courseInterests") or []
    return [item for item in interests if isinstance(item, str) and item.strip()]

def has_humanities_balance(ap_courses: list[dict], course_interests: Optional[list[str]] = None) -> bool:
    course_names = [str(item.get("course", "")) for item in ap_courses]
    course_names.extend(course_interests or [])

    for course_name in course_names:
        course = course_name.lower()
        if any(keyword in course for keyword in HUMANITIES_COURSE_HINTS):
            return True
    return False

def prioritize_interested_courses(courses: list[str], course_interests: list[str]) -> list[str]:
    interest_set = set(course_interests)
    return sorted(courses, key=lambda course: 0 if course in interest_set else 1)

def missing_profile_fields(profile_data: Optional[dict]) -> list[str]:
    if not profile_data:
        return ["grade", "targetCountry", "major"]

    required_fields = ["grade", "targetCountry", "major"]
    return [field for field in required_fields if not profile_data.get(field)]

def build_student_strategy(profile_data: Optional[dict]) -> dict:
    profile = profile_data or {}
    grade_number = get_grade_number(profile.get("grade"))
    country = profile.get("targetCountry") or "未填写"
    major_track = infer_major_track(profile.get("major"))
    gpa_status = get_gpa_status(profile)
    language_status = get_language_status(profile)
    ap_courses = get_existing_ap_courses(profile)
    course_interests = get_course_interests(profile)
    rules = COURSE_RECOMMENDATION_RULES.get(major_track) or COURSE_RECOMMENDATION_RULES["人文社科"]
    us_application = "美国" in country

    gpa_priority = 90 if grade_number in (9, 10) else 80
    if gpa_status["status"] in ["missing", "weak"]:
        gpa_priority = 100
    elif gpa_status["status"] == "stable":
        gpa_priority = max(gpa_priority, 85)
    else:
        gpa_priority = 75

    language_priority = 70 if us_application else 55
    if language_status["status"] == "missing":
        language_priority = 82 if grade_number in (10, 11) else 68
    elif language_status["status"] == "weak":
        language_priority = 90
    elif language_status["status"] == "stable":
        language_priority = 62
    elif language_status["status"] == "strong":
        language_priority = 45

    if gpa_status["status"] == "weak":
        ap_priority = 48
        ap_load = "先稳住校内成绩，AP建议控制在1-2门高相关课程。"
    elif grade_number in (9, 10):
        ap_priority = 62
        ap_load = "可以试探性选择1-2门与方向高度相关的AP，不要牺牲GPA。"
    elif grade_number == 11:
        ap_priority = 82
        ap_load = "可以形成3-5门核心AP组合，注意难度和出分确定性。"
    else:
        ap_priority = 58
        ap_load = "12年级更适合补强已有逻辑，不建议盲目增加高风险课程。"

    stable_gpa = gpa_status["status"] in ["stable", "strong"]
    stable_language = language_status["status"] in ["stable", "strong"]
    activity_priority = 58
    competition_priority = 50
    if stable_gpa and stable_language:
        activity_priority = 82
        competition_priority = 76
    elif gpa_status["status"] == "weak":
        activity_priority = 45
        competition_priority = 42
    elif grade_number in (10, 11):
        activity_priority = 68
        competition_priority = 62

    essay_priority = 28
    if grade_number == 11:
        essay_priority = 62
    elif grade_number == 12:
        essay_priority = 92

    exploration_priority = 70 if grade_number in (9, 10) else 45
    if major_track == "未确定":
        exploration_priority = 88

    priorities = [
        {"name": "GPA", "score": gpa_priority, "reason": f"当前GPA状态：{gpa_status['label']}。"},
        {"name": "语言成绩", "score": language_priority, "reason": f"当前语言状态：{language_status['label']}。"},
        {"name": "AP课程", "score": ap_priority, "reason": ap_load},
        {"name": "活动背景", "score": activity_priority, "reason": "在硬性成绩稳定后，用持续活动体现申请方向和个人画像。"},
        {"name": "竞赛/科研", "score": competition_priority, "reason": "适合作为专业兴趣证明，但不应压过GPA和语言短板。"},
        {"name": "文书准备", "score": essay_priority, "reason": "低年级先积累素材，高年级再集中打磨文书表达。"},
        {"name": "申请人设探索", "score": exploration_priority, "reason": "通过课程、活动和阅读逐步验证目标专业，不需要过早包装。"},
    ]
    priorities.sort(key=lambda item: item["score"], reverse=True)

    existing_course_names = {item.get("course") for item in ap_courses}
    included_core_courses = [course for course in rules["core"] if course in existing_course_names]
    included_support_courses = [course for course in rules["support"] if course in existing_course_names]
    included_balance_courses = [
        course
        for course in rules["balance"]
        if course in existing_course_names or course in course_interests
    ]
    core_courses = [course for course in rules["core"] if course not in existing_course_names]
    support_courses = [course for course in rules["support"] if course not in existing_course_names]
    balance_courses = []
    interested_balance_courses = [
        course
        for course in course_interests
        if course in rules["balance"] and course not in existing_course_names
    ]
    interested_support_courses = [
        course
        for course in course_interests
        if course in rules["support"] and course not in existing_course_names
    ]

    support_courses = prioritize_interested_courses(
        list(dict.fromkeys(interested_support_courses + support_courses)),
        course_interests,
    )
    if not has_humanities_balance(ap_courses):
        balance_courses = list(dict.fromkeys(interested_balance_courses + [
            course for course in rules["balance"] if course not in existing_course_names
        ]))
        balance_courses = prioritize_interested_courses(balance_courses, course_interests)

    weaknesses = []
    if gpa_status["status"] in ["missing", "weak"]:
        weaknesses.append("GPA是当前最大短板，优先保证校内成绩和课程稳定性。")
    if us_application and language_status["status"] in ["missing", "weak"]:
        weaknesses.append("语言成绩仍需尽快补齐或提高，否则会限制美国申请范围。")
    if not ap_courses:
        weaknesses.append("AP记录较少，需要从目标专业核心课开始建立课程强度。")
    elif not has_humanities_balance(ap_courses, course_interests):
        weaknesses.append("当前AP组合偏专业课，建议补一门写作/历史/社科类课程平衡画像。")
    if course_interests:
        weaknesses.append(f"你最近表达过对 {course_interests[-1]} 的兴趣，系统已纳入课程组合判断。")
    if not profile.get("activity", {}).get("description") and not profile.get("portfolio"):
        weaknesses.append("活动和背景信息不足，后续需要沉淀可描述、可持续的经历。")

    next_actions = [
        f"未来4-8周优先处理：{priorities[0]['name']}。",
        ap_load,
        "每次Profile更新或AI对话补充新成绩后，系统会重新计算优先级和短板。"
    ]
    if balance_courses:
        next_actions.append(f"为避免方向失衡，可从 {balance_courses[0]} 开始补充一门平衡课程。")

    return {
        "profile": {
            "grade": profile.get("grade") or "未填写",
            "targetCountry": country,
            "major": profile.get("major") or "未填写",
            "majorTrack": major_track,
            "gpaStatus": gpa_status,
            "languageStatus": language_status,
            "apCount": len(ap_courses),
            "courseInterests": course_interests,
        },
        "priorities": priorities,
        "coursePlan": {
            "includedCore": included_core_courses[:3],
            "includedSupport": included_support_courses[:2],
            "includedBalance": included_balance_courses[:2],
            "core": core_courses[:3],
            "support": support_courses[:2],
            "balance": balance_courses[:2],
            "loadAdvice": ap_load,
            "reason": rules["reason"],
        },
        "weaknesses": weaknesses,
        "nextActions": next_actions,
        "persona": {
            "direction": f"{major_track}方向申请者" if major_track != "未确定" else "仍在探索方向的申请者",
            "balance": "建议形成“专业核心能力 + 一门表达/人文/社科平衡课 + 可持续活动”的画像。",
        }
    }

def format_strategy_for_prompt(strategy: dict) -> str:
    priorities = "\n".join(
        [f"- {item['name']}：{item['score']}，{item['reason']}" for item in strategy["priorities"][:5]]
    )
    course_plan = strategy["coursePlan"]
    weaknesses = "\n".join([f"- {item}" for item in strategy["weaknesses"]]) or "- 暂无明显短板"
    return (
        f"画像方向：{strategy['persona']['direction']}\n"
        f"优先级：\n{priorities}\n"
        f"推荐核心AP：{', '.join(course_plan['core']) or '暂无'}\n"
        f"平衡课程：{', '.join(course_plan['balance']) or '暂无'}\n"
        f"短板：\n{weaknesses}"
    )

def normalize_course_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())

AP_COURSE_KEY_MAP = {normalize_course_key(course): course for course in AP_OFFICIAL_COURSES}

def find_official_ap_course(message: str) -> Optional[str]:
    compact_message = normalize_course_key(message)
    for key, course in AP_COURSE_KEY_MAP.items():
        if key and key in compact_message:
            return course

    aliases = {
        "calc bc": "AP Calculus BC",
        "calculus bc": "AP Calculus BC",
        "calc ab": "AP Calculus AB",
        "calculus ab": "AP Calculus AB",
        "csa": "AP Computer Science A",
        "csp": "AP Computer Science Principles",
        "physics c": "AP Physics C: Mechanics",
        "apush": "AP United States History",
        "psych": "AP Psychology",
        "ap心理": "AP Psychology",
        "心理学": "AP Psychology",
        "心理": "AP Psychology",
        "ap统计": "AP Statistics",
        "统计学": "AP Statistics",
        "ap微积分bc": "AP Calculus BC",
        "微积分bc": "AP Calculus BC",
        "ap微积分ab": "AP Calculus AB",
        "微积分ab": "AP Calculus AB",
        "ap计算机": "AP Computer Science A",
        "计算机a": "AP Computer Science A",
        "ap物理c": "AP Physics C: Mechanics",
        "ap生物": "AP Biology",
        "ap化学": "AP Chemistry",
        "ap宏观": "AP Macroeconomics",
        "ap微观": "AP Microeconomics",
        "stats": "AP Statistics",
        "bio": "AP Biology",
        "chem": "AP Chemistry",
        "macro": "AP Macroeconomics",
        "micro": "AP Microeconomics",
    }
    lower_message = message.lower()
    for alias, course in aliases.items():
        if alias in lower_message:
            return course
    return None

def add_course_interest(profile_data: dict, course: str) -> bool:
    interests = profile_data.setdefault("courseInterests", [])
    if course in interests:
        return False
    interests.append(course)
    return True

def remove_unscored_ap_course(profile_data: dict, course: str) -> bool:
    ap_courses = profile_data.get("apCourses") or []
    remaining_courses = [
        item
        for item in ap_courses
        if not (
            item.get("course") == course
            and str(item.get("score", "")).strip() in ["", "0", "暂未出分"]
        )
    ]
    changed = len(remaining_courses) != len(ap_courses)
    if changed:
        profile_data["apCourses"] = remaining_courses
    return changed

def upsert_ap_course(profile_data: dict, course: str, score: int) -> None:
    ap_courses = profile_data.setdefault("apCourses", [])
    for item in ap_courses:
        if item.get("course") == course:
            item["score"] = score
            return
    ap_courses.append({"course": course, "score": score})

def append_portfolio_item(profile_data: dict, bucket: str, description: str) -> bool:
    portfolio = profile_data.setdefault("portfolio", {})
    items = portfolio.setdefault(bucket, [])
    normalized = description.strip()
    if not normalized or normalized in items:
        return False
    items.append(normalized[:180])
    return True

def apply_profile_updates_from_message(message: str, profile_data: Optional[dict]) -> tuple[dict, list[str]]:
    data = copy.deepcopy(profile_data or {})
    updates = []
    text = message.strip()

    course = find_official_ap_course(text)
    if course:
        score_match = re.search(r"([1-5])\s*分", text)
        score = int(score_match.group(1)) if score_match else 0
        question_or_interest_intent = any(
            keyword in text
            for keyword in ["想学", "要学", "要不要", "适合", "推荐", "可以选", "该选", "是吗", "吗", "辅修", "感兴趣"]
        )
        is_confirmed_course = score > 0 or any(
            keyword in text
            for keyword in ["新增", "增加", "拿到", "获得", "考了", "出了", "已学", "在学", "选了"]
        )

        if is_confirmed_course and not question_or_interest_intent:
            upsert_ap_course(data, course, score)
            updates.append(f"AP课程：{course}，分数/目标 {score if score else '暂未出分'}")
        else:
            moved_from_ap = remove_unscored_ap_course(data, course)
            if add_course_interest(data, course) or moved_from_ap:
                updates.append(f"课程兴趣：{course}")

    gpa_match = re.search(r"(?:gpa|GPA)[：:\s]*(\d(?:\.\d+)?)", text)
    if gpa_match:
        gpa_value = gpa_match.group(1)
        if "加权" in text or "weighted" in text.lower():
            data["weightedGpa"] = gpa_value
            updates.append(f"加权GPA：{gpa_value}")
        else:
            data["unweightedGpa"] = gpa_value
            updates.append(f"未加权GPA：{gpa_value}")

    sat_match = re.search(r"\bSAT[：:\s]*(1[0-6]\d{2}|[4-9]\d{2})", text, re.IGNORECASE)
    act_match = re.search(r"\bACT[：:\s]*([1-3]?\d)", text, re.IGNORECASE)
    if sat_match:
        data["satAct"] = {"type": "SAT", "score": sat_match.group(1)}
        updates.append(f"SAT：{sat_match.group(1)}")
    elif act_match:
        data["satAct"] = {"type": "ACT", "score": act_match.group(1)}
        updates.append(f"ACT：{act_match.group(1)}")

    language_patterns = [
        ("托福", r"(?:托福|TOEFL)[：:\s]*(\d{2,3})"),
        ("雅思", r"(?:雅思|IELTS)[：:\s]*(\d(?:\.\d)?)"),
        ("多邻国", r"(?:多邻国|Duolingo)[：:\s]*(\d{2,3})"),
    ]
    for test_type, pattern in language_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["languageTest"] = {"type": test_type, "score": match.group(1)}
            updates.append(f"{test_type}：{match.group(1)}")
            break

    activity_buckets = [
        ("竞赛", "competitions"),
        ("科研", "research"),
        ("夏校", "summerPrograms"),
        ("志愿", "volunteer"),
        ("活动", "activities"),
    ]
    if any(verb in text for verb in ["参加", "新增", "增加", "完成", "获得", "拿到"]):
        for keyword, bucket in activity_buckets:
            if keyword in text and append_portfolio_item(data, bucket, text):
                updates.append(f"背景库新增：{keyword}")
                break

    return data, updates

def build_profile_summary(profile_data: Optional[dict]) -> str:
    if not profile_data:
        return "用户尚未完善个人Profile。"

    ap_courses = [
        f"{item.get('course', '')}({item.get('score', '')})"
        for item in profile_data.get("apCourses", [])
        if item.get("course")
    ]
    return (
        f"年级：{profile_data.get('grade') or '未填写'}\n"
        f"目标国家/地区：{profile_data.get('targetCountry') or '未填写'}\n"
        f"目标专业：{profile_data.get('major') or '未填写'}\n"
        f"加权GPA：{profile_data.get('weightedGpa') or '未填写'}\n"
        f"未加权GPA：{profile_data.get('unweightedGpa') or '未填写'}\n"
        f"AP课程：{', '.join(ap_courses) if ap_courses else '未填写'}\n"
        f"SAT/ACT：{profile_data.get('satAct') or '未填写'}\n"
        f"语言成绩：{profile_data.get('languageTest') or '未填写'}\n"
        f"活动背景：{profile_data.get('activity') or '未填写'}\n"
        f"背景库：{profile_data.get('portfolio') or '未填写'}"
    )

def local_planning_answer(message: str, profile_data: Optional[dict]) -> str:
    strategy = build_student_strategy(profile_data)
    course_plan = strategy["coursePlan"]
    included_courses = (
        course_plan.get("includedCore", [])
        + course_plan.get("includedSupport", [])
        + course_plan.get("includedBalance", [])
    )
    suggestions = [
        "这是基于当前资料生成的本地规划建议：",
        f"1. 当前画像：{strategy['persona']['direction']}，目标地区是 {strategy['profile']['targetCountry']}。",
        f"2. 当前最高优先级是 {strategy['priorities'][0]['name']}：{strategy['priorities'][0]['reason']}",
        f"3. AP核心建议：{', '.join(course_plan['core']) or '先补充目标专业和现有AP信息'}。",
    ]

    if included_courses:
        suggestions.append(f"4. 已纳入组合判断：{', '.join(included_courses)}。")
    elif course_plan["balance"]:
        suggestions.append(f"4. 为避免画像失衡，建议补充平衡课程：{', '.join(course_plan['balance'])}。")
    else:
        suggestions.append("4. 当前AP组合暂未发现明显失衡，下一步更适合围绕短板做深。")

    if strategy["weaknesses"]:
        suggestions.append(f"5. 当前短板：{strategy['weaknesses'][0]}")
    suggestions.append("你可以继续补充新成绩或活动，我会把它写入Profile库并重新计算优先级。")
    return "\n".join(suggestions)

def call_deepseek_ai(message: str, profile_summary: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DeepSeek API Key未配置")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是AP Planner的升学规划AI顾问。你只能回答AP课程、GPA、SAT/ACT、语言成绩、"
                    "申请规划、活动背景、目标专业、院校匹配、留学时间线相关问题。"
                    "如果用户提出无关问题，必须礼貌拒绝并引导回升学规划。"
                    "回答要具体、结构化、适合高中生和家长理解，避免编造确定录取结果。"
                )
            },
            {
                "role": "user",
                "content": f"用户Profile：\n{profile_summary}\n\n用户问题：{message}"
            }
        ],
        temperature=0.4,
        max_tokens=900,
    )
    return response.choices[0].message.content or "暂时无法生成回答。"

# 数据库依赖
def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"数据库错误: {str(e)}")
    finally:
        db.close()

# 创建数据库表
Base.metadata.create_all(bind=engine)

def ensure_user_email_column():
    """为已有SQLite数据库补齐email字段。"""
    with engine.connect() as connection:
        columns = connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()
        column_names = {column[1] for column in columns}
        if "email" not in column_names:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN email VARCHAR")
            connection.commit()

ensure_user_email_column()

# FastAPI 应用初始化
app = FastAPI(
    title="AP升学规划后端API",
    description="AP_Project_Backend 项目接口文档",
    version="1.0.0"
)

# 跨域配置（生产环境严格限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# 初始化测试用户
def create_test_user(db: Session):
    """创建测试用户（仅当不存在时）"""
    if not db.query(User).filter(User.username == "student123").first():
        test_user = User(
            username="student123",
            password=get_password_hash("12345678"),  # 加密存储
            email="student123@example.com",
            name="测试学生",
            role="student",
            current_grade_term=GradeTermEnum.G10_UPPER
        )
        db.add(test_user)
        db.commit()

# 执行测试用户创建
with SessionLocal() as db:
    create_test_user(db)

# 接口定义（无重复，逻辑完整）
@app.post("/api/login", summary="用户登录", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """用户登录接口（对接数据库，密码加密验证）"""
    # 查询用户
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        return {"code": 401, "msg": "用户名不存在", "token": ""}
    # 验证密码（加密）
    if not verify_password(data.password, user.password):
        return {"code": 401, "msg": "密码错误", "token": ""}
    # 生成JWT Token
    token = create_access_token({"sub": str(user.id)})
    return {"code": 200, "msg": "登录成功", "token": token}

@app.get("/api/user/info", summary="获取用户信息", response_model=UserInfoResponse)
def user_info(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """根据Token获取用户信息"""
    # 检查Authorization
    if not authorization or not authorization.startswith("Bearer "):
        return {"code": 401, "msg": "缺少Token", "data": None}

    # 提取真正token
    token = authorization.replace("Bearer ", "")

    try:
        user_id = parse_token(token)
    except HTTPException as e:
        return {"code": e.status_code, "msg": e.detail, "data": None}
    # 查询用户
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"code": 404, "msg": "用户不存在", "data": None}
    # 返回用户信息
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "current_grade_term": user.current_grade_term.value
        }
    }

@app.post("/api/user/settings", summary="更新用户设置")
def update_user_settings(
    data: UserSettingsRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"code": 404, "msg": "用户不存在", "data": None}

    user.email = data.email
    user.name = data.name
    user.current_grade_term = GradeTermEnum(data.current_grade_term)
    db.commit()

    return {"code": 200, "msg": "保存成功"}

@app.post("/api/user/password", summary="修改密码")
def change_password(
    data: ChangePasswordRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"code": 404, "msg": "用户不存在", "data": None}

    if not verify_password(data.old_password, user.password):
        return {"code": 400, "msg": "旧密码不正确", "data": None}

    user.password = get_password_hash(data.new_password)
    db.commit()
    return {"code": 200, "msg": "密码修改成功"}

@app.get("/api/ap/plans", summary="获取AP规划数据")
def get_ap_plans(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """获取当前用户的AP规划数据（对接APPlan表）"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"code": 401, "msg": "缺少Token", "data": None}

    token = authorization.replace("Bearer ", "")

    try:
        user_id = parse_token(token)
    except HTTPException as e:
        return {"code": e.status_code, "msg": e.detail, "data": None}
    # 查询AP规划
    ap_plans = db.query(APPlan).filter(APPlan.user_id == user_id).all()
    # 格式化数据
    data = [{"course": plan.course, "score": plan.score} for plan in ap_plans]
    return {"code": 200, "msg": "success", "data": data}

@app.post("/api/profile/save", summary="保存当前用户Profile")
def save_profile(
    data: ProfileRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """保存或更新当前登录用户的Profile资料"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"code": 401, "msg": "缺少Token", "data": None}

    token = authorization.replace("Bearer ", "")

    try:
        user_id = parse_token(token)
    except HTTPException as e:
        return {"code": e.status_code, "msg": e.detail, "data": None}

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    profile_data = data.model_dump()
    if profile and isinstance(profile.data, dict):
        for preserved_key in ["portfolio"]:
            if preserved_key in profile.data and preserved_key not in profile_data:
                profile_data[preserved_key] = profile.data[preserved_key]
        for preserved_key in ["courseInterests"]:
            if preserved_key in profile.data and preserved_key not in profile_data:
                profile_data[preserved_key] = profile.data[preserved_key]

    if profile:
        profile.data = profile_data
    else:
        profile = Profile(user_id=user_id, data=profile_data)
        db.add(profile)

    db.commit()
    return {"code": 200, "msg": "保存成功", "data": {"analysis": build_student_strategy(profile_data)}}

@app.get("/api/profile/me", summary="获取当前用户Profile")
def get_my_profile(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """获取当前登录用户保存过的Profile资料"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"code": 401, "msg": "缺少Token", "data": None}

    token = authorization.replace("Bearer ", "")

    try:
        user_id = parse_token(token)
    except HTTPException as e:
        return {"code": e.status_code, "msg": e.detail, "data": None}

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        return {"code": 404, "msg": "暂无资料", "data": None}

    return {"code": 200, "msg": "success", "data": profile.data}

@app.get("/api/onboarding/status", summary="获取首次背调完成状态")
def get_onboarding_status(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    profile_data = profile.data if profile else None
    missing_fields = missing_profile_fields(profile_data)

    return {
        "code": 200,
        "msg": "success",
        "data": {
            "completed": len(missing_fields) == 0,
            "missing_fields": missing_fields,
            "requires_onboarding": len(missing_fields) > 0,
        }
    }

@app.get("/api/planning/analysis", summary="获取当前用户智能画像分析")
def get_planning_analysis(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    profile_data = profile.data if profile else None

    return {
        "code": 200,
        "msg": "success",
        "data": build_student_strategy(profile_data)
    }

@app.post("/api/ai-chat", summary="升学规划AI对话")
def ai_chat(
    data: AIChatRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    message = data.message.strip()
    if not is_admission_related(message):
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "source": "local_reject",
                "answer": (
                    "我只能协助 AP 课程、升学规划、申请准备、GPA、标化、活动背景、"
                    "目标专业和院校匹配相关问题。请把问题调整到升学规划范围内。"
                )
            }
        }

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    profile_data = profile.data if profile else {}
    updated_profile_data, detected_updates = apply_profile_updates_from_message(message, profile_data)

    if detected_updates:
        if profile:
            profile.data = updated_profile_data
        else:
            profile = Profile(user_id=user_id, data=updated_profile_data)
            db.add(profile)
        db.flush()
        profile_data = updated_profile_data

    strategy = build_student_strategy(profile_data)
    profile_summary = (
        f"{build_profile_summary(profile_data)}\n\n"
        f"系统画像分析：\n{format_strategy_for_prompt(strategy)}"
    )

    try:
        answer = call_deepseek_ai(message, profile_summary)
        source = "deepseek"
    except Exception as e:
        answer = local_planning_answer(message, profile_data)
        source = "local_fallback"
        print(f"DeepSeek调用失败，已使用本地fallback: {e}")

    if detected_updates:
        answer = (
            f"我已把这次信息纳入Profile库：{'; '.join(detected_updates)}。\n"
            "下面是基于更新后画像的判断：\n\n"
            f"{answer}"
        )

    history = AIPlanHistory(
        user_id=user_id,
        question=message,
        answer=answer,
        source=source
    )
    db.add(history)
    db.commit()

    return {
        "code": 200,
        "msg": "success",
        "data": {
            "id": history.id,
            "source": source,
            "answer": answer,
            "detected_updates": detected_updates,
            "analysis": strategy
        }
    }

@app.get("/api/ai-plans", summary="获取AI规划历史")
def get_ai_plans(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    histories = (
        db.query(AIPlanHistory)
        .filter(AIPlanHistory.user_id == user_id)
        .order_by(AIPlanHistory.created_at.desc())
        .all()
    )

    data = [
        {
            "id": item.id,
            "question": item.question,
            "answer": item.answer,
            "source": item.source,
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        for item in histories
    ]
    return {"code": 200, "msg": "success", "data": data}

@app.delete("/api/ai-plans/{plan_id}", summary="删除AI规划历史")
def delete_ai_plan(
    plan_id: int,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    user_id, error_response = get_user_id_from_authorization(authorization)
    if error_response:
        return error_response

    history = (
        db.query(AIPlanHistory)
        .filter(AIPlanHistory.id == plan_id, AIPlanHistory.user_id == user_id)
        .first()
    )
    if not history:
        return {"code": 404, "msg": "规划记录不存在", "data": None}

    db.delete(history)
    db.commit()
    return {"code": 200, "msg": "删除成功"}

@app.get("/health", summary="服务健康检查")
def health_check():
    """健康检查接口"""
    return JSONResponse(
        content={
            "status": "ok",
            "message": "AP升学规划后端服务运行正常",
            "version": "1.0.0"
        },
        media_type="application/json; charset=utf-8"
    )

# ===================== 注册接口实现 =====================
@app.post("/api/register", summary="用户注册")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    try:
        # 1. 校验用户名是否已存在
        existing_user = db.query(User).filter(User.username == data.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")
        
        # 2. 创建用户主记录（密码加密）
        new_user = User(
            username=data.username,
            password=get_password_hash(data.password),  # 密码加密存储
            email=data.email,
            name=data.name,
            role="student",
            current_grade_term=GradeTermEnum(data.current_grade_term)  # 转换为枚举类型
        )
        db.add(new_user)
        db.flush()  # 预提交获取ID，避免commit后refresh
        
        # 3. 插入GPA数据（枚举转换）
        for gpa_item in data.gpa_list:
            new_gpa = GPA(
                user_id=new_user.id,
                grade_term=GradeTermEnum(gpa_item.grade_term),
                weighted_gpa=gpa_item.weighted_gpa,
                unweighted_gpa=gpa_item.unweighted_gpa
            )
            db.add(new_gpa)
        
        # 4. 插入AP课程成绩
        for ap_item in data.ap_plans:
            new_ap = APPlan(
                user_id=new_user.id,
                course=ap_item.course,
                score=ap_item.score
            )
            db.add(new_ap)
        
        # 5. 插入标化成绩（枚举转换）
        for std_item in data.standard_tests:
            new_std = StandardTest(
                user_id=new_user.id,
                test_type=StandardTestTypeEnum(std_item.test_type),
                score=std_item.score
            )
            db.add(new_std)
        
        # 6. 插入SAT/ACT成绩（可选，枚举转换）
        if data.sat_act:
            new_sat_act = SatAct(
                user_id=new_user.id,
                test_type=SatActTypeEnum(data.sat_act.test_type),
                score=data.sat_act.score
            )
            db.add(new_sat_act)
        
        # 7. 插入背景提升项目（可选）
        if data.background_projects:
            for bg_item in data.background_projects:
                new_bg = BackgroundProject(
                    user_id=new_user.id,
                    project_type=bg_item.project_type,
                    project_name=bg_item.project_name,
                    description=bg_item.description
                )
                db.add(new_bg)
        
        # 8. 提交所有数据
        db.commit()
        
        # 9. 返回注册成功响应
        return {
            "code": 200,
            "msg": "注册成功",
            "user_id": new_user.id
        }
    
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"注册失败：{str(e)}")

# 挂载前端静态文件（最后定义，避免覆盖接口）
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
