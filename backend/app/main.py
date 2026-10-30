"""FastAPI 应用入口。启动：uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ensure_dirs
from .db import init_db
from .routers import (
    disease,
    feedback,
    gis,
    graph,
    health,
    recognize,
    search,
    stats,
    user,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    init_db()
    yield


app = FastAPI(
    title="豆卫兵 API",
    version="0.1.0",
    description=(
        "基于多模态数据融合、动态知识图谱与 GAN 增强的"
        "绿豆病害智能分级与精准防治系统"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    health.router,
    user.router,
    disease.router,
    search.router,
    recognize.router,
    feedback.router,
    graph.router,
    gis.router,
    stats.router,
):
    app.include_router(router)
