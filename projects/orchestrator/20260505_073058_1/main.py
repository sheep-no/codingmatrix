# projects/orchestrator/20260505_073058_1/main.py
import sys

def calculate(a: float, b: float, operator: str) -> float:
    """
    执行基本数学运算
    
    参数:
        a (float): 第一个操作数
        b (float): 第二个操作数
        operator (str): 运算符（+, -, *, /）
    
    返回:
        float: 运算结果
    
    异常:
        ValueError: 当运算符无效时抛出
        ZeroDivisionError: 当除以零时抛出
    """
    try:
        if operator == '+':
            return a + b
        elif operator == '-':
            return a - b
        elif operator == '*':
            return a * b
        elif operator == '/':
            if b == 0:
                raise ZeroDivisionError("除数不能为零")
            return a / b
        else:
            raise ValueError(f"无效运算符: {operator}")
    except Exception as e:
        print(f"计算错误: {str(e)}")
        sys.exit(1)

def main():
    """
    主程序入口，提供命令行计算器功能
    """
    print("欢迎使用简单计算器")
    print("请输入表达式（例如 '2 + 3'）或 'exit' 退出:")
    
    while True:
        try:
            user_input = input("> ").strip()
            
            if user_input.lower() == 'exit':
                print("感谢使用，再见!")
                break
                
            if not user_input:
                continue
                
            # 解析输入表达式
            parts = user_input.split()
            if len(parts) != 3:
                raise ValueError("请输入有效的表达式，格式为 '数字 运算符 数字'")
                
            num1 = float(parts[0])
            operator = parts[1]
            num2 = float(parts[2])
            
            # 执行计算
            result = calculate(num1, num2, operator)
            print(f"结果: {result}")
            
        except ValueError as ve:
            print(f"输入错误: {str(ve)}")
        except ZeroDivisionError as zde:
            print(f"错误: {str(zde)}")
        except Exception as e:
            print(f"发生未知错误: {str(e)}")

if __name__ == "__main__":
    main()