from fastapi import APIRouter

from app.api.v1 import auth, documents, exports, insights, intelligence, organization, proposals, tasks, tenders

api_router = APIRouter(prefix="/api/v1")
for module in (auth, organization, tenders, documents, intelligence, proposals, tasks, insights, exports):
    api_router.include_router(module.router)
