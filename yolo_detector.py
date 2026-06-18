import cv2
import numpy as np
from ultralytics import YOLO

class YoloRegistrationDetector:
    def __init__(self, model_path='best.pt'):
        # 初始化 YOLO 模型
        self.model = YOLO(model_path)

    def crop_registration_area(self, image_path):
        """
        利用 YOLO 检测注册号区域并裁剪。如果未检测到，返回原图矩阵。
        """
        # 使用兼容中文路径的方式读入图片矩阵
        try:
            img_array = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"--> [YOLO] 读取图片失败: {e}，尝试直接传入路径")
            img = cv2.imread(image_path)

        if img is None:
            return None

        # 运行 YOLO 推理 (conf=0.4 表示置信度大于40%才要)
        results = self.model(img, conf=0.4, verbose=False)
        
        # 检查是否检测到了框
        if len(results) > 0 and len(results[0].boxes) > 0:
            # 拿到置信度最高的一个框
            box = results[0].boxes[0]
            xyxy = box.xyxy[0].cpu().numpy() # [xmin, ymin, xmax, ymax]
            
            xmin, ymin, xmax, ymax = map(int, xyxy)
            
            # 【核心优化】给裁剪区域适当向外扩充 10-20 像素，防止 YOLO 框太紧把注册号首尾字母切掉
            h, w, _ = img.shape
            padding = 15
            xmin = max(0, xmin - padding)
            ymin = max(0, ymin - padding)
            xmax = min(w, xmax + padding)
            ymax = min(h, ymax + padding)

            # 裁剪感兴趣区域 (ROI)
            cropped_img = img[ymin:ymax, xmin:xmax]
            print(f"--> [YOLO] 成功精准定位注册号区域，完成局部裁剪。")
            return cropped_img
        
        # 降级策略：没检测到就返回原图矩阵，不影响后续 OCR
        print(f"--> [YOLO] 未检测到明显的注册号区域，安全降级返回全图。")
        return img