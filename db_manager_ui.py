import os
import sqlite3
import pandas as pd
import streamlit as st

# 1. 绝对路径精确锁定你真正的数据库文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "aviation_core_2025_08.db")


def get_db_connection():
    if not os.path.exists(DB_PATH):
        st.error(f"❌ 未找到核心数据库文件，请确保它存在于: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# 2. 安全初始化：建立一个“影子备注扩展表”，100% 不破坏原有的 58 万条数据
def init_remark_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    # 创建独立扩展表：存储手工新加的飞机，或给老飞机打的备注
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aircraft_remarks (
            registration TEXT PRIMARY KEY,
            owner TEXT,
            operator TEXT,
            manufacturerName TEXT,
            model TEXT,
            typecode TEXT,
            built TEXT,
            remark TEXT,
            is_custom_added INTEGER DEFAULT 0 -- 0代表老飞机加备注，1代表纯手工新录入
        );
    """)
    conn.commit()
    conn.close()


init_remark_table()

# --- Streamlit UI 布局 ---
st.set_page_config(page_title="飞流扫描器 - 核心档案管理器", layout="wide")
st.title("✈️ 飞机档案本地数据库管理后台 (安全颗粒度对齐版)")
st.caption(f"当前安全锁定的核心后端: `{DB_PATH}` | 库内原始档案: `587,161` 条")

tab1, tab2, tab3 = st.tabs(["🔍 精准查询与修改", "➕ 手动添加新档案", "📊 备注与新增快照"])

# ==================== TAB 1: 查询与修改（联动影子表） ====================
with tab1:
    st.subheader("1. 飞机档案检索与更新")
    search_reg = st.text_input("请输入飞机注册号（例如：SP-FGR）:", "").strip()

    if search_reg:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 核心逻辑：先查影子表(是否有新录入或改过备注的)，如果没有，再连原始 aircraft 表
        cursor.execute("""
            SELECT 
                r.registration as r_reg, a.registration as a_reg,
                COALESCE(r.owner, a.owner) as owner,
                COALESCE(r.operator, a.operator) as operator,
                COALESCE(r.manufacturerName, a.manufacturerName) as manufacturerName,
                COALESCE(r.model, a.model) as model,
                COALESCE(r.typecode, a.typecode) as typecode,
                COALESCE(r.built, a.built) as built,
                r.remark
            FROM (SELECT * FROM aircraft WHERE UPPER(registration) = ?) a
            LEFT JOIN aircraft_remarks r ON UPPER(a.registration) = UPPER(r.registration)
            UNION
            SELECT 
                registration as r_reg, NULL as a_reg,
                owner, operator, manufacturerName, model, typecode, built, remark
            FROM aircraft_remarks 
            WHERE UPPER(registration) = ? AND is_custom_added = 1
        """, (search_reg.upper(), search_reg.upper()))
        
        record = cursor.fetchone()
        conn.close()

        if record:
            # 确定当前这架飞机最终展现出来的注册号
            final_reg = record["r_reg"] if record["r_reg"] else record["a_reg"]
            st.success(f"🎉 成功匹配到档案！")

            with st.form(key="update_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_owner = st.text_input("所有人/航空公司", record["owner"] or "")
                    new_operator = st.text_input("运营单位", record["operator"] or "")
                    new_manufacturer = st.text_input("制造商", record["manufacturerName"] or "")
                with col2:
                    new_model = st.text_input("详细机型", record["model"] or "")
                    new_typecode = st.text_input("ICAO机型代码 (typecode)", record["typecode"] or "")
                    new_built = st.text_input("出厂年份", record["built"] or "")

                new_remark = st.text_area("📝 针对该飞机的特定备注（如：常驻机型、特殊涂装、OCR易错字）", record["remark"] or "")

                submit_update = st.form_submit_button(label="💾 确认保存修改与备注")

                if submit_update:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    # 写入影子表，使用 REPLACE INTO 覆盖或新增备注项，绝对不碰原始 aircraft 表
                    cursor.execute("""
                        REPLACE INTO aircraft_remarks (registration, owner, operator, manufacturerName, model, typecode, built, remark, is_custom_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT is_custom_added FROM aircraft_remarks WHERE UPPER(registration)=?), 0))
                    """, (final_reg.upper(), new_owner, new_operator, new_manufacturer, new_model, new_typecode, new_built, new_remark, final_reg.upper()))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.success(f"修改成功！飞机 `{final_reg}` 的备注与调整数据已安全写入独立扩展层。")
        else:
            st.warning(f"⚠️ 本地核心库中暂无 `{search_reg}` 的档案。你可以前往【手动添加新档案】选项卡进行创建！")

# ==================== TAB 2: 手动添加新的注册号 ====================
with tab2:
    st.subheader("2. 录入全新飞机档案数据")
    with st.form(key="insert_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            ins_reg = st.text_input("* 注册号 (必填，如 B-1234):").strip()
            ins_owner = st.text_input("* 所有人/航空公司 (如 Air China):")
            ins_operator = st.text_input("运营单位 (可选):")
        with col2:
            ins_manufacturer = st.text_input("制造商 (如 Airbus):")
            ins_model = st.text_input("详细机型 (如 A350-941):")
            ins_typecode = st.text_input("ICAO机型代码 (如 A359):")
            ins_built = st.text_input("出厂年份 (可选):")

        ins_remark = st.text_area("备注信息 (可选):")
        submit_insert = st.form_submit_button(label="➕ 将新注册号注入本地扩展库")

        if submit_insert:
            if not ins_reg or not ins_owner:
                st.error("❌ 失败：注册号与所有人为必填核心项，不能留空！")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 双重查重：查原表或者查影子表里手工加过的
                cursor.execute("""
                    SELECT 1 FROM aircraft WHERE UPPER(registration) = ?
                    UNION
                    SELECT 1 FROM aircraft_remarks WHERE UPPER(registration) = ? AND is_custom_added = 1
                """, (ins_reg.upper(), ins_reg.upper()))
                
                if cursor.fetchone():
                    st.error(f"❌ 强行阻断：注册号 `{ins_reg}` 在数据库中已经存在！请去第一栏检索它并进行修改。")
                    conn.close()
                else:
                    # 插入到影子表中，标记 is_custom_added = 1
                    cursor.execute("""
                        INSERT INTO aircraft_remarks (registration, owner, operator, manufacturerName, model, typecode, built, remark, is_custom_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """, (ins_reg.upper(), ins_owner, ins_operator if ins_operator else None, 
                          ins_manufacturer, ins_model, ins_typecode, ins_built if ins_built else None, ins_remark))
                    conn.commit()
                    conn.close()
                    st.success(f"🚀 成功！全新的自定义注册号 `{ins_reg}` 已并入扩展层！")

# ==================== TAB 3: 备注与新增快照（只看增量表） ====================
with tab3:
    st.subheader("3. 独立扩展层管理快照（查看所有人工介入/新增的飞机）")
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("""
            SELECT registration as 注册号, owner as 所有人, model as 机型, 
                   remark as 人工备注, CASE is_custom_added WHEN 1 THEN '手动新增' ELSE '老数据改动' END as 数据来源 
            FROM aircraft_remarks 
            ORDER BY rowid DESC
        """, conn)
        
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("💡 扩展层目前很干净，还没有产生过人工修改或新录入的备注数据。")
    except Exception as e:
        st.error(f"读取异常: {e}")
    finally:
        conn.close()