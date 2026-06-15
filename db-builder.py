import pandas as pd
import sqlite3
import os
import time

# ==========================================
# 1. 路径与字段配置
# ==========================================
# 匹配你本地实际的路径
CSV_PATH = './data/aircraft-database-complete-2025-08.csv'  
DB_PATH = './data/aviation_core_2025_08.db'

# 我们需要的 OpenSky 核心字段
KEEP_COLUMNS = [
    'registration',        # 注册号（如 B-1234, N172DN）
    'manufacturerName',    # 制造商名称（如 Boeing, Airbus）
    'model',               # 详细机型（如 737-89L, F-14D）
    'typecode',            # ICAO 机型代码（如 B738, F14）
    'operator',            # 运营航司/单位
    'owner',               # 所有人
    'built'                # 出厂年份
]

def build_database():
    start_time = time.time()
    
    # 安全检查：确保原始 CSV 文件存在
    if not os.path.exists(CSV_PATH):
        print(f"错误: 在路径 '{CSV_PATH}' 未找到原始 CSV 文件！")
        print("请检查文件名和路径是否完全正确。")
        return

    print("==================================================")
    print("开始构建本地离线航空数据库...")
    print("正在分块读取大体积 CSV 文件，请稍候...")
    print("==================================================")

    # 2. 初始化本地 SQLite 数据库连接
    conn = sqlite3.connect(DB_PATH)
    
    # 3. 分块读取并写入数据库（防止 200MB 数据一次性加载榨干内存）
    chunk_size = 50000
    total_rows_processed = 0
    is_first_chunk = True

    for chunk in pd.read_csv(CSV_PATH, usecols=KEEP_COLUMNS, low_memory=False, chunksize=chunk_size, quotechar="'"):
        # 数据清洗 1：丢弃没有注册号（registration）的无效行
        chunk = chunk.dropna(subset=['registration'])
        
        # 数据清洗 2：为了让后续 OCR 检索 100% 匹配，将注册号全部转为大写、去除两端空格
        chunk['registration'] = chunk['registration'].astype(str).str.upper().str.strip()
        
        # 将当前分块的数据追加写入 SQLite 表中
        if is_first_chunk:
            chunk.to_sql('aircraft', conn, if_exists='replace', index=False)
            is_first_chunk = False
        else:
            chunk.to_sql('aircraft', conn, if_exists='append', index=False)
            
        total_rows_processed += len(chunk)
        print(f"已处理并灌入数据: {total_rows_processed} 条...")

    # 4. 关键步骤：为注册号字段创建索引 (Index)
    print("--------------------------------------------------")
    print("正在为注册号字段创建索引...")
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_registration ON aircraft (registration);")
    conn.commit()
    conn.close()

    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print("==================================================")
    print("本地航空离线数据库构建成功！")
    print(f"最终有效记录数: {total_rows_processed} 条")
    print(f"数据库文件路径: {os.path.abspath(DB_PATH)}")
    print(f"总耗时: {elapsed_time:.2f} 秒")
    print("==================================================")

if __name__ == '__main__':
    build_database()