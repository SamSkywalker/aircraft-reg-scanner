# db_manager.py
import os
import sqlite3
import pandas as pd
from typing import Optional, Dict, List, Tuple


class AviationDBManager:
    """飞机档案数据库管理类 - 纯后端版本，无UI依赖"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径，默认为 data/aviation_core_2025_08.db
        """
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "data", "aviation_core_2025_08.db")
        else:
            self.db_path = db_path
        
        self._init_remark_table()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_remark_table(self):
        """初始化影子备注扩展表"""
        conn = self._get_connection()
        cursor = conn.cursor()
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
                is_custom_added INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()
    
    def query_aircraft(self, registration: str) -> Optional[Dict]:
        """
        查询飞机档案（合并原始表与备注表）
        
        Args:
            registration: 飞机注册号（大小写不敏感）
            
        Returns:
            飞机信息字典，如果不存在返回None
            字段: registration, owner, operator, manufacturerName, 
                  model, typecode, built, remark, is_custom_added
        """
        reg_upper = registration.upper().strip()
        if not reg_upper:
            return None
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 先查影子表(是否有新录入或改过备注的)，如果没有，再连原始 aircraft 表
        cursor.execute("""
            SELECT 
                COALESCE(r.registration, a.registration) as registration,
                COALESCE(r.owner, a.owner) as owner,
                COALESCE(r.operator, a.operator) as operator,
                COALESCE(r.manufacturerName, a.manufacturerName) as manufacturerName,
                COALESCE(r.model, a.model) as model,
                COALESCE(r.typecode, a.typecode) as typecode,
                COALESCE(r.built, a.built) as built,
                r.remark,
                COALESCE(r.is_custom_added, 0) as is_custom_added
            FROM (SELECT * FROM aircraft WHERE UPPER(registration) = ?) a
            LEFT JOIN aircraft_remarks r ON UPPER(a.registration) = UPPER(r.registration)
            UNION
            SELECT 
                registration, owner, operator, manufacturerName, 
                model, typecode, built, remark, is_custom_added
            FROM aircraft_remarks 
            WHERE UPPER(registration) = ? AND is_custom_added = 1
        """, (reg_upper, reg_upper))
        
        record = cursor.fetchone()
        conn.close()
        
        return dict(record) if record else None
    
    def update_aircraft(self, registration: str, data: Dict) -> bool:
        """
        更新飞机档案（写入影子表，不碰原始表）
        
        Args:
            registration: 飞机注册号
            data: 要更新的字段字典，可包含:
                  owner, operator, manufacturerName, model, 
                  typecode, built, remark
        
        Returns:
            是否更新成功
        """
        reg_upper = registration.upper().strip()
        if not reg_upper:
            return False
        
        # 检查飞机是否存在（原始表或影子表）
        existing = self.query_aircraft(reg_upper)
        if not existing:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取当前是否 custom_added 状态
        cursor.execute(
            "SELECT is_custom_added FROM aircraft_remarks WHERE UPPER(registration) = ?",
            (reg_upper,)
        )
        result = cursor.fetchone()
        is_custom = result["is_custom_added"] if result else 0
        
        # 构建更新字段
        fields = {
            'owner': data.get('owner'),
            'operator': data.get('operator'),
            'manufacturerName': data.get('manufacturerName'),
            'model': data.get('model'),
            'typecode': data.get('typecode'),
            'built': data.get('built'),
            'remark': data.get('remark'),
            'is_custom_added': is_custom
        }
        
        cursor.execute("""
            REPLACE INTO aircraft_remarks (
                registration, owner, operator, manufacturerName, 
                model, typecode, built, remark, is_custom_added
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reg_upper,
            fields['owner'],
            fields['operator'],
            fields['manufacturerName'],
            fields['model'],
            fields['typecode'],
            fields['built'],
            fields['remark'],
            fields['is_custom_added']
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def add_aircraft(self, registration: str, data: Dict) -> bool:
        """
        添加新飞机档案（写入影子表，标记为自定义新增）
        
        Args:
            registration: 飞机注册号（必填）
            data: 飞机数据字典，可包含:
                  owner（必填）, operator, manufacturerName, 
                  model, typecode, built, remark
        
        Returns:
            是否添加成功
        """
        reg_upper = registration.upper().strip()
        if not reg_upper:
            return False
        
        owner = data.get('owner')
        if not owner:
            return False
        
        # 检查是否已存在
        existing = self.query_aircraft(reg_upper)
        if existing:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO aircraft_remarks (
                registration, owner, operator, manufacturerName, 
                model, typecode, built, remark, is_custom_added
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            reg_upper,
            owner,
            data.get('operator'),
            data.get('manufacturerName'),
            data.get('model'),
            data.get('typecode'),
            data.get('built'),
            data.get('remark')
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def delete_aircraft_remark(self, registration: str) -> bool:
        """
        删除飞机在影子表中的备注记录（恢复为原始数据）
        
        Args:
            registration: 飞机注册号
        
        Returns:
            是否删除成功
        """
        reg_upper = registration.upper().strip()
        if not reg_upper:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 只删除影子表中的记录（仅当不是custom_added时才能完全删除）
        cursor.execute(
            "DELETE FROM aircraft_remarks WHERE UPPER(registration) = ? AND is_custom_added = 0",
            (reg_upper,)
        )
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def delete_custom_aircraft(self, registration: str) -> bool:
        """
        删除手动新增的飞机记录（仅限is_custom_added=1的记录）
        
        Args:
            registration: 飞机注册号
        
        Returns:
            是否删除成功
        """
        reg_upper = registration.upper().strip()
        if not reg_upper:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM aircraft_remarks WHERE UPPER(registration) = ? AND is_custom_added = 1",
            (reg_upper,)
        )
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def get_all_remarks(self) -> pd.DataFrame:
        """
        获取所有影子表记录（人工备注/新增列表）
        
        Returns:
            DataFrame: 包含注册号、所有人、机型、备注、数据来源
        """
        conn = self._get_connection()
        df = pd.read_sql_query("""
            SELECT 
                registration as registration, 
                owner, 
                model, 
                remark, 
                CASE is_custom_added WHEN 1 THEN 'manual_add' ELSE 'modified' END as source
            FROM aircraft_remarks 
            ORDER BY rowid DESC
        """, conn)
        conn.close()
        return df
    
    def search_aircraft(self, keyword: str, limit: int = 50) -> List[Dict]:
        """
        模糊搜索飞机（按注册号、所有人、机型）
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
        
        Returns:
            匹配的飞机列表
        """
        if not keyword:
            return []
        
        keyword = f"%{keyword.upper()}%"
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 合并查询：原始表 + 影子表
        cursor.execute("""
            SELECT 
                COALESCE(r.registration, a.registration) as registration,
                COALESCE(r.owner, a.owner) as owner,
                COALESCE(r.operator, a.operator) as operator,
                COALESCE(r.manufacturerName, a.manufacturerName) as manufacturerName,
                COALESCE(r.model, a.model) as model,
                COALESCE(r.typecode, a.typecode) as typecode,
                COALESCE(r.built, a.built) as built,
                r.remark,
                COALESCE(r.is_custom_added, 0) as is_custom_added
            FROM aircraft a
            LEFT JOIN aircraft_remarks r ON UPPER(a.registration) = UPPER(r.registration)
            WHERE UPPER(a.registration) LIKE ? 
               OR UPPER(a.owner) LIKE ?
               OR UPPER(a.model) LIKE ?
            UNION
            SELECT 
                registration, owner, operator, manufacturerName, 
                model, typecode, built, remark, is_custom_added
            FROM aircraft_remarks 
            WHERE is_custom_added = 1
              AND (UPPER(registration) LIKE ? OR UPPER(owner) LIKE ? OR UPPER(model) LIKE ?)
            LIMIT ?
        """, (keyword, keyword, keyword, keyword, keyword, keyword, limit))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    
    def get_stats(self) -> Dict:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 原始表记录数
        cursor.execute("SELECT COUNT(*) as count FROM aircraft")
        original_count = cursor.fetchone()["count"]
        
        # 影子表记录数
        cursor.execute("SELECT COUNT(*) as count FROM aircraft_remarks")
        remark_count = cursor.fetchone()["count"]
        
        # 自定义新增数
        cursor.execute(
            "SELECT COUNT(*) as count FROM aircraft_remarks WHERE is_custom_added = 1"
        )
        custom_count = cursor.fetchone()["count"]
        
        conn.close()
        
        return {
            "original_records": original_count,
            "remark_records": remark_count,
            "custom_added": custom_count,
            "modified_records": remark_count - custom_count
        }


# 便捷函数：供外部直接调用
def get_db_manager(db_path: Optional[str] = None) -> AviationDBManager:
    """获取数据库管理器实例"""
    return AviationDBManager(db_path)


# 使用示例
if __name__ == "__main__":
    # 测试代码
    db = AviationDBManager()
    
    # 查询飞机
    plane = db.query_aircraft("B-1200")
    if plane:
        print(f"找到飞机: {plane['registration']}")
        print(f"所有人: {plane['owner']}")
    else:
        print("未找到该飞机")
    
    # 统计信息
    stats = db.get_stats()
    print(f"\n数据库统计: {stats}")
    
    # 搜索
    results = db.search_aircraft("Airbus", limit=5)
    print(f"\n搜索到 {len(results)} 条结果")
    
"""
usage:

# main.py
from db_manager import AviationDBManager

# 方式1：使用默认路径
db = AviationDBManager()

# 方式2：指定自定义路径
db = AviationDBManager("/path/to/your/database.db")

# 查询飞机
plane = db.query_aircraft("B-1234")
if plane:
    print(f"机型: {plane['model']}")

# 更新飞机信息（添加备注）
db.update_aircraft("B-1234", {
    "remark": "常驻北京首都机场",
    "owner": "Air China"
})

# 添加新飞机
db.add_aircraft("B-9999", {
    "owner": "China Southern",
    "model": "A350-900",
    "remark": "新引进飞机"
})

# 获取所有备注记录
remarks_df = db.get_all_remarks()
print(remarks_df)

# 模糊搜索
results = db.search_aircraft("Airbus", limit=20)
    

方法说明
query_aircraft(reg)	查询单架飞机完整信息
update_aircraft(reg, data)	更新飞机信息（写影子表）
add_aircraft(reg, data)	添加新飞机（标记为custom）
delete_aircraft_remark(reg)	删除影子表备注（恢复原始）
delete_custom_aircraft(reg)	删除自定义新增的飞机
get_all_remarks()	获取所有影子表记录
search_aircraft(keyword)	模糊搜索飞机
get_stats()	获取数据库统计信息
"""