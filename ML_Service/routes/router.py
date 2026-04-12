from fastapi import APIRouter

from routes.summarise import router as summarise_router
from routes.classify import router as classify_router
from routes.route import router as route_router
from routes.llm import router as llm_router
from routes.cache import router as cache_router 
from routes.embed import router as embed_router

# Aggregate all route modules here so main.py has a single import point.
api_router = APIRouter()
api_router.include_router(summarise_router)
api_router.include_router(classify_router)
api_router.include_router(route_router)
api_router.include_router(llm_router)   # ← LLM dispatcher (tier → model)
api_router.include_router(cache_router)  
api_router.include_router(embed_router)  