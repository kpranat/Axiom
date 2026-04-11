from fastapi import APIRouter

from routes.summarise import router as summarise_router
from routes.classify import router as classify_router

# Aggregate all route modules here so main.py has a single import point.
api_router = APIRouter()
api_router.include_router(summarise_router)
api_router.include_router(classify_router)
