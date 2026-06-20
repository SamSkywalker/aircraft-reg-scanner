import cv2
import numpy as np
import os
from ultralytics import YOLO

class YoloRegistrationDetector:
    def __init__(self, model_path='best-train4.pt', debug_dir='./images/yolo_debug'):
        """
        初始化检测器
        :param model_path: YOLO 模型权重路径
        :param debug_dir: 调试目录。如果传入 "0721"、None 或 False，则彻底关闭调试图片落地
        """
        self.model = YOLO(model_path)
        
        # 智能判定：触发暗号则彻底抹除 debug 路径，保持干净静音
        if debug_dir in ["0721", None, False]:
            self.debug_dir = None
        else:
            self.debug_dir = debug_dir
            os.makedirs(self.debug_dir, exist_ok=True)

    def crop_registration_area(self, image_path, padding_ratio=0.12):
        """
        利用 YOLO 检测注册号区域并裁剪。
        【降级策略】如果未检测到明显的注册号区域，安全降级返回整张原图大矩阵。
        """
        # 1. 使用支持中文路径的安全方式读取原图矩阵
        try:
            img_array = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"--> [YOLO] 字节流读取图片失败，尝试普通读取: {e}")
            img = cv2.imread(image_path)

        # 防御机制：如果是真正的死图（读不出任何矩阵数据），才返回 None 报文件损坏
        if img is None:
            return None

        h, w, _ = img.shape
        base_name = os.path.basename(image_path)
        name, ext = os.path.splitext(base_name)

        # 如果开启了 debug，复制一张干净的原图矩阵用来画双层瞄准镜
        debug_img = img.copy() if self.debug_dir else None

        # 2. 调用 YOLO 模型推理
        results = self.model(img, conf=0.4, verbose=False)
        
        # 3. 核心分支：检查是否检测到了框
        if len(results) > 0 and len(results[0].boxes) > 0:
            # 拿到置信度最高的一个框
            box = results[0].boxes[0]
            x1_orig, y1_orig, x2_orig, y2_orig = map(int, box.xyxy[0].cpu().numpy())
            conf = float(box.conf[0])

            # --- 按比例动态外扩算法 ---
            box_w = x2_orig - x1_orig
            box_h = y2_orig - y1_orig
            
            pad_w = int(box_w * padding_ratio)
            pad_h = int(box_h * padding_ratio)
            
            xmin_pad = max(0, x1_orig - pad_w)
            ymin_pad = max(0, y1_orig - pad_h)
            xmax_pad = min(w, x2_orig + pad_w)
            ymax_pad = min(h, y2_orig + pad_h)
            # ---------------------------

            # 局部精准裁剪
            cropped_img = img[ymin_pad:ymax_pad, xmin_pad:xmax_pad]
            print(f"--> [YOLO] 成功精准定位注册号区域，完成比例外扩裁剪。")

            # --- Debug 可视化输出流 ---
            if self.debug_dir:
                # 画双层框：绿色为 YOLO 原始框，蓝色为外扩实际切片框
                cv2.rectangle(debug_img, (x1_orig, y1_orig), (x2_orig, y2_orig), (0, 255, 0), 2)
                cv2.rectangle(debug_img, (xmin_pad, ymin_pad), (xmax_pad, ymax_pad), (255, 0, 0), 2)
                cv2.putText(debug_img, f"Reg {conf:.2f}", (x1_orig, max(20, y1_orig - 5)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # 安全写入大图瞄准框
                self._safe_imwrite(os.path.join(self.debug_dir, f"aim_{name}{ext}"), debug_img, ext)
                # 安全写入准备送去 OCR 的切片小图
                self._safe_imwrite(os.path.join(self.debug_dir, f"crop_{name}{ext}"), cropped_img, ext)
                print(f"--> [YOLO 调试器] 已将瞄准分析图与外扩切片实时保存至 debug 目录！")

            return cropped_img
        
        # 4. 【降级策略完美复活】没检测到，打印警告并安全返回原图大矩阵，绝不影响后续 OCR 的流程！
        print(f"--> [YOLO] 未检测到明显的注册号区域，安全降级返回全图。")
        
        if self.debug_dir:
            # 即使没框到，在 debug 模式下也输出一张无框图告知你：这张图降级了
            self._safe_imwrite(os.path.join(self.debug_dir, f"fallback_{name}{ext}"), img, ext)
            print(f"--> [YOLO 调试器] 已将触发降级兜底的无框原图保存至 debug 目录供分析！")

        return img

    def _safe_imwrite(self, save_path, img_matrix, ext):
        """内部工具：支持中文路径的安全图片写入"""
        try:
            _, buf = cv2.imencode(ext, img_matrix)
            with open(save_path, "wb") as f:
                f.write(buf)
        except Exception as e:
            print(f"❌ [YOLO] 写入 Debug 图片失败: {save_path}, 错误: {e}")

if __name__ == "__main__":
    # 简单测试
    detector = YoloRegistrationDetector()
    cropped = detector.crop_registration_area(r"X:\D\experiment\aircraft-reg-scanner\images\test2.jpg")
    if cropped is not None:
        print("裁剪成功，返回了图像矩阵！")
    else:
        print("裁剪失败，返回了 None！")