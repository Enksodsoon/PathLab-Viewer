from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy.orm import Session as OrmSession


def register_assessment_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
) -> None:
    @app.get("/api/v2/assessment/administrations/{public_id}")
    def administration_metadata(
        public_id: str,
        response: Response,
        _: Annotated[OrmSession, Depends(database_dependency)],
    ) -> dict[str, object]:
        del public_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
