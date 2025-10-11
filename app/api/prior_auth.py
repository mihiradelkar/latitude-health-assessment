from fastapi import APIRouter

router = APIRouter()

@router.post("/evaluate")
async def evaluate_prior_auth():
    """Evaluate prior authorization (to be implemented)"""
    return {"message": "Prior auth evaluation - coming soon"}