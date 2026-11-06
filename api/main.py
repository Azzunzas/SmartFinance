from fastapi import Depends, FastAPI

from api.deps import require_auth
from api.routers.accounts import router as accounts_router
from api.routers.auth import router as auth_router
from api.routers.bills import router as bills_router
from api.routers.categories import router as categories_router
from api.routers.connections import router as connections_router
from api.routers.investments import router as investments_router
from api.routers.metrics import router as metrics_router
from api.routers.planned_items import router as planned_items_router
from api.routers.recurrences import router as recurrences_router
from api.routers.sync import router as sync_router
from api.routers.transactions import router as transactions_router

app = FastAPI(title="SmartFinance API")
app.include_router(auth_router)
_protected = [Depends(require_auth)]
app.include_router(planned_items_router, dependencies=_protected)
app.include_router(recurrences_router, dependencies=_protected)
app.include_router(connections_router, dependencies=_protected)
app.include_router(investments_router, dependencies=_protected)
app.include_router(metrics_router, dependencies=_protected)
app.include_router(transactions_router, dependencies=_protected)
app.include_router(accounts_router, dependencies=_protected)
app.include_router(bills_router, dependencies=_protected)
app.include_router(categories_router, dependencies=_protected)
app.include_router(sync_router, dependencies=_protected)
