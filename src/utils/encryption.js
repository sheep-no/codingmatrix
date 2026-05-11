/**
 * RSA + AES 混合加密工具
 *
 * 使用 Web Crypto API 实现 RSA-OAEP 和 AES-CBC 加密
 */

let rsaPublicKey = null
let publicKeyExpiry = null

export async function getRSAPublicKey() {
  if (rsaPublicKey && publicKeyExpiry && Date.now() < publicKeyExpiry) {
    return rsaPublicKey
  }

  try {
    const response = await fetch('/api/v1/public-key')
    if (!response.ok) {
      throw new Error('获取公钥失败')
    }

    const data = await response.json()
    rsaPublicKey = data.public_key
    publicKeyExpiry = Date.now() + 3600 * 1000

    console.log('RSA 公钥已获取')
    return rsaPublicKey
  } catch (error) {
    console.error('获取 RSA 公钥失败:', error)
    return null
  }
}

export function generateAESKey() {
  return crypto.getRandomValues(new Uint8Array(32))
}

export function generateIV() {
  return crypto.getRandomValues(new Uint8Array(16))
}

function base64Encode(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export async function aesEncrypt(data, key, iv) {
  const cryptoKey = await crypto.subtle.importKey('raw', key, { name: 'AES-CBC' }, false, [
    'encrypt'
  ])

  const plaintext = new TextEncoder().encode(JSON.stringify(data))
  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-CBC', iv: iv },
    cryptoKey,
    plaintext
  )

  const combined = new Uint8Array(iv.length + ciphertextBuffer.byteLength)
  combined.set(iv, 0)
  combined.set(new Uint8Array(ciphertextBuffer), iv.length)

  return base64Encode(combined.buffer)
}

export async function rsaEncryptKey(aesKey, publicKeyPem) {
  try {
    const publicKey = await importPublicKey(publicKeyPem)
    const encryptedBuffer = await crypto.subtle.encrypt(
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      publicKey,
      aesKey
    )
    return base64Encode(encryptedBuffer)
  } catch (error) {
    console.error('RSA 加密失败:', error)
    throw error
  }
}

async function importPublicKey(pem) {
  const pemContents = pem
    .replace('-----BEGIN PUBLIC KEY-----', '')
    .replace('-----END PUBLIC KEY-----', '')
    .replace(/\s/g, '')

  const binaryDer = atob(pemContents)
  const derArray = new Uint8Array(binaryDer.length)
  for (let i = 0; i < binaryDer.length; i++) {
    derArray[i] = binaryDer.charCodeAt(i)
  }

  return await crypto.subtle.importKey(
    'spki',
    derArray.buffer,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt']
  )
}

export async function encryptLoginData(loginData) {
  try {
    const publicKey = await getRSAPublicKey()
    if (!publicKey) {
      console.error('无法获取 RSA 公钥')
      return null
    }

    const aesKey = generateAESKey()
    const iv = generateIV()
    console.log('AES key generated, iv generated')

    const encryptedData = await aesEncrypt(loginData, aesKey, iv)
    console.log('AES encryption done, encryptedData length:', encryptedData.length)

    const encryptedKey = await rsaEncryptKey(aesKey, publicKey)
    console.log('RSA encryption done, encryptedKey length:', encryptedKey.length)

    return {
      encrypted_data: encryptedData,
      encrypted_key: encryptedKey
    }
  } catch (error) {
    console.error('加密失败:', error)
    console.error('Stack:', error.stack)
    return null
  }
}

export function isEncryptionAvailable() {
  return rsaPublicKey !== null
}

export function clearPublicKeyCache() {
  rsaPublicKey = null
  publicKeyExpiry = null
}
