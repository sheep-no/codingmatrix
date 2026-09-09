"""Structured, deterministic generation for supported project contracts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from textwrap import dedent
from typing import Any, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CrudField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["string", "integer", "number", "boolean"]
    required: bool = True
    nullable: bool = False
    default: str | int | float | bool | None = None


class FastApiCrudIR(BaseModel):
    """Framework-independent CRUD facts consumed by the FastAPI renderer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["fastapi_sqlite_crud"] = "fastapi_sqlite_crud"
    entity_name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    resource_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    route_path: str = Field(pattern=r"^/[a-zA-Z0-9_/{}/-]+$")
    database_file: str = Field(default="todos.db", pattern=r"^[a-zA-Z0-9_.-]+\.db$")
    fields: Tuple[CrudField, ...] = ()

    @model_validator(mode="after")
    def validate_fields(self) -> "FastApiCrudIR":
        names = [field.name for field in self.fields]
        if not names:
            raise ValueError("CRUD IR requires at least one field")
        if len(names) != len(set(names)):
            raise ValueError("CRUD IR field names must be unique")
        if "id" in names:
            raise ValueError("CRUD IR reserves id for the generated primary key")
        return self


class FastApiCrudLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry: str
    model: str
    database: str
    schema: str
    repository: str
    test: str

    @property
    def paths(self) -> Tuple[str, ...]:
        return (
            self.entry,
            self.model,
            self.database,
            self.schema,
            self.repository,
            self.test,
        )


_ROLE_STEMS = {
    "entry": {"main", "app_entry"},
    "model": {"models", "entities"},
    "database": {"database", "persistence"},
    "schema": {"schemas", "dto"},
    "repository": {"crud", "repository"},
}


class FastApiCrudRenderer:
    """Render one internally consistent six-file FastAPI CRUD project."""

    model_name = "deterministic-fastapi-crud-v1"

    def __init__(self, ir: FastApiCrudIR, layout: FastApiCrudLayout) -> None:
        self.ir = ir
        self.layout = layout

    def render(self, path: str) -> str:
        renderers = {
            self.layout.database: self._render_database,
            self.layout.model: self._render_model,
            self.layout.schema: self._render_schema,
            self.layout.repository: self._render_repository,
            self.layout.entry: self._render_entry,
            self.layout.test: self._render_test,
        }
        try:
            return renderers[path]()
        except KeyError as exc:
            raise ValueError(f"path is outside the FastAPI CRUD layout: {path}") from exc

    def _render_database(self) -> str:
        return dedent(
            f'''\
            from sqlalchemy import create_engine
            from sqlalchemy.orm import declarative_base, sessionmaker

            DATABASE_URL = "sqlite:///./{self.ir.database_file}"
            engine = create_engine(DATABASE_URL, connect_args={{"check_same_thread": False}})
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            Base = declarative_base()
            '''
        )

    def _render_model(self) -> str:
        database_module = _module_name(self.layout.database)
        imports = sorted({_sqlalchemy_type(field.type) for field in self.ir.fields})
        columns = ["    id = Column(Integer, primary_key=True, index=True)"]
        for field in self.ir.fields:
            arguments = [_sqlalchemy_type(field.type), f"nullable={field.nullable}"]
            if not field.required or field.default is not None:
                arguments.append(f"default={field.default!r}")
            columns.append(f"    {field.name} = Column({', '.join(arguments)})")
        return dedent(
            f'''\
            from sqlalchemy import Column, Integer, {", ".join(imports)}

            from {database_module} import Base


            class {self.ir.entity_name}(Base):
                __tablename__ = "{self.ir.resource_name}"

            {chr(10).join(columns)}
            '''
        ).replace("\n            id =", "\n    id =").replace("\n            ", "\n")

    def _render_schema(self) -> str:
        create_fields = "\n".join(
            f"    {field.name}: {_python_annotation(field)}{_schema_default(field)}"
            for field in self.ir.fields
        )
        update_fields = "\n".join(
            f"    {field.name}: {_python_type(field.type)} | None = None"
            for field in self.ir.fields
        )
        response_fields = "\n".join(
            f"    {field.name}: {_python_type(field.type)}{' | None' if field.nullable else ''}"
            for field in self.ir.fields
        )
        return dedent(
            f'''\
            from pydantic import BaseModel, ConfigDict


            class {self.ir.entity_name}Create(BaseModel):
            {create_fields}


            class {self.ir.entity_name}Update(BaseModel):
            {update_fields}


            class {self.ir.entity_name}Response(BaseModel):
                model_config = ConfigDict(from_attributes=True)

                id: int
            {response_fields}
            '''
        ).replace("\n            ", "\n")

    def _render_repository(self) -> str:
        database_module = _module_name(self.layout.database)
        model_module = _module_name(self.layout.model)
        schema_module = _module_name(self.layout.schema)
        entity = self.ir.entity_name
        variable = _snake_case(entity)
        return dedent(
            f'''\
            from collections.abc import Generator

            from sqlalchemy.orm import Session

            from {database_module} import SessionLocal
            from {model_module} import {entity}
            from {schema_module} import {entity}Create, {entity}Update


            def get_db() -> Generator[Session, None, None]:
                database = SessionLocal()
                try:
                    yield database
                finally:
                    database.close()


            def create_{variable}(database: Session, payload: {entity}Create) -> {entity}:
                {variable} = {entity}(**payload.model_dump())
                database.add({variable})
                database.commit()
                database.refresh({variable})
                return {variable}


            def list_{self.ir.resource_name}(database: Session) -> list[{entity}]:
                return database.query({entity}).order_by({entity}.id).all()


            def get_{variable}(database: Session, {variable}_id: int) -> {entity} | None:
                return database.get({entity}, {variable}_id)


            def update_{variable}(database: Session, {variable}: {entity}, payload: {entity}Update) -> {entity}:
                for field, value in payload.model_dump(exclude_unset=True).items():
                    setattr({variable}, field, value)
                database.commit()
                database.refresh({variable})
                return {variable}


            def delete_{variable}(database: Session, {variable}: {entity}) -> None:
                database.delete({variable})
                database.commit()
            '''
        )

    def _render_entry(self) -> str:
        database_module = _module_name(self.layout.database)
        repository_module = _module_name(self.layout.repository)
        schema_module = _module_name(self.layout.schema)
        entity = self.ir.entity_name
        variable = _snake_case(entity)
        route = self.ir.route_path.rstrip("/")
        return dedent(
            f'''\
            from fastapi import Depends, FastAPI, HTTPException, Response, status
            from sqlalchemy.orm import Session

            import {repository_module} as repository
            from {database_module} import Base, engine
            from {schema_module} import {entity}Create, {entity}Response, {entity}Update

            Base.metadata.create_all(bind=engine)
            app = FastAPI(title="{entity} API")


            @app.get("/health")
            def health() -> dict[str, str]:
                return {{"status": "healthy"}}


            @app.post("{route}", response_model={entity}Response, status_code=status.HTTP_201_CREATED)
            def create_{variable}(payload: {entity}Create, database: Session = Depends(repository.get_db)):
                return repository.create_{variable}(database, payload)


            @app.get("{route}", response_model=list[{entity}Response])
            def list_{self.ir.resource_name}(database: Session = Depends(repository.get_db)):
                return repository.list_{self.ir.resource_name}(database)


            @app.get("{route}/{{{variable}_id}}", response_model={entity}Response)
            def get_{variable}({variable}_id: int, database: Session = Depends(repository.get_db)):
                {variable} = repository.get_{variable}(database, {variable}_id)
                if {variable} is None:
                    raise HTTPException(status_code=404, detail="{entity} not found")
                return {variable}


            @app.put("{route}/{{{variable}_id}}", response_model={entity}Response)
            def update_{variable}({variable}_id: int, payload: {entity}Update, database: Session = Depends(repository.get_db)):
                {variable} = repository.get_{variable}(database, {variable}_id)
                if {variable} is None:
                    raise HTTPException(status_code=404, detail="{entity} not found")
                return repository.update_{variable}(database, {variable}, payload)


            @app.delete("{route}/{{{variable}_id}}", status_code=status.HTTP_204_NO_CONTENT)
            def delete_{variable}({variable}_id: int, database: Session = Depends(repository.get_db)):
                {variable} = repository.get_{variable}(database, {variable}_id)
                if {variable} is None:
                    raise HTTPException(status_code=404, detail="{entity} not found")
                repository.delete_{variable}(database, {variable})
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            '''
        )

    def _render_test(self) -> str:
        database_module = _module_name(self.layout.database)
        entry_module = _module_name(self.layout.entry)
        repository_module = _module_name(self.layout.repository)
        route = self.ir.route_path.rstrip("/")
        payload = _example_payload(self.ir.fields)
        update = _updated_payload(self.ir.fields)
        return dedent(
            f'''\
            import pytest
            from fastapi.testclient import TestClient
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from {database_module} import Base
            from {entry_module} import app
            from {repository_module} import get_db


            @pytest.fixture
            def client(tmp_path):
                engine = create_engine(
                    f"sqlite:///{{tmp_path / 'test.db'}}",
                    connect_args={{"check_same_thread": False}},
                )
                testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                Base.metadata.create_all(bind=engine)

                def override_get_db():
                    database = testing_session()
                    try:
                        yield database
                    finally:
                        database.close()

                app.dependency_overrides[get_db] = override_get_db
                with TestClient(app) as test_client:
                    yield test_client
                app.dependency_overrides.clear()
                Base.metadata.drop_all(bind=engine)
                engine.dispose()


            def test_crud_lifecycle(client):
                created = client.post("{route}", json={payload!r})
                assert created.status_code == 201
                item_id = created.json()["id"]

                assert client.get("{route}").status_code == 200
                assert client.get(f"{route}/{{item_id}}").status_code == 200

                updated = client.put(f"{route}/{{item_id}}", json={update!r})
                assert updated.status_code == 200

                assert client.delete(f"{route}/{{item_id}}").status_code == 204
                assert client.get(f"{route}/{{item_id}}").status_code == 404
            '''
        )


def select_fastapi_crud_renderer(
    requirement: str,
    file_entries: Mapping[str, Mapping[str, Any]],
    supplied_ir: object = None,
) -> Optional[FastApiCrudRenderer]:
    """Select deterministic generation only for a complete supported contract."""
    layout = _resolve_layout(tuple(file_entries))
    if layout is None:
        return None

    ir: Optional[FastApiCrudIR]
    if isinstance(supplied_ir, Mapping):
        if supplied_ir.get("kind") != "fastapi_sqlite_crud":
            return None
        ir = FastApiCrudIR.model_validate(supplied_ir)
    else:
        ir = _infer_todo_ir(requirement)
    if ir is None:
        return None
    return FastApiCrudRenderer(ir, layout)


def _resolve_layout(paths: Tuple[str, ...]) -> Optional[FastApiCrudLayout]:
    if len(paths) != 6 or any(not path.endswith(".py") for path in paths):
        return None
    resolved: dict[str, str] = {}
    for path in paths:
        stem = PurePosixPath(path).stem.lower()
        if stem.startswith("test_") or stem.endswith("_test"):
            role = "test"
        else:
            role = next((name for name, stems in _ROLE_STEMS.items() if stem in stems), "")
        if not role or role in resolved:
            return None
        resolved[role] = path
    if set(resolved) != {"entry", "model", "database", "schema", "repository", "test"}:
        return None
    return FastApiCrudLayout.model_validate(resolved)


def _infer_todo_ir(requirement: str) -> Optional[FastApiCrudIR]:
    lowered = requirement.lower()
    crud_markers = "crud" in lowered or all(term in requirement for term in ("创建", "查询", "更新", "删除"))
    if "fastapi" not in lowered or "sqlite" not in lowered or not crud_markers:
        return None
    route_match = re.search(r"/api(?:/[a-zA-Z0-9_-]+)*/todos\b", lowered)
    if route_match is None:
        return None
    return FastApiCrudIR(
        entity_name="Todo",
        resource_name="todos",
        route_path=route_match.group(0),
        fields=(
            CrudField(name="title", type="string"),
            CrudField(name="description", type="string", required=False, nullable=True),
            CrudField(name="completed", type="boolean", required=False, default=False),
        ),
    )


def _module_name(path: str) -> str:
    return PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _python_type(field_type: str) -> str:
    return {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}[field_type]


def _sqlalchemy_type(field_type: str) -> str:
    return {"string": "String", "integer": "Integer", "number": "Float", "boolean": "Boolean"}[field_type]


def _python_annotation(field: CrudField) -> str:
    annotation = _python_type(field.type)
    return f"{annotation} | None" if field.nullable else annotation


def _schema_default(field: CrudField) -> str:
    if field.required and field.default is None and not field.nullable:
        return ""
    return f" = {field.default!r}"


def _example_payload(fields: Tuple[CrudField, ...]) -> dict[str, object]:
    values = {"string": "generated", "integer": 1, "number": 1.5, "boolean": False}
    return {field.name: field.default if field.default is not None else values[field.type] for field in fields}


def _updated_payload(fields: Tuple[CrudField, ...]) -> dict[str, object]:
    first = fields[0]
    values = {"string": "updated", "integer": 2, "number": 2.5, "boolean": True}
    return {first.name: values[first.type]}
