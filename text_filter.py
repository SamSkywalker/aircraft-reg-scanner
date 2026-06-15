import re

class RegistrationFilter:
    def __init__(self):
        # 强注册号正则
        self.strict_pattern = re.compile(r'^[A-Z0-9]{1,3}-[A-Z0-9]{3,6}$')
        # 航司关键词正则：匹配包含 AIRLINES, AIRWAYS, AIR 或 CARGO 的文本
        self.airline_keywords = re.compile(r'.*(AIRLINE|AIRWAY|AIR|CARGO|AERO).*')

    def clean_and_fix_text(self, text):
        cleaned = text.upper().replace(" ", "")
        if '-' in cleaned:
            cleaned = cleaned.replace("/", "1").replace("\\", "1")
        return cleaned

    def select_best_candidate(self, raw_results):
        """
        同时筛选注册号和航司视觉线索
        返回一个元组: (最可能的注册号, 识别到的航司线索文本)
        """
        valid_candidates = []
        visual_airline_hint = None
        max_airline_prob = 0.0

        for bbox, text, prob in raw_results:
            cleaned_text = text.upper().replace(" ", "")
            fixed_text = self.clean_and_fix_text(text)

            # 逻辑 1: 筛选注册号
            if self.strict_pattern.match(fixed_text):
                valid_candidates.append({
                    'registration': fixed_text,
                    'confidence': prob
                })
            else:
                # 逻辑 2: 如果不是注册号，判断是否包含航司关键词
                # 优先选取置信度最高的航司文本作为线索
                if self.airline_keywords.match(cleaned_text) and prob > max_airline_prob:
                    max_airline_prob = prob
                    visual_airline_hint = cleaned_text

        # 决定最终的注册号
        best_reg = None
        if valid_candidates:
            valid_candidates.sort(key=lambda x: x['confidence'], reverse=True)
            best_reg = valid_candidates[0]['registration']
            print(f"--> 锁定最可能的注册号: {best_reg}")
        
        if visual_airline_hint:
            print(f"--> 捕获到机身航司线索: {visual_airline_hint}")

        return best_reg, visual_airline_hint

if __name__ == '__main__':
    # 测试代码
    mock_ocr_results = [
        ([[0,0],[1,1]], "AIR CHINA", 0.95),
        ([[0,0],[1,1]], "B-28/3", 0.72),
    ]
    filter_tool = RegistrationFilter()
    reg, hint = filter_tool.select_best_candidate(mock_ocr_results)
    print(f"\n结果 - 注册号: {reg}, 航司线索: {hint}")