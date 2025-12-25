import asyncio
import pytest
from fetchr.database.models import Package, File
from fetchr.database.session import init_db, SessionLocal
from fetchr.manager.download_manager import DownloadManager
from pathlib import Path

# Mock Aria2DaemonManager to avoid needing actual process for structure test
from unittest.mock import MagicMock

def test_db_models_structure():
    # Use in-memory DB for testing
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from fetchr.database.models import Base
    
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Test Package creation
    root_pkg = Package(name="Root Package", path="/tmp/root", status="ACTIVE")
    session.add(root_pkg)
    session.commit()

    # Test Subpackage
    sub_pkg = Package(name="Sub Package", path="/tmp/root/sub", parent_id=root_pkg.id, status="ACTIVE")
    session.add(sub_pkg)
    session.commit()

    # Test File
    file = File(package_id=sub_pkg.id, url="http://example.com/file.zip", filename="file.zip")
    session.add(file)
    session.commit()

    # Verify relationships
    assert sub_pkg.parent == root_pkg
    assert root_pkg.children[0] == sub_pkg
    assert file.package == sub_pkg
    assert sub_pkg.files[0] == file

    print("✅ DB Models structure verified successfully!")

if __name__ == "__main__":
    test_db_models_structure()
