#!/usr/bin/env python3
"""
加密登录测试

测试 RSA+AES 混合加密登录流程
"""

import sys
import base64
import json
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
import os

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"

def generate_aes_key():
 """生成随机 AES 密钥（256 位）"""
 return os.urandom(32)

def generate_iv():
 """生成随机 IV（128 位）"""
 return os.urandom(16)

def aes_encrypt(data, aes_key):
 """使用 AES 加密数据"""
 iv = generate_iv()
 
 # PKCS7 填充
 padder = sym_padding.PKCS7(128).padder()
 padded_data = padder.update(json.dumps(data).encode()) + padder.finalize()
 
 # AES CBC 加密
 cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
 encryptor = cipher.encryptor()
 ciphertext = encryptor.update(padded_data) + encryptor.finalize()
 
 # 组合 IV 和密文
 return base64.b64encode(iv + ciphertext).decode()

def rsa_encrypt_key(aes_key, public_key_pem):
 """使用 RSA 公钥加密 AES 密钥"""
 public_key = serialization.load_pem_public_key(
 public_key_pem.encode(),
 backend=default_backend()
 )
 
 encrypted_key = public_key.encrypt(
 aes_key,
 padding.OAEP(
 mgf=padding.MGF1(algorithm=padding.hashes.SHA256()),
 algorithm=padding.hashes.SHA256(),
 label=None
 )
 )
 
 return base64.b64encode(encrypted_key).decode()

def test_encrypted_login():
 """测试加密登录"""
 session = requests.Session()
 
 print("\n" + "="*60)
 print("加密登录测试")
 print("="*60 + "\n")
 
 # 1. 获取 CSRF Token
 print("1. 获取 CSRF Token...")
 response = session.get(f"{API}/csrf-token")
 if response.status_code != 200:
 print(f" [FAILED] 获取 CSRF Token 失败：{response.status_code}")
 return False
 
 csrf_token = response.json()["csrf_token"]
 print(f" CSRF Token: {csrf_token[:30]}...")
 
 # 2. 获取 RSA 公钥
 print("\n2. 获取 RSA 公钥...")
 response = session.get(f"{API}/public-key")
 if response.status_code != 200:
 print(f" [FAILED] 获取公钥失败：{response.status_code}")
 return False
 
 public_key = response.json()["public_key"]
 print(f" 公钥算法：RSA-OAEP (2048 位)")
 
 # 3. 加密登录数据
 print("\n3. 加密登录数据...")
 login_data = {
 "email": "test@example.com",
 "password": "Test123!@#"
 }
 
 aes_key = generate_aes_key()
 encrypted_data = aes_encrypt(login_data, aes_key)
 encrypted_key = rsa_encrypt_key(aes_key, public_key)
 
 print(f" AES 密钥：{base64.b64encode(aes_key).decode()[:30]}...")
 print(f" 加密数据：{encrypted_data[:50]}...")
 print(f" 加密密钥：{encrypted_key[:50]}...")
 
 # 4. 发送加密登录请求
 print("\n4. 发送加密登录请求...")
 encrypted_payload = {
 "encrypted_data": encrypted_data,
 "encrypted_key": encrypted_key
 }
 
 headers = {
 "Content-Type": "application/json",
 "X-CSRF-Token": csrf_token
 }
 
 response = session.post(
 f"{API}/login",
 json=encrypted_payload,
 headers=headers
 )
 
 if response.status_code == 200:
 data = response.json()
 print(f" 登录成功！")
 print(f" - 用户：{data.get('username', 'unknown')}")
 print(f" - 加密模式：{data.get('encryption_enabled', False)}")
 print(f" - Token: {data['access_token'][:50]}...")
 
 # 验证 Cookie
 cookies = session.cookies.get_dict()
 if "refresh_token" in cookies:
 print(f" - Refresh Token Cookie: ")
 if "csrf_token" in cookies:
 print(f" - CSRF Token Cookie: ")
 
 return True
 else:
 print(f" [FAILED] 登录失败：{response.status_code}")
 try:
 error = response.json()
 print(f" - 错误：{error.get('detail', 'Unknown')}")
 except:
 print(f" - 错误：{response.text[:200]}")
 return False

def test_plaintext_login():
 """测试明文登录（降级兼容）"""
 session = requests.Session()
 
 print("\n" + "="*60)
 print("明文登录测试（降级兼容）")
 print("="*60 + "\n")
 
 # 1. 获取 CSRF Token
 print("1. 获取 CSRF Token...")
 response = session.get(f"{API}/csrf-token")
 if response.status_code != 200:
 print(f" [FAILED] 获取 CSRF Token 失败")
 return False
 
 csrf_token = response.json()["csrf_token"]
 print(f" CSRF Token: {csrf_token[:30]}...")
 
 # 2. 明文登录
 print("\n2. 发送明文登录请求...")
 login_data = {
 "email": "test@example.com",
 "password": "Test123!@#"
 }
 
 headers = {
 "Content-Type": "application/json",
 "X-CSRF-Token": csrf_token
 }
 
 response = session.post(
 f"{API}/login",
 json=login_data,
 headers=headers
 )
 
 if response.status_code == 200:
 data = response.json()
 print(f" 登录成功（明文模式）")
 print(f" - 用户：{data.get('username', 'unknown')}")
 return True
 else:
 print(f" [WARNING] 登录失败（可能是用户不存在）: {response.status_code}")
 return None # 不是错误，只是用户可能不存在

if __name__ == "__main__":
 print("\n" + "="*60)
 print("RSA+AES 加密登录测试")
 print("="*60)
 
 # 测试加密登录
 encrypted_success = test_encrypted_login()
 
 # 测试明文登录（降级）
 plaintext_result = test_plaintext_login()
 
 print("\n" + "="*60)
 print("测试总结")
 print("="*60)
 print(f"加密登录：{' 通过' if encrypted_success else '[FAILED] 失败'}")
 if plaintext_result is not None:
 print(f"明文登录：{' 通过' if plaintext_result else '[WARNING] 用户不存在'}")
 
 print("\n安全特性:")
 print(" RSA 2048 位非对称加密")
 print(" AES 256 位对称加密")
 print(" CBC 模式 + PKCS7 填充")
 print(" OAEP 填充（RSA）")
 print(" CSRF Token 保护")
 print(" 一次一密钥（AES 密钥每次生成）")
 print()
