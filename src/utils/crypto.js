/**
 * RSA 加密工具
 * 
 * 使用 Web Crypto API 实现 RSA-OAEP 加密
 * 用于前端加密 API Key 后再传输到后端
 */

/**
 * 将 PEM 格式的公钥转换为 CryptoKey 对象
 * @param {string} pem - PEM 格式的公钥
 * @returns {Promise<CryptoKey>}
 */
async function importPublicKey(pem) {
  // 移除 PEM 头尾和换行
  const pemContents = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, '')
    .replace(/-----END PUBLIC KEY-----/, '')
    .replace(/\s/g, '');
  
  // Base64 解码为 ArrayBuffer
  const binaryString = window.atob(pemContents);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  
  // 导入公钥
  return await window.crypto.subtle.importKey(
    'spki',
    bytes,
    {
      name: 'RSA-OAEP',
      hash: { name: 'SHA-256' },
    },
    false,
    ['encrypt']
  );
}

/**
 * 使用 RSA 公钥加密文本
 * @param {string} text - 要加密的文本
 * @param {string} publicKeyPEM - PEM 格式的公钥
 * @returns {Promise<string>} Base64 编码的加密数据
 */
export async function encryptWithRSAPublicKey(text, publicKeyPEM) {
  const publicKey = await importPublicKey(publicKeyPEM);
  
  // 编码文本
  const encodedText = new TextEncoder().encode(text);
  
  // 加密
  const encrypted = await window.crypto.subtle.encrypt(
    {
      name: 'RSA-OAEP',
    },
    publicKey,
    encodedText
  );
  
  // 转换为 Base64
  const encryptedArray = new Uint8Array(encrypted);
  let binary = '';
  for (let i = 0; i < encryptedArray.length; i++) {
    binary += String.fromCharCode(encryptedArray[i]);
  }
  
  return window.btoa(binary);
}

/**
 * 生成随机字符串（用于测试）
 * @param {number} length 
 * @returns {string}
 */
export function generateRandomString(length = 32) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}
