from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Filesystem path where this package contents should be stored
    path: Mapped[str] = mapped_column(String, nullable=False)
    
    # Status: QUEUED, ACTIVE, PAUSED, COMPLETED, ERROR
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    
    # Recursive relationship for subpackages
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packages.id"), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    children: Mapped[List["Package"]] = relationship("Package", back_populates="parent", cascade="all, delete-orphan")
    parent: Mapped[Optional["Package"]] = relationship("Package", back_populates="children", remote_side=[id])
    
    files: Mapped[List["File"]] = relationship("File", back_populates="package", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Package(id={self.id}, name='{self.name}', status='{self.status}')>"

class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"))
    
    url: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    
    # Link to Aria2
    aria2_gid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    downloaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Metadata
    priority: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Relationship
    package: Mapped["Package"] = relationship("Package", back_populates="files")

    @property
    def progress(self) -> float:
        if self.size_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.size_bytes) * 100

    def __repr__(self):
        return f"<File(id={self.id}, filename='{self.filename}', status='{self.status}')>"
