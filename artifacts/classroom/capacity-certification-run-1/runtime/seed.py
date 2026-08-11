import json
import os
from datetime import UTC, datetime

from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Slide, User
from wsi_viewer.publication import delivery_version
from wsi_viewer.security import hash_password

SLIDE_ID = "classroom-cert-slide"
PUBLIC_ID = "classroom-cert-real-dzi"
PASSWORD = os.environ["PATHLAB_CLASSROOM_SEED_PASSWORD"]

settings = Settings()
with session_factory(settings)() as database:
    user = database.query(User).filter(User.username == "admin").one_or_none()
    if user is None:
        database.add(User(username="admin", password_hash=hash_password(PASSWORD)))
    slide = database.get(Slide, SLIDE_ID)
    if slide is None:
        slide = Slide(
            id=SLIDE_ID,
            public_id=PUBLIC_ID,
            display_name="Local real-DZI certification fixture",
            original_filename="deidentified-certification-fixture.ome.tiff",
            source_bytes=0,
            derivative_bytes=25_585_664,
            derivative_file_count=500,
            render_mode="static_dzi",
            state=SlideState.PUBLISHED,
            slide_metadata={
                "width": 7557,
                "height": 7360,
                "dziTileSize": 512,
                "dziFormat": "jpg",
            },
            sha256="c" * 64,
            published_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
        database.add(slide)
    database.commit()
    database.refresh(slide)
    print(
        json.dumps(
            {
                "slideId": slide.id,
                "publicId": slide.public_id,
                "assetVersion": delivery_version(slide),
                "adminUsername": "admin",
                "adminPassword": PASSWORD,
            }
        )
    )
