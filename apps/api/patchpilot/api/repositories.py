import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from patchpilot.db.session import get_db
from patchpilot.models import Repository
from patchpilot.schemas.domain import RepositoryCreate, RepositoryRead, RepositoryUpdate

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(db: Session = Depends(get_db)) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.full_name)).all())


@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(data: RepositoryCreate, db: Session = Depends(get_db)) -> Repository:
    existing = db.scalar(select(Repository).where(Repository.full_name == data.full_name))
    if existing:
        raise HTTPException(409, "Repository is already configured")
    owner, name = data.full_name.split("/", 1)
    repository = Repository(
        owner=owner,
        name=name,
        full_name=data.full_name,
        github_url=str(data.github_url or f"https://github.com/{data.full_name}"),
        default_branch=data.default_branch,
        test_command=data.test_command,
        lint_command=data.lint_command,
        protected_paths=data.protected_paths,
        coding_guidelines=data.coding_guidelines,
        autonomy_level=data.autonomy_level,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


def get_or_404(repository_id: uuid.UUID, db: Session) -> Repository:
    repository = db.get(Repository, repository_id)
    if not repository:
        raise HTTPException(404, "Repository not found")
    return repository


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(repository_id: uuid.UUID, db: Session = Depends(get_db)) -> Repository:
    return get_or_404(repository_id, db)


@router.patch("/{repository_id}", response_model=RepositoryRead)
def update_repository(
    repository_id: uuid.UUID, data: RepositoryUpdate, db: Session = Depends(get_db)
) -> Repository:
    repository = get_or_404(repository_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(repository, key, value)
    db.commit()
    db.refresh(repository)
    return repository

