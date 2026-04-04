from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 初始化FastAPI应用
app = FastAPI(
    title="AP升学规划后端API",
    description="AP_Project_Backend 项目接口文档",
    version="1.0.0"
)

# 跨域配置（前后端联调必须）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义JSON响应，强制UTF-8编码
@app.get("/health")
def health_check():
    return JSONResponse(
        content={
            "status": "ok",
            "message": "AP升学规划后端服务运行正常",
            "version": "1.0.0"
        },
        media_type="application/json; charset=utf-8"
    )