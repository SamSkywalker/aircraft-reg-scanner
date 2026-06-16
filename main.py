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

def generate_variant_regs(raw_text):
    """
    如果文本包含易混淆字符，自动分裂生成所有可能的组合
    """
    confusion_map = {
        'B': '8', '8': 'B', 
        'O': '0', '0': 'O',
        'I': '1', '1': 'I',
        'S': '5', '5': 'S',
        'Z': '2', '2': 'Z',
        'T': '1', '1': 'T',
        'A': '4', '4': 'A'
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

def verify_and_query_database(raw_reg_text):
    """
    联动最新的 prefixes 表与 aircraft 表，利用修复后的最终形态与长度指纹精准识别国籍与档案
    """
    if not os.path.exists(DB_PATH):
        print(f"错误: 找不到本地数据库文件 {DB_PATH}")
        return []

    # 1. 基础预处理
    raw_cleaned = raw_reg_text.upper().replace(" ", "")
    
    # 2. 派生所有可能的混淆变体
    candidates = generate_variant_regs(raw_cleaned)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    valid_hit_records = []
    
    for candidate in candidates:
        # 3. 先行执行数据驱动的斜杠/横杠智能修复，拿到最终的注册号形态
        # 这一步先假定大方向去修复符号，以便拿到准确的字符串指纹
        if '-' in candidate:
            final_reg = candidate.replace("/", "1").replace("\\", "1")
        else:
            # 盲切前缀来判断是否要补横杠
            pure_letters = candidate.replace("/", "").replace("\\", "")
            # 临时探测一下大前缀是否需要横杠
            cursor.execute("SELECT has_dash FROM prefixes WHERE clean_prefix = ? LIMIT 1", (pure_letters[:1],))
            test_match = cursor.fetchone()
            has_dash_guess = test_match[0] if test_match else 0
            
            if has_dash_guess == 1:
                first_slash_idx = -1
                for idx, char in enumerate(candidate):
                    if char in ['/', '\\']:
                        first_slash_idx = idx
                        break
                if first_slash_idx != -1:
                    before_slash = candidate[:first_slash_idx]
                    after_slash = candidate[first_slash_idx+1:]
                    processed_after = after_slash.replace('/', '1').replace('\\', '1')
                    final_reg = f"{before_slash}-{processed_after}"
                else:
                    final_reg = f"{candidate[:1]}-{candidate[1:]}"
            else:
                final_reg = candidate.replace("/", "1").replace("\\", "1")

        final_reg = re.sub(r'-+', '-', final_reg)

        # 4. 基于最终形态 [final_reg] 计算绝对精确的长度指纹
        final_pure_text = final_reg.replace("-", "")
        final_pure_len = len(final_pure_text)
        
        prefix_matches = []
        # 逐级提取前缀去数据库中检索
        for length in [3, 2, 1]:
            possible_clean_prefix = final_pure_text[:length]
            cursor.execute(
                "SELECT clean_prefix, has_dash, [Country Name] FROM prefixes WHERE clean_prefix = ?", 
                (possible_clean_prefix,)
            )
            prefix_matches = cursor.fetchall()
            if prefix_matches:
                break
                
        if not prefix_matches:
            continue # 前缀不合法，淘汰
            
        # === 核心多规则长度分流决策层（基于修复后的精准长度） ===
        chosen_match = None
        if len(prefix_matches) > 1:
            for match in prefix_matches:
                curr_country = str(match[2]).upper()
                # 大陆编排：去杠后总长 5 位（包含 B-XXXX 和新版 B-XXXA 混合编排）
                if final_pure_len == 5 and "TAIWAN" not in curr_country:
                    chosen_match = match
                    break
                # 台湾地区编排：去杠后总长 6 位（B-XXXXX 格式）
                elif final_pure_len == 6 and "TAIWAN" in curr_country:
                    chosen_match = match
                    break
            
            if not chosen_match:
                chosen_match = prefix_matches[0]
        else:
            chosen_match = prefix_matches[0]
            
        db_clean_prefix, has_dash, country_name = chosen_match
        # =======================================================

        # 5. 横杠合规性二次校验
        if has_dash == 1 and '-' not in final_reg:
            continue
        if has_dash == 0 and '-' in final_reg:
            continue
            
        # 6. 微观在册档案精确匹配
        query = """
            SELECT registration, manufacturerName, model, typecode, operator, built, owner
            FROM aircraft 
            WHERE registration = ? 
            LIMIT 1
        """
        cursor.execute(query, (final_reg,))
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
                "原始初筛输入": raw_reg_text,
                "所属国籍（地区）": country_name
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

def pipeline(image_path):
    if not os.path.exists(image_path):
        print(f"错误: 找不到输入的测试图片 {image_path}")
        return

    print("==================================================")
    print("启动带国籍（地区）校对与智能多路径纠错的识别流水线...")
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
        handle_failure(image_path, f"所有初筛文本 {ocr_detected_regs} 均未通过国籍（地区）格式校验或在册库无档案")
        return

    # 4. 决策输出层
    if len(hit_aircraft_list) == 1:
        aircraft_info = hit_aircraft_list[0]
        db_owner = str(aircraft_info["所有人"]).upper()
        db_operator = str(aircraft_info["运营单位"]).upper()
        
        print("\n================ 识别成功 ================")
        print(f"图片路径: {image_path}")
        print(f"确认注册号: {aircraft_info['注册号']} (原始OCR: {aircraft_info['原始初筛输入']})")
        # 新增：在此处打印根据前缀字典识别出来的国籍
        print(f"所属国籍（地区）: {aircraft_info['所属国籍（地区）'] if aircraft_info['所属国籍（地区）'] else '未知国籍（地区）'}")
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
            # 冲突列表里也顺便带上国籍（地区）提示
            print(f"  选项 {idx+1} -> 注册号: {aircraft_info['注册号']} [{aircraft_info['所属国籍（地区）']}] | 机型: {aircraft_info['详细机型']} | 运营单位: {aircraft_info['运营单位']}")
            
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