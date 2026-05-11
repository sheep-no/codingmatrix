<template>
  <div id="app">
    <h1>📝 待办事项</h1>
    <div class="input-group">
      <input
        v-model="newTask"
        type="text"
        placeholder="输入新任务... (按Enter添加)"
      />
      <button @click="addTask">添加</button>
    </div>
    
    <ul v-if="tasks.length">
      <li v-for="task in tasks" :key="task.id" class="task-item">
        <span :class="{ 'completed': task.completed }">
          {{ task.completed ? '✅' : '📌' }}
        </span>
        <span class="task-text">{{ task.text }}</span>
        <div class="task-actions">
          <button
            :disabled="!task.completed"
            @click="toggleTask(task.id)"
          >
            {{ task.completed ? '完成' : '取消' }}
          </button>
          <button
            :disabled="task.completed"
            @click="deleteTask(task.id)"
          >
            删除
          </button>
        </div>
      </li>
    </ul>
    
    <div v-else-if="!tasks.length" class="empty-state">
      <p>暂无任务，添加第一个吧！</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TodoApp',
  data() {
    return {
      tasks: [],
      newTask: ''
    }
  },
  mounted() {
    this.loadTasks()
  },
  methods: {
    loadTasks() {
      this.tasks = JSON.parse(localStorage.getItem('tasks')) || []
    },
    addTask() {
      if (!this.newTask.trim()) return
      const task = {
        id: Date.now(),
        text: this.newTask.trim(),
        completed: false
      }
      this.tasks.push(task)
      this.saveTasks()
      this.newTask = ''
    },
    toggleTask(id) {
      const index = this.tasks.findIndex(t => t.id === id)
      if (index !== -1) {
        this.tasks[index].completed = !this.tasks[index].completed
        this.saveTasks()
      }
    },
    deleteTask(id) {
      this.tasks = this.tasks.filter(t => t.id !== id)
      this.saveTasks()
    },
    saveTasks() {
      localStorage.setItem('tasks', JSON.stringify(this.tasks))
    }
  },
  computed: {
    // 确保每次任务变化后正确重新加载（已由mounted处理）
  }
}
</script>

<style scoped>
#app {
  font-family: 'Arial', sans-serif;
  max-width: 600px;
  margin: 2rem auto;
  padding: 2rem;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

h1 {
  text-align: center;
  margin-bottom: 2rem;
  color: #333;
}

.input-group {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

input {
  flex: 1;
  padding: 0.5rem 1rem;
  border: 2px solid #ddd;
  border-radius: 4px;
  font-size: 1rem;
}

button {
  padding: 0.5rem 1.5rem;
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.3s;
}

button:hover {
  background: #45a049;
}

ul {
  list-style: none;
  padding: 0;
}

.task-item {
  background: white;
  border-radius: 6px;
  padding: 1rem;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.task-item.completed .task-text {
  text-decoration: line-through;
  opacity: 0.7;
}

.task-text {
  flex: 1;
  margin-left: 0.5rem;
}

.task-actions {
  display: flex;
  gap: 0.5rem;
}

.task-actions button {
  padding: 0.5rem 1rem;
}

.empty-state {
  text-align: center;
  color: #777;
  margin-top: 2rem;
}
</style>
