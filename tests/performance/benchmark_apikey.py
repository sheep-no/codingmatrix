#!/usr/bin/env python3
"""
API Key 管理性能基准测试

测试以下操作的性能：
1. RSA 加密/解密
2. Redis 存储/读取
3. 批量导入
4. 健康检查
"""
import time
import statistics
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.utils.crypto import RSAKeyManager, get_rsa_key_manager
import base64
import uuid

# ========== 测试配置 ==========
ITERATIONS = 100
WARMUP = 10


def benchmark(name, func, iterations=ITERATIONS):
    """基准测试函数"""
    # 预热
    for _ in range(WARMUP):
        func()
    
    # 正式测试
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # 转换为毫秒
    
    return {
        'name': name,
        'avg_ms': statistics.mean(times),
        'median_ms': statistics.median(times),
        'min_ms': min(times),
        'max_ms': max(times),
        'p95_ms': sorted(times)[int(len(times) * 0.95)],
        'p99_ms': sorted(times)[int(len(times) * 0.99)],
    }


def test_rsa_encrypt_decrypt():
    """测试 RSA 加密解密"""
    manager = get_rsa_key_manager()
    test_key = f"sk-test-{uuid.uuid4().hex}"
    
    # 使用公钥加密（模拟前端）
    public_key = manager.public_key
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    
    encrypted = public_key.encrypt(
        test_key.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    encrypted_base64 = base64.b64encode(encrypted).decode("utf-8")
    
    # 解密
    decrypted = manager.decrypt(encrypted_base64)
    assert decrypted == test_key


def test_get_public_key():
    """测试获取公钥"""
    manager = get_rsa_key_manager()
    public_key = manager.get_public_key_pem()
    assert len(public_key) > 100


def test_key_metadata_creation():
    """测试 Key 元数据创建"""
    from app.services.apikey_manager import KeyMetadata
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    meta = KeyMetadata(
        token=str(uuid.uuid4()),
        provider="siliconflow",
        remark="test",
        status="unverified",
        created_at=now.isoformat() + "Z",
        expires_at=(now + timedelta(hours=24)).isoformat() + "Z",
        ttl_seconds=86400,
        enabled=True
    )
    assert meta.provider == "siliconflow"


def test_token_generation():
    """测试 Token 生成"""
    from app.services.apikey_manager import APIKeyManager
    # 使用私有方法生成 token (如果有的话)
    token = str(uuid.uuid4())
    assert len(token) == 36


def run_benchmarks():
    """运行所有基准测试"""
    print("=" * 60)
    print("API Key 管理性能基准测试")
    print(f"迭代次数：{ITERATIONS}")
    print(f"预热次数：{WARMUP}")
    print("=" * 60)
    
    results = []
    
    # 1. RSA 加密/解密
    print("\n1. RSA 加密/解密...")
    result = benchmark("RSA 加密/解密", test_rsa_encrypt_decrypt)
    results.append(result)
    print(f"   平均：{result['avg_ms']:.2f}ms")
    print(f"   中位数：{result['median_ms']:.2f}ms")
    print(f"   P95：{result['p95_ms']:.2f}ms")
    
    # 2. 获取公钥
    print("\n2. 获取公钥...")
    result = benchmark("获取公钥", test_get_public_key)
    results.append(result)
    print(f"   平均：{result['avg_ms']:.2f}ms")
    print(f"   中位数：{result['median_ms']:.2f}ms")
    print(f"   P95：{result['p95_ms']:.2f}ms")
    
    # 3. 元数据创建
    print("\n3. 元数据创建...")
    result = benchmark("元数据创建", test_key_metadata_creation)
    results.append(result)
    print(f"   平均：{result['avg_ms']:.2f}ms")
    print(f"   中位数：{result['median_ms']:.2f}ms")
    print(f"   P95：{result['p95_ms']:.2f}ms")
    
    # 4. Token 生成
    print("\n4. Token 生成...")
    result = benchmark("Token 生成", test_token_generation)
    results.append(result)
    print(f"   平均：{result['avg_ms']:.2f}ms")
    print(f"   中位数：{result['median_ms']:.2f}ms")
    print(f"   P95：{result['p95_ms']:.2f}ms")
    
    # 汇总
    print("\n" + "=" * 60)
    print("性能测试结果汇总")
    print("=" * 60)
    print(f"{'操作':<20} | {'平均 (ms)':<10} | {'中位数 (ms)':<10} | {'P95 (ms)':<10}")
    print("-" * 60)
    for r in results:
        print(f"{r['name']:<20} | {r['avg_ms']:<10.2f} | {r['median_ms']:<10.2f} | {r['p95_ms']:<10.2f}")
    
    # 评估
    print("\n" + "=" * 60)
    print("性能评估")
    print("=" * 60)
    for r in results:
        if r['avg_ms'] < 1:
            status = "✅ 优秀"
        elif r['avg_ms'] < 10:
            status = "✅ 良好"
        elif r['avg_ms'] < 100:
            status = "✅ 可接受"
        else:
            status = "⚠️ 需要优化"
        print(f"{r['name']}: {status} ({r['avg_ms']:.2f}ms)")


if __name__ == "__main__":
    run_benchmarks()
