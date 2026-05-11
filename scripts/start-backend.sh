#!/bin/bash
# 快速启动后端并测试
pkill -9 -f uvicorn 2>/dev/null || true
sleep 2
cd /workspace
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"
sleep 5

# 测试健康检查
echo "Testing health endpoint..."
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool | head -10

# 测试 RSA 公钥
echo -e "\nTesting public-key endpoint..."
curl -s http://localhost:8000/api/v1/public-key | python3 -c "import sys, json; d=json.load(sys.stdin); print('✅ RSA Public Key:', 'OK' if 'public_key' in d else 'FAIL')"

echo -e "\nBackend is ready!"
