from fastapi import APIRouter

from routes.summarise import router as summarise_router

# Aggregate all route modules here so main.py has a single import point.
api_router = APIRouter()
api_router.include_router(summarise_router)
