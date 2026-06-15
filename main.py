import os
import shutil
import sqlite3
from datetime import datetime
from ocr_engine import LocalOCREngine
from text_filter import RegistrationFilter
import glob
import re

DB_PATH = './data/aviation_core_2025_08.db'
FAILED_DIR = './images/failed_cases'

# ==========================================
# 修改点 1: 新增多路径变体生成算法 (解决 B/8, O/0)
# ==========================================
def generate_variant_regs(raw_text):
    """
    如果文本包含易混淆字符，自动分裂生成所有可能的组合
    例如："B-28B3" -> ["B-28B3", "B-2883"]
    """
    confusion_map = {
        'B': '8', '8': 'B', 
        'O': '0', '0': 'O'
    }
    variants = {raw_text}
    for i, char in enumerate(raw_text):
        if char in confusion_map:
            new_variants = set()
            for current_text in variants:
                substituted = current_text[:i] + confusion_map[char] + current_text[i+1:]
                new_variants.add(substituted)
            variants.update(new_variants)
    return list(variants)

# ==========================================
# 修改点 2: 升级查库函数，引入前缀格式校验与多路径比对
# ==========================================
def verify_and_query_database(raw_reg_text):
    """
    联动最新的 prefixes 表与 aircraft 表，验证并检索出所有合法的飞机档案
    """
    if not os.path.exists(DB_PATH):
        print(f"错误: 找不到本地数据库文件 {DB_PATH}")
        return []

    # 基础清洗：统一将看错的斜杠或反斜杠修正为横杠
    cleaned = raw_reg_text.upper()
    
    # 场景 A：如果文本里已经自带了横杠（例如 B-28/3）
    # 此时后面的斜杠 100% 是数字 1 被看错，直接替换成 1
    if '-' in cleaned:
        cleaned = cleaned.replace("/", "1").replace("\\", "1")
    else:
        # 场景 B：如果文本里完全没有横杠（例如日本飞机 JAB1AM 变成了 JAB/AM，或者中国飞机被整体看错成 B/28/3）
        # 我们优先把第一个斜杠当成可能的横杠，后续的斜杠当成数字 1
        # 为了让多路径变体发挥最大威力，我们直接把斜杠替换成横杠，但如果长度和特征符合中国 B-XXXX 格式，再特殊处理
        if cleaned.startswith('B/') and len(cleaned) >= 6:
            # 专门针对中国飞机把横杠看错成斜杠的情况（如 B/28/3 -> B-2813）
            cleaned = 'B-' + cleaned[2:].replace("/", "1").replace("\\", "1")
        else:
            # 其他通用情况，先统一换成横杠，交给后续前缀表去卡
            cleaned = cleaned.replace("/", "-").replace("\\", "-")
            
    # 压缩可能连续出现的横杠
    cleaned = re.sub(r'-+', '-', cleaned)
    
    # 派生所有可能的混淆变体
    candidates = generate_variant_regs(cleaned)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    valid_hit_records = []
    
    for candidate in candidates:
        # 1. 提取不带横杠的纯文本，用来去匹配 clean_prefix
        candidate_no_dash = candidate.replace("-", "")
        
        # 2. 宏观前缀校验：尝试匹配 clean_prefix（取前1到3位纯字母数字进行匹配）
        prefix_match = None
        for length in [3, 2, 1]:
            possible_clean_prefix = candidate_no_dash[:length]
            cursor.execute(
                "SELECT clean_prefix, has_dash FROM prefixes WHERE clean_prefix = ?", 
                (possible_clean_prefix,)
            )
            prefix_match = cursor.fetchone()
            if prefix_match:
                break
                
        if not prefix_match:
            continue # 连全球国籍纯字母前缀都对不上，直接淘汰
            
        db_clean_prefix, has_dash = prefix_match
        
        # 3. 横杠合规性硬卡（数据库中 1 代表有杠， 0 代表无杠）
        if has_dash == 1 and '-' not in candidate:
            continue
        if has_dash == 0 and '-' in candidate:
            continue
            
        # 4. 微观在册档案匹配
        query = """
            SELECT registration, manufacturerName, model, typecode, operator, built, owner
            FROM aircraft 
            WHERE registration = ? 
            LIMIT 1
        """
        cursor.execute(query, (candidate,))
        row = cursor.fetchone()
        
        if row:
            valid_hit_records.append({
                "注册号": row[0],
                "制造商": row[1],
                "详细机型": row[2],
                "ICAO代码": row[3],
                "运营单位": row[4],
                "出厂年份": row[5],
                "所有人": row[6],
                "原始初筛输入": raw_reg_text  # 新增：把触发命名的初筛源头文本带出去，修复日志 Bug
            })
            
    conn.close()
    return valid_hit_records

def handle_failure(image_path, reason):
    print(f"\n[结果]: fail (原因: {reason})")
    if not os.path.exists(FAILED_DIR):
        os.makedirs(FAILED_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(image_path)
    name, ext = os.path.splitext(base_name)
    new_name = f"fail_{timestamp}_{name}{ext}"
    dest_path = os.path.join(FAILED_DIR, new_name)
    try:
        shutil.copy(image_path, dest_path)
        print(f"已将失败图片归档至: {dest_path}")
    except Exception as e:
        print(f"归档失败: {e}")

# ==========================================
# 修改点 3: 重构流水线，嵌入双表验证业务层
# ==========================================
def pipeline(image_path):
    if not os.path.exists(image_path):
        print(f"错误: 找不到输入的测试图片 {image_path}")
        return

    print("==================================================")
    print("启动带航司交叉比对与智能多路径纠错的识别流水线...")
    print("==================================================")

    # 1. OCR 扫描
    ocr_engine = LocalOCREngine()
    raw_ocr_results = ocr_engine.detect_and_recognize(image_path)
    if not raw_ocr_results:
        handle_failure(image_path, "OCR 未扫描到任何文本")
        return

    # 2. 过滤并提取疑似注册号列表与航司线索
    reg_filter = RegistrationFilter()
    ocr_detected_regs, airline_hint = reg_filter.select_best_candidate(raw_ocr_results)
    if not ocr_detected_regs:
        handle_failure(image_path, "未检测到任何疑似注册号的文本")
        return

    # 3. 遍历初筛列表，双表联查与变体校对核心
    hit_aircraft_list = []
    
    for potential_reg in ocr_detected_regs:
        records = verify_and_query_database(potential_reg)
        if records:
            hit_aircraft_list.extend(records)

    if not hit_aircraft_list:
        handle_failure(image_path, f"所有初筛文本 {ocr_detected_regs} 均未通过国籍格式校验或在册库无档案")
        return

    # 4. 决策输出层
    if len(hit_aircraft_list) == 1:
        aircraft_info = hit_aircraft_list[0]
        db_owner = str(aircraft_info["所有人"]).upper()
        db_operator = str(aircraft_info["运营单位"]).upper()
        
        print("\n================ 识别成功 ================")
        print(f"图片路径: {image_path}")
        # 修复点：动态打印真正匹配上的那串原始初筛文本
        print(f"确认注册号: {aircraft_info['注册号']} (原始OCR: {aircraft_info['原始初筛输入']})")
        print(f"制造商: {aircraft_info['制造商']}")
        print(f"详细机型: {aircraft_info['详细机型']}")
        print(f"ICAO代码: {aircraft_info['ICAO代码']}")
        print(f"出厂年份: {aircraft_info['出厂年份'] if aircraft_info['出厂年份'] else '暂无数据'}")

        if airline_hint:
            if (airline_hint in db_owner or db_owner in airline_hint or 
                airline_hint in db_operator or db_operator in airline_hint):
                print(f"所有人/运营单位: {aircraft_info['所有人']} (已通过机身视觉线索 [{airline_hint}] 验证核对)")
            else:
                print(f"所有人(数据库): {aircraft_info['所有人']}")
                print(f"运营单位(数据库): {aircraft_info['运营单位']}")
                print(f"警报 - 机身视觉线索显示为: {airline_hint} (与数据库不吻合，请人工核实)")
        else:
            print(f"所有人: {aircraft_info['所有人']}")
            print(f"运营单位: {aircraft_info['运营单位']}")
    else:
        print("\n================ 识别成功 (存在多重在册冲突) ================")
        print(f"图片路径: {image_path}")
        print(f"提示：多个相似变体均符合规范且有活跃档案，输出列表供核对：")
        for idx, aircraft_info in enumerate(hit_aircraft_list):
            print(f"  选项 {idx+1} -> 注册号: {aircraft_info['注册号']} | 机型: {aircraft_info['详细机型']} | 运营单位: {aircraft_info['运营单位']}")
            
    print("==================================================")

if __name__ == '__main__':
    image_folder = "./images/"
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(image_folder, ext)))
    
    for image_path in image_files:
        print(f"Processing: {image_path}")
        pipeline(image_path)