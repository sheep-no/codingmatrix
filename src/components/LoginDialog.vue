<script setup>
  import { ref, computed } from 'vue'
  import { useAuth } from '@/composables/useAuth'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close', 'success'])

  const { login } = useAuth()

  const loginForm = ref({ email: '', password: '' })
  const isLoggingIn = ref(false)
  const loginError = ref('')
  const emailFocused = ref(false)
  const passwordFocused = ref(false)
  const rememberMe = ref(false)

  const showLoginDialog = computed({
    get: () => props.visible,
    set: val => {
      if (!val) emit('close')
    }
  })

  function closeLoginModal() {
    loginError.value = ''
    loginForm.value.email = ''
    loginForm.value.password = ''
    emailFocused.value = false
    passwordFocused.value = false
    emit('close')
  }

  async function handleLogin() {
    if (!loginForm.value.email || !loginForm.value.password) {
      loginError.value = '请填写邮箱和密码'
      return
    }

    isLoggingIn.value = true
    loginError.value = ''

    const result = await login(loginForm.value.email, loginForm.value.password)
    isLoggingIn.value = false

    if (result.success) {
      emit('success')
      closeLoginModal()
    } else {
      loginError.value = result.error || '登录失败'
    }
  }
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="showLoginDialog" class="login-modal" @click.self="closeLoginModal">
        <div class="login-form">
          <div class="login-header">
            <div class="login-logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
            <h3>欢迎回来</h3>
            <p>登录到您的账户</p>
          </div>

          <div class="login-body">
            <div class="input-group" :class="{ focused: emailFocused, filled: loginForm.email }">
              <div class="input-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path
                    d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"
                  />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
              </div>
              <input
                v-model="loginForm.email"
                type="email"
                placeholder=" "
                autocomplete="email"
                @focus="emailFocused = true"
                @blur="emailFocused = false"
              />
              <label>邮箱地址</label>
            </div>

            <div
              class="input-group"
              :class="{ focused: passwordFocused, filled: loginForm.password }"
            >
              <div class="input-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </div>
              <input
                v-model="loginForm.password"
                type="password"
                placeholder=" "
                autocomplete="current-password"
                @focus="passwordFocused = true"
                @blur="passwordFocused = false"
                @keyup.enter="handleLogin"
              />
              <label>密码</label>
            </div>

            <div class="login-options">
              <label class="remember-me">
                <input v-model="rememberMe" type="checkbox" />
                <span class="checkmark"></span>
                <span>记住我</span>
              </label>
              <a href="#" class="forgot-link">忘记密码?</a>
            </div>
          </div>

          <p v-if="loginError" class="error-message">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {{ loginError }}
          </p>

          <div class="login-footer">
            <button class="btn-cancel" @click="closeLoginModal">取消</button>
            <button class="btn-login" :disabled="isLoggingIn" @click="handleLogin">
              <span v-if="!isLoggingIn">登录</span>
              <span v-else class="loading">
                <svg class="spinner" viewBox="0 0 24 24">
                  <circle
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    stroke-width="3"
                    fill="none"
                    stroke-dasharray="31.4 31.4"
                  />
                </svg>
                登录中...
              </span>
            </button>
          </div>

          <div class="login-divider"><span>或</span></div>

          <div class="social-login">
            <button class="btn-social btn-github">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
                />
              </svg>
              GitHub
            </button>
            <button class="btn-social btn-google">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
              Google
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
  .login-modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(4px);
    overflow-y: auto;
  }

  .login-form {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    width: 90%;
    max-width: 400px;
    padding: 32px;
    box-shadow: 0 20px 60px var(--shadow-color);
    color: var(--text-primary);
    animation: modalSlideIn 0.3s ease-out;
  }

  @keyframes modalSlideIn {
    from {
      opacity: 0;
      transform: translateY(-20px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .login-header {
    text-align: center;
    margin-bottom: 24px;
  }

  .login-logo {
    width: 64px;
    height: 64px;
    background: linear-gradient(135deg, var(--color-primary-600), var(--color-primary-500));
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 16px;
  }

  .login-logo svg {
    width: 32px;
    height: 32px;
    color: white;
  }

  .login-header h3 {
    margin: 0 0 4px;
    font-size: 20px;
    color: var(--text-primary);
  }

  .login-header p {
    margin: 0;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .input-group {
    position: relative;
    margin-bottom: 20px;
  }

  .input-group .input-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 20px;
    height: 20px;
    color: var(--text-tertiary);
    pointer-events: none;
    transition: color 0.2s;
  }

  .input-group.focused .input-icon {
    color: var(--color-primary-500);
  }

  .input-group input {
    width: 100%;
    height: 48px;
    padding: 0 12px 0 44px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    font-size: 14px;
    transition:
      border-color 0.2s,
      box-shadow 0.2s;
  }

  .input-group.focused input {
    border-color: var(--color-primary-500);
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb, 59, 130, 246), 0.2);
    outline: none;
  }

  .input-group label {
    position: absolute;
    left: 44px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-tertiary);
    font-size: 14px;
    pointer-events: none;
    transition: all 0.2s ease-out;
    background: transparent;
  }

  .input-group.focused label,
  .input-group.filled label {
    top: -8px;
    left: 12px;
    font-size: 12px;
    color: var(--color-primary-500);
    background: var(--bg-primary);
    padding: 0 4px;
  }

  .login-options {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .remember-me {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .forgot-link {
    font-size: 14px;
    color: var(--color-primary-500);
    text-decoration: none;
  }

  .forgot-link:hover {
    text-decoration: underline;
  }

  .error-message {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--color-danger-500);
    font-size: 13px;
    margin: 12px 0;
  }

  .error-message svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .login-footer {
    display: flex;
    gap: 12px;
    margin-top: 20px;
  }

  .login-footer button {
    flex: 1;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition:
      background 0.2s,
      transform 0.1s;
  }

  .btn-cancel {
    background: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .btn-cancel:hover {
    background: var(--bg-tertiary);
  }

  .btn-login {
    background: linear-gradient(135deg, var(--color-primary-600), var(--color-primary-500));
    color: white;
  }

  .btn-login:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(var(--color-primary-rgb, 59, 130, 246), 0.3);
  }

  .btn-login:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .login-footer .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .spinner {
    width: 16px;
    height: 16px;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .login-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 24px 0;
    color: var(--text-tertiary);
    font-size: 14px;
  }

  .login-divider::before,
  .login-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-color);
  }

  .social-login {
    display: flex;
    gap: 12px;
  }

  .btn-social {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 14px;
    cursor: pointer;
    transition: background 0.2s;
  }

  .btn-social:hover {
    background: var(--bg-tertiary);
  }

  .btn-social svg {
    width: 20px;
    height: 20px;
  }

  .modal-fade-enter-active,
  .modal-fade-leave-active {
    transition: opacity 0.2s ease;
  }

  .modal-fade-enter-from,
  .modal-fade-leave-to {
    opacity: 0;
  }
</style>
