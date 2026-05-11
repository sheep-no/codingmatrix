/**
 * static/js/todo_list.js
 * 
 * Description: 前端 Todo 列表交互逻辑
 * Author: Senior Frontend Engineering Team
 * Tech Stack: Vanilla ES6 Module (Compatible with Vue/React/React-Odomino context)
 * 
 * Features:
 * - API Client abstraction
 * - State Management (Local Todo Store)
 * - CRUD Operations
 * - Filtering & Sorting Logic
 */

/* =========================================
   1. Configuration & Constants
   ========================================= */
const APP_CONFIG = {
  BASE_API_URL: '/api',  // Assumes FastAPI root path
  TOKEN_HEADER: 'Authorization',
  TOKEN_KEY: 'auth_token' // Used for localStorage persistence
};

// Logic for filtering & sorting
const PriorityOrder = {
  high: 3,
  medium: 2,
  low: 1
};

/* =========================================
   2. API Client Services
   ========================================= */

/**
 * Constructs HTTP Headers including Token
 * @returns {Object} Headers object
 */
function getHeaders() {
  const token = localStorage.getItem(APP_CONFIG.TOKEN_KEY);
  const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
  if (token) {
    headers[APP_CONFIG.TOKEN_HEADER] = `Bearer ${token}`; // JWT Bearer standard
  }
  return headers;
}

/**
 * Wrapper for Fetch API with Error Handling
 */
async function apiRequest(endPoint, method = 'GET', body = null) {
  const url = `${APP_CONFIG.BASE_API_URL}${endPoint}`;
  const options = {
    method,
    headers: getHeaders()
  };

  // Add request body
  if (body && method !== 'GET') {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);
    
    // Standardize response format (FastAPI default behavior)
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      // Handle specific status codes
      if (response.status === 401) {
         // Handle Token Expiry
         localStorage.removeItem(APP_CONFIG.TOKEN_KEY);
         window.location.href = '/login'; 
         throw new Error(errorData.detail || 'Session expired');
      }
      throw new Error(errorData.detail || `HTTP Error: ${response.status}`);
    }

    return response.json();
  } catch (error) {
    console.error('API Error:', error);
    Promise.reject(error);
  }
}

/**
 * Core CRUD Operations
 */
async function fetchTodos(params = {}) {
  return await apiRequest('/todos', 'GET', params);
}

async function createTodo(data) {
  return await apiRequest('/todos', 'POST', data);
}

async function updateTodo(id, data) {
  // Note: Using PUT vs PATCH depends on backend logic. Here using PUT for full intent update
  const response = await apiRequest(`/todos/${id}`, 'PUT', data);
  
  // Check if FastAPI returns 200 OK or 201 CREATED for edit logic
  if (response.status === 201) {
      window.alert('Todo updated successfully');
  }
  return response;
}

async function deleteTodo(id) {
  await apiRequest(`/todos/${id}`, 'DELETE');
}

async function toggleTodoStatus(todoId) {
   // Assuming backend accepts partial update for { "completed": !status }
   // Or frontend sending current state. Sending complete state directly is safer for partial updates.
  const todo = state.todos.find(t => t.id === todoId);
  const updateBody = { 
    ...todo, 
    completed: !todo.completed 
  };
  return await apiRequest(`/todos/${todoId}`, 'PUT', updateBody);
}

/* =========================================
   3. Data Management State
   ========================================= */

// Store for local application state
const store = {
  todos: [],
  isLoading: false,
  filterStatus: 'all', // all, active, completed
  priorityOrder: 'any', // any, low, medium, high
  
  // Setters/Getters that persist or sync
  setTodos: (data) => {
    store.todos = Array.isArray(data) ? data : [];
  },

  isLoading: false,
  setLoading: (bool) => { store.isLoading = bool; }
};

/* =========================================
   4. UI Logic & Event Handlers
   ========================================= */

function renderTodos(list) {
  // Verification: ensure data is ready before proceeding
  if (!Array.isArray(list)) return;

  // Filter Logic
  const filtered = list.filter(todo => {
    if (store.filterStatus === 'active') return !todo.completed;
    if (store.filterStatus === 'completed') return todo.completed;
    return true;
  });

  // Sort Logic
  filtered.sort((a, b) => {
    // Pending first by default
    if (a.completed !== b.completed) return a.completed ? 1 : -1;
    
    // Then sort by priority
    const prior1 = PriorityOrder[a.priority] || 0;
    const prior2 = PriorityOrder[b.priority] || 0;
    return prior2 - prior1;
  });

  // Simulate React/Vue DOM content update
  // replace this with render() function logic based on Vue use or Mount
  const container = document.getElementById('todoAppContainer');
  if (container) {
    // Parsing to string to inject template or DOM elements
    // Note: Implement a rendering template below or provided data in component
    container.innerHTML = filtered.map(item => createTodoRowElement(item)).join('');
  }
}

// Simple "element factory" for React/Vue Injection
function createTodoRowElement(todoData) {
  const priorityClasses = {
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-green-100 text-green-800'
  };
  const priorityLabel = todoData.priority || 'low';

  return `
    <div class="todo-item ${todoData.completed ? 'todos-completed' : ''}" data-id="${todoData.id}">
      <input type="checkbox" ${todoData.completed ? 'checked' : ''} />
      <div class="todo-content ${todoData.completed ? 'todos-completed' : ''}">
        <div class="checkbox-block">
          <span class="title">${todoData.title}</span>
          <span class="desc"> ${todoData.description || ''}</span>
          <span class="date办结">${todoData.deadline}</span>
        </div>
        <div class="meta-info">Priority: ${priorityLabel}</div>
        <div class="controls">
           <button class="btn-delete" data-id="${todoData.id}">X</button>
        </div>
      </div>
    </div>
  `;
}

/* =========================================
   5. Main Controller Initialization
   ========================================= */

async function initApp() {
  // Attach Current User State (JWT Token)
  const token = localStorage.getItem(APP_CONFIG.TOKEN_KEY);
  
  return fetchTodos().then(data => {
    store.setTodos(data.admin); // FastAPI usage assumed: admin/todos list
    renderTodos(data);
    console.log('App Initialized. Todo Count:', data.length);
  }).catch(err => {
    console.error('Failed to connect to Todo List API:', err);
    alert('Error loading Todos. Please try again later.');
  });
}

// Attach DOM Event Listeners
function attachEventListeners() {
  // 🔴 TODO IMPLEMENT VIEW SPECIFIC BINDINGS
  // 1. Checkbox Toggle
  document.addEventListener('DOMContentLoaded', () => {
    const checkboxes = document.querySelectorAll('.todo-checkbox');
    checkboxes.forEach(cb => {
      cb.addEventListener('click', (e) => {
        const todoId = e.target.closest('.todo-row').dataset.id;
        const todo = store.todos.find(t => t.id == todoId);
        if (todo) {
           toggleTodoStatus(todoId).then(data => {
               // Sync UI
               e.target.checked = data.completed;
               renderTodos(store.todos); 
           });
        }
      });
    });

    // 2. Delete Actions
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('btn-delete')) {
        const todoId = e.target.dataset.id;
        deleteTodo(todoId).then(() => {
            removeTodoFromState(todoId);
            renderTodos(store.todos);
        })
      }
    }); // or use event delegation
  });
}

// cleanup helper
function removeTodoFromState(id) {
    store.todos = store.todos.filter(t => t.id != id);
    store.setTodos(store.todos);
}

/* =========================================
   6. Boot
   ========================================= */

// Auto-run only if DOM ready (Vanilla JS entry point)
window.addEventListener('DOMContentLoaded', () => {
  // Order: 1. Init State (assuming initial load), 2. Init UI
  fetchTodos().then(data => {
      store.setTodos(data);
      renderTodos(data);
  });
});