import easyocr
import re
import torch
import cv2
import numpy as np

class LocalOCREngine:
    def __init__(self):
        print("正在初始化本地 OCR 引擎...")
        # 初始化 EasyOCR，指定只识别英文('en')
        # 如果电脑有 NVIDIA 显卡且配置了 CUDA，可以设置 gpu=True，否则 gpu=False
        use_gpu = torch.cuda.is_available()
        
        if use_gpu:
            print(f"检测到可用 GPU: {torch.cuda.get_device_name(0)}，已自动开启 CUDA 加速。")
        else:
            print("未检测到 NVIDIA 显卡或未配置 CUDA 环境，系统将自动使用 CPU 进行计算。")
            
        # 将自适应的结果传入 gpu 参数
        self.reader = easyocr.Reader(['en'], gpu=use_gpu)
        print("本地 OCR 引擎初始化完毕。")

    def detect_and_recognize(self, image_path):
        """
        全图扫描照片中的所有文本区域
        """
        print(f"正在对图像进行全图扫描: {image_path}")
        try:
            # readtext 会返回一个列表，每个元素格式为: ([坐标], "文本", 置信度)
            files_bt = np.fromfile(image_path, np.uint8)
            img_mat = cv2.imdecode(files_bt, cv2.IMREAD_COLOR)
            if img_mat is None:
                raise ValueError("无法读取图像文件")
            
            raw_results = self.reader.readtext(img_mat)
            return raw_results
        
        except Exception as e:
            print(f"OCR 扫描过程中发生错误: {e}")
            return []

    def filter_registration_candidates(self, raw_results):
        """
        使用规则引擎对 OCR 结果进行初步清洗和筛选，提取可能属于注册号的文本
        """
        candidates = []
        
        # 定义一个基础的全球民航注册号粗筛规则（去掉横杠后，通常由 3 到 8 位的英文字母和数字组成）
        # 这里先做宽泛筛选，避免把漏识别或者格式微调的注册号直接丢弃
        base_pattern = re.compile(r'^[A-Z0-9]{3,8}$')

        for bbox, text, prob in raw_results:
            # 1. 基础清洗：转大写、去掉空格、去掉横杠
            cleaned_text = text.upper().replace(" ", "").replace("-", "")
            
            # 2. 正则粗筛：必须符合基本字符长度和类型要求，且置信度大于 40%
            if base_pattern.match(cleaned_text) and prob > 0.4:
                candidates.append({
                    'raw_text': text,         # 原始识别文本，方便调试
                    'cleaned_text': cleaned_text, # 清洗后的文本，用于数据库比对
                    'confidence': prob,       # 置信度
                    'bbox': bbox              # 文字在图中的坐标
                })
                
        return candidates

# 测试本模块功能
if __name__ == '__main__':
    # 这里可以放一张你准备好的飞机照片路径进行单模块测试
    test_image_path = "./images/IMG_6400-已增强-降噪.jpg" 
    
    # 实例化引擎
    engine = LocalOCREngine()
    
    # 模拟运行
    raw_res = engine.detect_and_recognize(test_image_path)
    if raw_res:
        print("\n--- 原始 OCR 识别到的所有文本 ---")
        for bbox, text, prob in raw_res:
            print(f"文本: {text} | 置信度: {prob:.2f}")
            
        print("\n--- 经过规则过滤后的注册号候选者 ---")
        filtered_res = engine.filter_registration_candidates(raw_res)
        for c in filtered_res:
            print(f"候选文本: {c['cleaned_text']} (原始: {c['raw_text']}) | 置信度: {c['confidence']:.2f}")
    else:
        print("未在图中识别到任何文本。")