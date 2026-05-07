# 统一导入所有需要的模块（遵循PEP8，集中在顶部）
from sqlalchemy import create_engine, Column, String, Integer, Float, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import enum
from fastapi import FastAPI, Body, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
import os
from typing import List, Optional, Union
import re
4
# 配置项（生产环境建议用.env文件）
SQLALCHEMY_DATABASE_URL = "sqlite:///./ap_project.db"
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-202405")  # 环境变量优先
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*").split(",")  # 生产环境配置具体域名

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
    name: str = Field(..., description="真实姓名")
    current_grade_term: str = Field(..., pattern="^(9|10|11|12)年级(上|下)$", description="当前就读年级+学期")
    
    # GPA列表（根据当前年级自动校验必填项）
    gpa_list: List[GPARequest] = Field(..., description="各学期GPA列表")
    
    # AP课程成绩（必填）
    ap_plans: List[APPlanRequest] = Field(..., description="AP课程+成绩")
    
    # 标化成绩（可选，至少填一个）
    standard_tests: List[StandardTestRequest] = Field(..., min_items=1, description="标化成绩（至少一项）")
    
    # SAT/ACT（二选一，必填一项）
    sat_act: SatActRequest = Field(..., description="SAT/ACT成绩")
    
    # 背景提升（预留，可选）
    background_projects: Optional[List[BackgroundProjectRequest]] = Field(None, description="背景提升项目")

    # 校验GPA列表：根据当前年级校验必填学期
    @validator("gpa_list")
    def check_gpa_terms(cls, v, values):
        current_term = values.get("current_grade_term")
        if not current_term:
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

# 密码加密工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """加密密码(处理bcrypt 72字节限制)"""
    # 截断密码到72字节（bcrypt最大支持长度）
    password_truncated = password[:72]
    return pwd_context.hash(password_truncated)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)

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
            "name": user.name,
            "role": user.role,
            "current_grade_term": user.current_grade_term.value
        }
    }

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
        
        # 6. 插入SAT/ACT成绩（枚举转换）
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
# app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

