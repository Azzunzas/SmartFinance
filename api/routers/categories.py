from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.categories import CategoryOut
from core.repository.categories import list_categories

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_all(session: Session = Depends(get_session)) -> list[CategoryOut]:
    """Catálogo somente leitura para filtros e classificação manual."""
    return [CategoryOut.model_validate(item) for item in list_categories(session)]
