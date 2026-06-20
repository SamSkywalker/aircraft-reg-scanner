import streamlit as st
import cv2
import numpy as np
import os

# ==========================================
# 核心纽带：无缝引入你原汁原味的后端关键流水线
# ==========================================
from yolo_detector import YoloRegistrationDetector
from ocr_engine import LocalOCREngine
from text_filter import RegistrationFilter
from main import verify_and_query_database  # 确保 main.py 在同级目录下

# 1. 页面基本配置
st.set_page_config(
    page_title="飞机注册号智能扫描器",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ 飞机注册号离线智能扫描系统")
st.markdown("---")

# 2. 单例模式初始化模型：传入暗号 "0721" 关闭本地 Debug 图像落盘，由 UI 接管渲染
@st.cache_resource
def init_offline_pipeline():
    # 强制锁死训练出来的最新最佳模型权重
    detector = YoloRegistrationDetector(model_path='best-train6.pt', debug_dir="0721")
    ocr = LocalOCREngine()
    reg_filter = RegistrationFilter()
    return detector, ocr, reg_filter

with st.spinner("本地 AI 检测识别管线正在加载，请稍候..."):
    yolo_detector, ocr_engine, reg_filter = init_offline_pipeline()

# 3. 侧边栏：仅保留核心交互控件
st.sidebar.header("⚙️ 系统动态调校")
st.sidebar.info("仅供测试使用")

# 4. 主界面：图片拖拽上传区
uploaded_file = st.file_uploader("请在此拖拽或选择一张飞机照片...", type=["jpg", "jpeg", "png", "bmp"])

if uploaded_file is not None:
    # A. 兼容中文与特殊字符的内存级流读取（不伤硬盘）
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    
    # 建立左右两栏布局：左图右数
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🖼️ 原始输入图像")
        st.image(img_rgb, use_container_width=True)
        
    with col2:
        st.subheader("🎯 视觉管线实时状态")
        
        # B. 触发 YOLO 冲锋：为了绕过路径，将图片临时在本地保存供 detector 检索
        temp_path = "temp_ui_upload_target.jpg"
        # 兼容中文名落盘的银弹
        cv2.imencode('.jpg', img_bgr)[1].tofile(temp_path)
        
        # 调用与 main 逻辑一模一样的底层检测（内部自带未检测到自动降级返回原图大矩阵功能）
        input_img_matrix = yolo_detector.crop_registration_area(temp_path)
        
        # 清理临时交换文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if input_img_matrix is None:
            st.error("❌ 严重错误：系统无法加载该图像数据")
            st.stop()
            
        is_shape_match = (input_img_matrix.shape == img_bgr.shape)
        
        # 2. 深度无损验证：如果维度一致，进一步对前 100 个像素点进行抽样或整体均值比对
        is_fallback = False
        if is_shape_match:
            # 计算两张图的绝对平均误差，差值极小（由于JPG压缩导致的1-2个灰度级震荡）则视为同一张图
            absolute_diff = cv2.absdiff(input_img_matrix, img_bgr)
            mean_diff = np.mean(absolute_diff)
            if mean_diff < 3.0:  # 容忍误差阈值
                is_fallback = True

        # ========================================================
        # 核心输出层展示
        if not is_fallback:
            st.success("🎯 YOLO 成功瞄准并切片局部注册号区域")
            crop_display = cv2.cvtColor(input_img_matrix, cv2.COLOR_BGR2RGB)
            st.image(crop_display, caption="YOLO 推理按比例外扩切片 (ROI)", width=350)
        else:
            st.warning("⚠️ YOLO 漏检，系统自动降级触发【全图 OCR 扫描保底预案】")
            
        # D. 送入本地 OCR 引擎深度扫描
        with st.spinner("OCR 字符提取中..."):
            raw_ocr_results = ocr_engine.detect_and_recognize(input_img_matrix)
            
        if not raw_ocr_results:
            st.error("❌ 识别失败原因：OCR 未在裁切或全图区域内扫描到任何文本")
            st.stop()
            
        # E. 文本清洗与初筛
        ocr_detected_regs, airline_hint = reg_filter.select_best_candidate(raw_ocr_results)
        if not ocr_detected_regs:
            st.error("❌ 识别失败原因：未检测到任何疑似注册号的文本结构")
            st.stop()
            
        # F. 遍历初筛列表，双表联查与变体校对核心（完全复制 main 行为）
        hit_aircraft_list = []
        for potential_reg in ocr_detected_regs:
            # 联动你在 main 里面最新写的 Levenshtein 编辑距离模糊打分系统
            records = verify_and_query_database(potential_reg)
            if records:
                hit_aircraft_list.extend(records)
                
        if not hit_aircraft_list:
            st.error(f"❌ 识别失败原因：所有初筛文本 {ocr_detected_regs} 均未通过国籍格式校验或数据库中查无此档")
            st.stop()
            
        # ==========================================
        # G. 结果渲染层：严格按照 main.py 的多态判定输出
        # ==========================================
        st.markdown("---")
        
        if len(hit_aircraft_list) == 1:
            aircraft_info = hit_aircraft_list[0]
            db_owner = str(aircraft_info["所有人"])
            db_operator = str(aircraft_info["运营单位"])
            
            st.success(f"🎉 成功锁定注册号：**{aircraft_info['注册号']}** （原始输入: `{aircraft_info['原始初筛输入']}`）")
            
            # 渲染高纯度档案卡片
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                st.metric(label="所属国家/地区", value=f"{aircraft_info['所属国籍（地区）'] if aircraft_info['所属国籍（地区）'] else '未知'}")
                st.metric(label="航空公司 / 所有人", value=db_owner)
            with m_col2:
                st.metric(label="制造商与机型", value=f"{aircraft_info['制造商']} / {aircraft_info['详细机型']}")
                st.metric(label="ICAO 航空代码", value=aircraft_info['ICAO代码'])
                
            # 处理航司线索验证（复制 main 归一化层逻辑）
            if airline_hint:
                clean_hint = str(airline_hint).upper().replace(" ", "")
                clean_owner = db_owner.upper().replace(" ", "")
                clean_operator = db_operator.upper().replace(" ", "")
                
                if (clean_hint in clean_owner or clean_owner in clean_hint or 
                    clean_hint in clean_operator or clean_operator in clean_hint):
                    st.toast(f"✅ 机身线索 [{airline_hint}] 验证吻合！", icon="💖")
                else:
                    st.warning(f"⚠️ 警报：机身视觉线索显示为 `{airline_hint}`，与数据库档案不匹配，请人工核实。")
        else:
            st.warning("⚠️ 识别成功，但发现多重在册冲突 (存在相似变体活跃档案)")
            st.write("系统为你输出最优冲突备选列表供人工勾选：")
            st.dataframe(hit_aircraft_list, use_container_width=True)