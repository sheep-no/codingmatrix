from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import json
import os

app = FastAPI()

class Todo(BaseModel):
    title: str
    description: Optional[str] = None
    completed: bool = False
    priority: int = 1

class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    completed: bool = False
    priority: int = 1

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[Optional[str]] = None
    completed: Optional[bool] = None
    priority: Optional[int] = None

class TodoResponse(BaseModel):
    title: str
    description: Optional[str]
    completed: bool
    priority: int
    id: int

class TodoListResponse(BaseModel):
    todos: List[TodoResponse]
    total: int

def get_storage_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.json")

def load_todos() -> List[dict]:
    path = get_storage_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('todos', [])
    except (json.JSONDecodeError, IOError):
        return []

def save_todos(todos: List[dict]) -> None:
    path = get_storage_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'todos': todos}, f, ensure_ascii=False)

def generate_id(todos: List[dict]) -> int:
    if not todos:
        return 1
    return max(todo['id'] for todo in todos) + 1

@app.get("/api/v1/todos", response_model=TodoListResponse)
async def list_todos():
    todos = load_todos()
    return TodoListResponse(todos=todos, total=len(todos))

@app.post("/api/v1/todos", response_model=TodoResponse, status_code=201)
async def create_todo(todo: TodoCreate):
    todos = load_todos()
    new_todo = todo.model_dump()
    new_todo['id'] = generate_id(todos)
    todos.append(new_todo)
    save_todos(todos)
    return TodoResponse(**new_todo)

@app.get("/api/v1/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: int):
    todos = load_todos()
    for todo in todos:
        if todo['id'] == todo_id:
            return TodoResponse(**todo)
    raise HTTPException(status_code=404, detail="Todo not found")

@app.put("/api/v1/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(todo_id: int, todo: TodoUpdate):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo['id'] == todo_id:
            update_data = todo.model_dump(exclude_unset=True)
            todos[i].update(update_data)
            save_todos(todos)
            return TodoResponse(**todos[i])
    raise HTTPException(status_code=404, detail="Todo not found")

@app.delete("/api/v1/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: int):
    todos = load_todos()
    original_count = len(todos)
    todos = [todo for todo in todos if todo['id'] != todo_id]
    save_todos(todos)
    if len(todos) == original_count:
        raise HTTPException(status_code=404, detail="Todo not found")
    return None