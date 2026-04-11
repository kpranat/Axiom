from fastapi import APIRouter

from routes.summarise import router as summarise_router
from routes.cache import router as cache_router
from routes.embed import router as embed_router

# Aggregate all route modules here so main.py has a single import point.
api_router = APIRouter()
api_router.include_router(summarise_router)
api_router.include_router(cache_router)
api_router.include_router(embed_router)
