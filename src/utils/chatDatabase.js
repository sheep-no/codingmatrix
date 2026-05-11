/**
 * IndexedDB 工具模块
 * 用于持久化存储对话历史
 */

class ChatDatabase {
  constructor() {
    this.db = null
    this.DB_NAME = 'AIChatDB'
    this.DB_VERSION = 1
    this.STORE_NAME = 'conversations'
    this.initialized = false
  }

  /**
   * 初始化 IndexedDB
   */
  async init() {
    if (this.initialized && this.db) {
      return this.db
    }

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.DB_NAME, this.DB_VERSION)

      request.onerror = () => {
        console.error('[ERR] IndexedDB init failed:', request.error)
        reject(request.error)
      }

      request.onsuccess = () => {
        this.db = request.result
        this.initialized = true
        console.log('[OK] IndexedDB initialized')
        resolve(this.db)
      }

      request.onupgradeneeded = event => {
        const database = event.target.result

        if (!database.objectStoreNames.contains(this.STORE_NAME)) {
          const objectStore = database.createObjectStore(this.STORE_NAME, {
            keyPath: 'conversationId'
          })
          objectStore.createIndex('conversationId', 'conversationId', { unique: true })
          objectStore.createIndex('lastUpdated', 'lastUpdated', { unique: false })

          // 创建 TTL 索引用于自动清理
          objectStore.createIndex('expiresAt', 'expiresAt', { unique: false })

          console.log('[OK] IndexedDB store created')
        }
      }
    })
  }

  /**
   * 保存对话到 IndexedDB
   * @param {string|number} conversationId - 对话 ID
   * @param {Array} messages - 消息数组
   * @param {string|number} [selectedHistoryItem] - 选中的历史项
   */
  async saveConversation(conversationId, messages, selectedHistoryItem = null) {
    if (!conversationId || String(conversationId).startsWith('temp_')) {
      console.log('⏭️ 跳过临时对话保存:', conversationId)
      return
    }

    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(this.STORE_NAME)

      const data = {
        conversationId: String(conversationId),
        messages: JSON.parse(JSON.stringify(messages)), // 深拷贝
        selectedHistoryItem: selectedHistoryItem
          ? JSON.parse(JSON.stringify(selectedHistoryItem))
          : null,
        lastUpdated: Date.now(),
        expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000 // 30 天后过期
      }

      const request = objectStore.put(data)

      request.onsuccess = () => {
        console.log(
          '[SAVE] Saved chat to IndexedDB:',
          conversationId,
          'message count:',
          messages.length
        )
      }

      request.onerror = () => {
        console.error('[ERR] Save chat to IndexedDB failed:', request.error)
      }

      return new Promise((resolve, reject) => {
        transaction.oncomplete = () => resolve(true)
        transaction.onerror = () => reject(transaction.error)
      })
    } catch (error) {
      console.error('[ERR] Save chat to IndexedDB exception:', error)
      return false
    }
  }

  /**
   * 从 IndexedDB 加载对话
   * @param {string|number} conversationId - 对话 ID
   * @returns {Promise<{messages: Array, selectedHistoryItem: Object|null}|null>}
   */
  async loadConversation(conversationId) {
    if (!conversationId || String(conversationId).startsWith('temp_')) {
      return null
    }

    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readonly')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const request = objectStore.get(String(conversationId))

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          if (request.result) {
            console.log(
              '📂 从 IndexedDB 加载对话成功:',
              conversationId,
              '消息数:',
              request.result.messages.length
            )
            resolve({
              messages: request.result.messages,
              selectedHistoryItem: request.result.selectedHistoryItem
            })
          } else {
            console.log('📂 IndexedDB 中未找到对话:', conversationId)
            resolve(null)
          }
        }

        request.onerror = () => {
          reject(request.error)
        }
      })
    } catch (error) {
      console.error('[ERR] Load chat from IndexedDB exception:', error)
      return null
    }
  }

  /**
   * 清除 IndexedDB 中的对话
   * @param {string|number} conversationId - 对话 ID
   */
  async deleteConversation(conversationId) {
    if (!conversationId) return

    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const request = objectStore.delete(String(conversationId))

      request.onsuccess = () => {
        console.log('[DEL] Cleared chat from IndexedDB:', conversationId)
      }

      return new Promise((resolve, reject) => {
        transaction.oncomplete = () => resolve(true)
        transaction.onerror = () => reject(transaction.error)
      })
    } catch (error) {
      console.error('[ERR] Clear IndexedDB chat exception:', error)
      return false
    }
  }

  /**
   * 清除所有过期对话
   */
  async clearExpiredConversations() {
    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const index = objectStore.index('expiresAt')
      const now = Date.now()

      const request = index.openCursor()
      let deletedCount = 0

      request.onsuccess = event => {
        const cursor = event.target.result
        if (cursor) {
          if (cursor.value.expiresAt < now) {
            objectStore.delete(cursor.primaryKey)
            deletedCount++
            console.log('[DEL] Cleared expired chat:', cursor.value.conversationId)
          }
          cursor.continue()
        } else {
          console.log('[OK] Cleaned', deletedCount, 'expired chats')
        }
      }

      return new Promise(resolve => {
        transaction.oncomplete = () => resolve(deletedCount)
      })
    } catch (error) {
      console.error('[ERR] Clear expired chats exception:', error)
      return 0
    }
  }

  /**
   * 清除所有对话
   */
  async clearAll() {
    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const request = objectStore.clear()

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          console.log('[DEL] Cleared all chats')
          resolve(true)
        }
        request.onerror = () => reject(request.error)
      })
    } catch (error) {
      console.error('[ERR] Clear all chats exception:', error)
      return false
    }
  }

  /**
   * 获取所有对话列表
   * @returns {Promise<Array>}
   */
  async getAllConversations() {
    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readonly')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const request = objectStore.getAll()

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          resolve(request.result || [])
        }
        request.onerror = () => reject(request.error)
      })
    } catch (error) {
      console.error('[ERR] Get all chats exception:', error)
      return []
    }
  }

  /**
   * 获取对话数量
   * @returns {Promise<number>}
   */
  async getCount() {
    try {
      await this.init()

      const transaction = this.db.transaction([this.STORE_NAME], 'readonly')
      const objectStore = transaction.objectStore(this.STORE_NAME)
      const request = objectStore.count()

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          resolve(request.result || 0)
        }
        request.onerror = () => reject(request.error)
      })
    } catch (error) {
      console.error('[ERR] Get chat count exception:', error)
      return 0
    }
  }
}

// 导出单例
export const chatDB = new ChatDatabase()
