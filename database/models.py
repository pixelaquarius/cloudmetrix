import os
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
import enum

Base = declarative_base()

class AssetStatus(enum.Enum):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    DONE = "Done"
    FAILED = "Failed"
    FAILED_NETWORK = "Failed_Network"
    FAILED_AUTH = "Failed_Auth"
    PUBLISHED = "Published"
    SEEDED = "Seeded"

class VideoAsset(Base):
    __tablename__ = 'video_assets'

    id = Column(String(36), primary_key=True)  # uuid
    filename = Column(String(255), nullable=False)
    title = Column(String(500))
    caption = Column(String(2000))
    hashtags = Column(String(500))
    profile = Column(String(100))
    status = Column(Enum(AssetStatus), default=AssetStatus.PENDING)
    downloaded_at = Column(DateTime, default=datetime.utcnow)
    scheduled_time = Column(DateTime, nullable=True)
    thumbnail_path = Column(String(500))
    source_url = Column(String(1000))
    bypass_copyright = Column(String(10), default='0')
    
    # Growth & Marketing Fields
    affiliate_link = Column(String(1000), nullable=True)
    ab_test_group = Column(String(50), nullable=True)
    first_comment_pinned = Column(Boolean, default=False)
    
    # Additional AI fields can be added here
    caption_variations = Column(String, nullable=True) # JSON string to store A/B test variants

# Configuration for async engine
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'cloudmetrix.db')}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
