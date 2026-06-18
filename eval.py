import json
from text_filter import RegistrationFilter
from main import verify_and_query_database

def evaluate_pipeline():
    # 1. 加载测试数据集
    with open('test_cases.json', 'r', encoding='utf-8') as f:
        cases = json.load(f)
    
    filter_tool = RegistrationFilter()
    total = len(cases)
    passed_count = 0
    
    print("==============================================")
    print(f" 开始执行数据驱动回归测试，共 {total} 个用例 ")
    print("==============================================")

    for idx, case in enumerate(cases):
        raw_ocr = case["raw_ocr"]
        expected = case["expected_reg"]
        should_pass = case["should_pass"]
        
        # 模拟文本过滤
        # 为了适配单条文本测试，包装成与 main.py 一致的 raw_results 格式
        mock_raw_results = [([[0,0],[1,1]], raw_ocr, 0.9)]
        candidates, _ = filter_tool.select_best_candidate(mock_raw_results)
        
        # 模拟数据库精准匹配
        hit_regs = []
        for cand in candidates:
            records = verify_and_query_database(cand)
            if records:
                hit_regs.append(records[0]["注册号"])
        
        # 结果判定
        is_success = False
        if should_pass:
            if expected in hit_regs:
                is_success = True
        else:
            if not hit_regs: # 预期不通过，且确实没有任何误报打进数据库
                is_success = True
                
        if is_success:
            passed_count += 1
            print(f"✅ 用例 {idx+1} 成功 | [{case['desc']}] 输入: {raw_ocr}")
        else:
            print(f"❌ 用例 {idx+1} 失败 | [{case['desc']}] 输入: {raw_ocr}")
            print(f"   --> 预期输出: '{expected}' (应该通过: {should_pass})")
            print(f"   --> 实际输出: {hit_regs}")

    # 计算整体准确率
    accuracy = (passed_count / total) * 100
    print("==============================================")
    print(f" 测试完成! 通过率: {passed_count}/{total} ({accuracy:.2f}%)")
    print("==============================================")

if __name__ == '__main__':
    evaluate_pipeline()