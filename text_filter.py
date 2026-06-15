import re

class RegistrationFilter:
    def __init__(self):
        # 航司关键词正则
        self.airline_keywords = re.compile(r'.*(AIRLINE|AIRWAY|AIR|CARGO|AERO).*')
        
        # 注册号放宽初筛：只要是 4-9 位由字母、数字、横杠、斜杠组成的文本即可
        self.loosely_pattern = re.compile(r'^[A-Z0-9/\-\\]{4,9}$')

    def select_best_candidate(self, raw_results):
        """
        不再盲目挑选单一文本，而是提取所有可能的注册号候选列表和航司线索
        """
        reg_candidates = []
        visual_airline_hint = None
        max_airline_prob = 0.0

        for bbox, text, prob in raw_results:
            cleaned_text = text.upper().replace(" ", "")
            
            if not cleaned_text:
                continue

            # 1. 提取航司视觉线索（航司 Logo 通常很大，不干扰它同时作为注册号候选的潜力）
            if self.airline_keywords.match(cleaned_text):
                if prob > max_airline_prob:
                    max_airline_prob = prob
                    visual_airline_hint = cleaned_text

            # 2. 只要符合基础注册号形态，统统收纳进候选列表
            if self.loosely_pattern.match(cleaned_text):
                reg_candidates.append(cleaned_text)

        # 去重处理，保持顺序
        reg_candidates = list(dict.fromkeys(reg_candidates))
        
        if visual_airline_hint:
            print(f"--> text_filter 捕获航司线索: {visual_airline_hint}")
        print(f"--> text_filter 初筛收集到的所有疑似注册号列表: {reg_candidates}")

        # 此时返回的是一个【列表】和【航司线索】
        return reg_candidates, visual_airline_hint

if __name__ == '__main__':
    mock_ocr_results = [
        ([[0,0],[1,1]], "AIR CHINA", 0.95),
        ([[0,0],[1,1]], "B-28/3", 0.72),
        ([[0,0],[1,1]], "JA81AM", 0.85),
        ([[0,0],[1,1]], "GATE", 0.90),
    ]
    
    filter_tool = RegistrationFilter()
    regs, hint = filter_tool.select_best_candidate(mock_ocr_results)
    print(f"\n正确输出 -> 候选列表: {regs}, 航司线索: {hint}")