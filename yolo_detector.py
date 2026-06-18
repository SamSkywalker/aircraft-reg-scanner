import cv2
import numpy as np
import os
from ultralytics import YOLO

class YoloRegistrationDetector:
    def __init__(self, model_path='best.pt'):
        self.model = YOLO(model_path)
        # 创建一个专门存放 YOLO 瞄准切片的调试文件夹
        self.debug_dir = './images/yolo_debug'
        os.makedirs(self.debug_dir, exist_ok=True)

    def crop_registration_area(self, image_path):
        """
        利用 YOLO 检测注册号区域并裁剪。同时将切片保存到本地供人工排查。
        """
        try:
            img_array = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"--> [YOLO] 读取图片失败: {e}")
            img = cv2.imread(image_path)

        if img is None:
            return None

        results = self.model(img, conf=0.4, verbose=False)
        
        if len(results) > 0 and len(results[0].boxes) > 0:
            box = results[0].boxes[0]
            xyxy = box.xyxy[0].cpu().numpy()
            
            xmin, ymin, xmax, ymax = map(int, xyxy)
            
            # 基础外扩边缘（防止切边）
            h, w, _ = img.shape
            padding = 15
            xmin = max(0, xmin - padding)
            ymin = max(0, ymin - padding)
            xmax = min(w, xmax + padding)
            ymax = min(h, ymax + padding)

            # 裁剪感兴趣区域 (ROI)
            cropped_img = img[ymin:ymax, xmin:xmax]
            
            # =================== 新增：断点可视化调试落盘 ===================
            base_name = os.path.basename(image_path)
            name, ext = os.path.splitext(base_name)
            # 生成诸如 debug_IMG_8464.jpg 的调试切片
            debug_save_path = os.path.join(self.debug_dir, f"debug_{name}{ext}")
            
            # 使用支持中文路径的安全写入方式
            try:
                is_success, buffer = cv2.imencode(ext, cropped_img)
                if is_success:
                    with open(debug_save_path, "wb") as f:
                        f.write(buffer)
                    print(f"--> [YOLO 调试器] 已将瞄准切片实时保存至: {debug_save_path}")
            except Exception as e:
                print(f"--> [YOLO 调试器] 保存切片失败: {e}")
            # ============================================================

            print(f"--> [YOLO] 成功精准定位注册号区域，完成局部裁剪。")
            return cropped_img
        
        print(f"--> [YOLO] 未检测到明显的注册号区域，安全降级返回全图。")
        return img