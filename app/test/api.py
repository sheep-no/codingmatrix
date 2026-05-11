import json
import urllib.request
import urllib.error
BASE_URL = "http://localhost:8080/api/v1"

def post(url, data):
    """发 POST 并打印返回"""
    try:
        req = urllib.request.Request(url,
                                     data=json.dumps(data).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req)
        print(">>>", url)
        print("<<<", resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(">>>", url, "ERROR", e.code)
        print("<<<", e.read().decode('utf-8'))


if __name__ == '__main__':
    # 1. 注册
    # post(BASE_URL + "/register",
    #      {"username": "mr_yang", "email": "mr_yang@example.com", "password": "12345678"})
    # 2. 登录
    post(BASE_URL + "/login",
         {"email": "mr_yang@example.com", "password": "12345678"})


# {\"username\":\"testuser\",\"email\":\"test@example.com\",\"password\":\"testpassword\"}"
# from openai import OpenAI
# import json
# client= OpenAI(
#     api_key="sk-hvrcuxxqjhkdsaysyqeulrvsjieknsdqablvxhuhesiuinny",
#     base_url="https://api.siliconflow.cn/v1"
# )
# code_response=client.chat.completions.create(
#     model="Qwen/Qwen2.5-Coder-7B-Instruct",
#     messages=[{"role": "user", "content": "写一个 Python 乘法口诀表只输出代码"}],
#     stream=False
# )
# print(code_response.choices[0].message.content)