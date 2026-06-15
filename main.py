import os
import shutil
import sqlite3
from datetime import datetime
from ocr_engine import LocalOCREngine
from text_filter import RegistrationFilter

DB_PATH = './data/aviation_core_2025_08.db'
FAILED_DIR = './images/failed_cases'

def query_database(tail_number):
    if not os.path.exists(DB_PATH):
        print(f"错误: 找不到本地数据库文件 {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = """
        SELECT registration, manufacturerName, model, typecode, operator, built, owner
        FROM aircraft 
        WHERE registration = ? 
        LIMIT 1
    """
    cursor.execute(query, (tail_number,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "注册号": row[0],
            "制造商": row[1],
            "详细机型": row[2],
            "ICAO代码": row[3],
            "运营单位": row[4],
            "出厂年份": row[5],
            "所有人": row[6]
        }
    return None

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
    print("🛫 启动带航司交叉比对的识别流水线...")
    print("==================================================")

    # 1. OCR 扫描
    ocr_engine = LocalOCREngine()
    raw_ocr_results = ocr_engine.detect_and_recognize(image_path)
    if not raw_ocr_results:
        handle_failure(image_path, "OCR 未扫描到任何文本")
        return

    # 2. 过滤并提取注册号与航司线索
    reg_filter = RegistrationFilter()
    target_reg, airline_hint = reg_filter.select_best_candidate(raw_ocr_results)
    if not target_reg:
        handle_failure(image_path, "无法通过强‘-’号规则验证")
        return

    # 3. 查库
    aircraft_info = query_database(target_reg)
    if not aircraft_info:
        handle_failure(image_path, f"数据库未查到注册号 [{target_reg}]")
        return

    # 4. 核心逻辑：航司/所有人一致性比对
    db_owner = str(aircraft_info["所有人"]).upper()
    db_operator = str(aircraft_info["运营单位"]).upper()
    
    print("\n================ 🎉 识别成功 ================")
    print(f"注册号: {aircraft_info['注册号']}")
    print(f"制造商: {aircraft_info['制造商']}")
    print(f"详细机型: {aircraft_info['详细机型']}")
    print(f"ICAO代码: {aircraft_info['ICAO代码']}")
    print(f"出厂年份: {aircraft_info['出厂年份'] if aircraft_info['出厂年份'] else '暂无数据'}")

    # 判断并输出所有人/运营单位
    if airline_hint:
        # 如果机身线索文字在数据库的“所有人”或“运营单位”中能匹配上（双向包含判断）
        if (airline_hint in db_owner or db_owner in airline_hint or 
            airline_hint in db_operator or db_operator in airline_hint):
            print(f"所有人/运营单位: {aircraft_info['所有人']} (已通过机身视觉线索 [{airline_hint}] 验证核对)")
        else:
            # 不一致时，两个都输出
            print(f"所有人(数据库): {aircraft_info['所有人']}")
            print(f"运营单位(数据库): {aircraft_info['运营单位']}")
            print(f"警报 - 机身视觉线索显示为: {airline_hint} (与数据库不吻合，请人工核实)")
    else:
        # 如果图中没拍到明显的航司文字，直接正常输出数据库内容
        print(f"所有人: {aircraft_info['所有人']}")
        print(f"运营单位: {aircraft_info['运营单位']}")
        
    print("==================================================")

if __name__ == '__main__':
    target_image = "./images/test.jpg" 
    pipeline(target_image)