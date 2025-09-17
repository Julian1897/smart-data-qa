from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import sqlite3
import os
from typing import Dict, Any, List, Optional
import traceback
import tempfile
from pydantic import BaseModel
import json
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = FastAPI(title="智能数据问答系统", version="1.0.0")

# 设置最大文件上传大小为100MB
app.max_request_size = 100 * 1024 * 1024

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str
    session_id: str

class DataSourceInfo(BaseModel):
    name: str
    type: str
    columns: List[str]
    row_count: int

class ModelConfig(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    api_key: str
    api_base: str
    model_name: str

# 存储会话信息
sessions = {}

# LLM配置
def create_llm(api_key: str = None, api_base: str = None, model_name: str = None):
    """创建LLM实例，支持自定义配置"""
    try:
        # 优先使用传入的参数，否则使用环境变量
        final_api_key = api_key or os.getenv("OPENAI_API_KEY")
        final_api_base = api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        final_model_name = model_name or os.getenv("MODEL_NAME", "gpt-3.5-turbo")
        
        if not final_api_key:
            raise ValueError("API Key is required")
        
        # 创建ChatOpenAI实例（延迟导入，避免导入阶段崩溃）
        from langchain_openai import ChatOpenAI  # 延迟导入

        llm = ChatOpenAI(
            openai_api_key=final_api_key,
            openai_api_base=final_api_base,
            model_name=final_model_name,
            temperature=0
        )
        return llm
    except Exception as e:
        print(f"LLM创建失败: {e}")
        return None

# 尝试以多种常见编码读取 CSV
def read_csv_with_auto_encoding(file_path: str) -> pd.DataFrame:
    candidate_encodings = [
        "utf-8",
        "utf-8-sig",
        "gbk",
        "gb2312",
        "big5",
        "shift_jis",
        "latin1",
    ]

    last_error: Optional[Exception] = None

    for enc in candidate_encodings:
        try:
            # 先尝试自动分隔符与 Python 引擎（更容错），并跳过坏行
            return pd.read_csv(
                file_path,
                encoding=enc,
                sep=None,
                engine="python",
                on_bad_lines="skip",
            )
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception:
            # 再尝试默认 C 引擎的常规读取
            try:
                return pd.read_csv(
                    file_path,
                    encoding=enc,
                    on_bad_lines="skip",
                )
            except Exception as e2:
                last_error = e2
                continue

    # 最后兜底：忽略无法解码的字节（pandas>=2.0 支持 encoding_errors）
    try:
        return pd.read_csv(
            file_path,
            encoding="utf-8",
            encoding_errors="ignore",
            sep=None,
            engine="python",
            on_bad_lines="skip",
        )
    except TypeError:
        # 如果不支持 encoding_errors，则退回 latin1
        return pd.read_csv(
            file_path,
            encoding="latin1",
            sep=None,
            engine="python",
            on_bad_lines="skip",
        )
    except Exception as e:
        # 如果依然失败，抛出更明确的异常
        raise HTTPException(status_code=400, detail=f"CSV 编码无法识别或解析失败: {str(last_error or e)}")

# 安全读取 Excel，针对不同扩展选择引擎
def read_excel_with_engine(file_path: str, extension: str) -> pd.DataFrame:
    ext = extension.lower()
    try:
        if ext == ".xls":
            try:
                import xlrd  # noqa: F401
            except Exception:
                raise HTTPException(status_code=400, detail="上传的是旧版 Excel(XLS) 文件，请先安装依赖：xlrd==1.2.0")
            return pd.read_excel(file_path, engine="xlrd")
        else:
            # xlsx/xlsm/xltx/xltm 等新版 Excel
            return pd.read_excel(file_path, engine="openpyxl")
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=400, detail=f"读取 Excel 失败，缺少依赖：{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 解析失败：{str(e)}")

# 地质化学数据专业分析
def analyze_geological_evolution(question: str, df: pd.DataFrame) -> str:
    """分析地质化学数据中的演化程度"""
    try:
        # 检查是否包含地质化学数据的关键列
        sio2_cols = [col for col in df.columns if 'SiO2' in str(col) or 'sio2' in str(col).lower()]
        mgo_cols = [col for col in df.columns if 'MgO' in str(col) or 'mgo' in str(col).lower()]
        k2o_cols = [col for col in df.columns if 'K2O' in str(col) or 'k2o' in str(col).lower()]
        sample_id_cols = [col for col in df.columns if 'sample' in str(col).lower() or '样品' in str(col)]

        if not (sio2_cols and mgo_cols and k2o_cols):
            return None

        sio2_col = sio2_cols[0]
        mgo_col = mgo_cols[0]
        k2o_col = k2o_cols[0]
        sample_id_col = sample_id_cols[0] if sample_id_cols else df.columns[0]

        # 计算演化指数：SiO2 + K2O - MgO
        # 这是地质学中常用的岩浆演化程度指标
        df_copy = df.copy()
        df_copy['演化指数'] = df_copy[sio2_col] + df_copy[k2o_col] - df_copy[mgo_col]

        # 找到演化程度最高的样品
        max_evolution_idx = df_copy['演化指数'].idxmax()
        max_sample = df_copy.iloc[max_evolution_idx]

        sample_id = max_sample[sample_id_col]
        evolution_index = max_sample['演化指数']
        sio2_val = max_sample[sio2_col]
        mgo_val = max_sample[mgo_col]
        k2o_val = max_sample[k2o_col]

        # 检查是否有岩石类型列
        rock_type_info = ""
        rock_type_cols = [col for col in df.columns if 'rock' in str(col).lower() or '岩石' in str(col) or 'type' in str(col).lower()]
        if rock_type_cols:
            rock_type = max_sample[rock_type_cols[0]]
            rock_type_info = f"，岩石类型为{rock_type}"

        return f"样品{sample_id}表现出最高的演化程度{rock_type_info}。该样品的演化指数为{evolution_index:.1f}（计算方式：SiO2({sio2_val}%) + K2O({k2o_val}%) - MgO({mgo_val}%) = {evolution_index:.1f}）。在地质学中，高SiO2含量、高K2O含量和低MgO含量通常表示岩浆经历了更高程度的分异演化。"

    except Exception as e:
        print(f"地质演化分析失败: {e}")
        return None

# 古生物地质时间专业分析
def analyze_geological_time(question: str, df: pd.DataFrame) -> str:
    """分析古生物分类学数据中的地质时间问题"""
    try:
        # 检查是否包含地质时间数据的关键列
        genus_cols = [col for col in df.columns if 'genus' in str(col).lower() or '属' in str(col)]
        period_cols = [col for col in df.columns if 'period' in str(col).lower() or '纪' in str(col)]
        epoch_cols = [col for col in df.columns if 'epoch' in str(col).lower() or '世' in str(col)]
        first_app_cols = [col for col in df.columns if 'first' in str(col).lower() and 'ma' in str(col).lower()]
        last_app_cols = [col for col in df.columns if 'last' in str(col).lower() and 'ma' in str(col).lower()]

        if not (genus_cols and first_app_cols and last_app_cols):
            return None

        genus_col = genus_cols[0]
        first_app_col = first_app_cols[0]
        last_app_col = last_app_cols[0]
        period_col = period_cols[0] if period_cols else None
        epoch_col = epoch_cols[0] if epoch_cols else None

        question_lower = question.lower()

        # 处理地质存续时间最长的属
        if "存续时间" in question and ("最长" in question or "最大" in question):
            # 计算每个属的存续时间（Ma值越大表示越早，所以存续时间 = FirstAppearance - LastAppearance）
            df_copy = df.copy()
            df_copy['存续时间'] = df_copy[first_app_col] - df_copy[last_app_col]

            # 找到存续时间最长的属
            max_duration_idx = df_copy['存续时间'].idxmax()
            max_genus = df_copy.iloc[max_duration_idx]

            genus_name = max_genus[genus_col]
            duration = max_genus['存续时间']
            first_app = max_genus[first_app_col]
            last_app = max_genus[last_app_col]

            period_info = ""
            if period_col:
                period_info = f"，主要存在于{max_genus[period_col]}纪"

            return f"{genus_name}属的地质存续时间最长{period_info}。该属从{first_app:.1f}百万年前首次出现，直到{last_app:.1f}百万年前最后消失，总存续时间为{duration:.1f}百万年。"

        # 处理奥陶纪时期筛选问题
        if "奥陶纪" in question or "ordovician" in question_lower:
            df_copy = df.copy()

            # 奥陶纪时间范围：485.4-443.8 Ma
            # 早奥陶世：485.4-470 Ma
            # 中奥陶世：470-458.4 Ma
            # 晚奥陶世：458.4-445.2 Ma

            if "晚奥陶世" in question or "late ordovician" in question_lower:
                # 筛选在奥陶纪出现，但在晚奥陶世之前就绝迹的属
                # 在奥陶纪出现：FirstAppearance <= 485.4
                # 在晚奥陶世前绝迹：LastAppearance > 458.4
                ordovician_genera = df_copy[
                    (df_copy[first_app_col] <= 485.4) &  # 在奥陶纪或之前出现
                    (df_copy[last_app_col] > 458.4) &    # 在晚奥陶世开始之前就绝迹
                    (df_copy[first_app_col] > df_copy[last_app_col])  # 确保时间逻辑正确
                ]
            else:
                # 筛选奥陶纪的属（FirstAppearance在奥陶纪范围内或更早，LastAppearance在奥陶纪范围内或更晚）
                ordovician_genera = df_copy[
                    (df_copy[first_app_col] <= 485.4) &  # 在奥陶纪结束前出现
                    (df_copy[last_app_col] >= 443.8)     # 在奥陶纪开始后消失
                ]

            if len(ordovician_genera) == 0:
                return "在指定条件下，没有找到符合要求的属。"

            # 构建回答
            genera_names = ordovician_genera[genus_col].tolist()
            if len(genera_names) == 1:
                genus_info = ordovician_genera.iloc[0]
                first_app = genus_info[first_app_col]
                last_app = genus_info[last_app_col]
                return f"符合条件的属是：{genera_names[0]}。该属在{first_app:.1f}百万年前首次出现，在{last_app:.1f}百万年前消失。"
            else:
                return f"符合条件的属有：{', '.join(genera_names)}。"

        return None

    except Exception as e:
        print(f"地质时间分析失败: {e}")
        return None

# 智能分析查询结果
def analyze_with_llm(question: str, sql_query: str, result: list, llm, session_info: dict = None) -> str:
    """使用LLM分析SQL查询结果，提供智能解释"""
    if not result:
        return "我不知道"

    # 特殊处理地质相关问题
    if session_info and session_info.get('db_path'):
        try:
            # 从数据库读取完整数据进行地质分析
            conn = sqlite3.connect(session_info['db_path'])
            df = pd.read_sql_query(f"SELECT * FROM {session_info['table_name']}", conn)
            conn.close()

            # 处理地质演化程度问题
            if "演化程度" in question or "演化" in question:
                geological_analysis = analyze_geological_evolution(question, df)
                if geological_analysis:
                    return geological_analysis

            # 处理地质时间相关问题
            if any(keyword in question.lower() for keyword in ['存续时间', '奥陶纪', 'ordovician', 'ma', '百万年', '地质时间', '属']):
                geological_time_analysis = analyze_geological_time(question, df)
                if geological_time_analysis:
                    return geological_time_analysis

        except Exception as e:
            print(f"地质数据分析失败: {e}")

    if not llm:
        return "我不知道"

    try:
        # 准备分析提示
        context = f"""
用户问题：{question}

执行的SQL查询：
{sql_query}

查询结果：
{result}

请基于查询结果回答用户的问题。特别注意：
1. 如果涉及时间/年代比较，请提供专业的时间顺序分析
2. 如果涉及地质年代（如Silurian, Carboniferous等），请说明它们的时间关系
3. 如果涉及地质演化程度，请考虑SiO2、MgO、K2O等化学成分的意义
4. 如果是数值比较，请明确指出最大/最小值
5. 如果是统计分析，请提供清晰的总结
6. 请用中文回答，语言简洁专业
7. 如果无法得出明确结论，请直接回答"我不知道"

请直接回答用户的问题，不要重复查询结果的原始数据。
"""

        # 调用LLM分析
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=context)]
        response = llm.invoke(messages)

        if hasattr(response, 'content'):
            return response.content
        else:
            return str(response)

    except Exception as e:
        print(f"LLM分析失败: {e}")
        return "我不知道"
def format_answer(question: str, sql_query: str, result: list, table_name: str) -> str:
    """将SQL查询结果转换为自然语言回答"""
    if not result:
        return "我不知道"

    question_lower = question.lower()

    # 特殊处理演化程度问题 - 如果SQL查询无法直接解决，返回"我不知道"
    if "演化程度" in question or "演化" in question:
        return "我不知道"

    # 处理计数类问题
    if "多少" in question_lower or "数量" in question_lower or "count" in question_lower:
        if len(result) == 1 and len(result[0]) == 1:
            count = list(result[0].values())[0]
            if "行" in question_lower:
                return f"数据总共有 {count} 行。"
            elif "人" in question_lower:
                return f"共有 {count} 人。"
            else:
                return f"总数量为 {count}。"
    
    # 处理显示前N条的问题
    if "前" in question_lower and ("条" in question_lower or "行" in question_lower):
        import re
        numbers = re.findall(r'\d+', question)
        limit = numbers[0] if numbers else "几"
        
        # 格式化表格数据
        if result:
            formatted_result = "以下是前{}条记录：\n\n".format(limit)
            for i, row in enumerate(result, 1):
                formatted_result += f"{i}. "
                row_parts = []
                for key, value in row.items():
                    row_parts.append(f"{key}: {value}")
                formatted_result += ", ".join(row_parts) + "\n"
            return formatted_result
    
    # 处理查找最值的问题
    if "最高" in question_lower or "最大" in question_lower:
        if result:
            row = result[0]
            if "薪资" in question_lower:
                name = row.get('姓名', '未知')
                salary = row.get('薪资', '未知')
                return f"薪资最高的是 {name}，薪资为 {salary} 元。"
            else:
                return f"最大值记录：{', '.join([f'{k}: {v}' for k, v in row.items()])}"
    
    if "最低" in question_lower or "最小" in question_lower:
        if result:
            row = result[0]
            if "薪资" in question_lower:
                name = row.get('姓名', '未知')
                salary = row.get('薪资', '未知')
                return f"薪资最低的是 {name}，薪资为 {salary} 元。"
            else:
                return f"最小值记录：{', '.join([f'{k}: {v}' for k, v in row.items()])}"
    
    # 处理平均值问题
    if "平均" in question_lower:
        if len(result) == 1 and len(result[0]) == 1:
            avg_value = list(result[0].values())[0]
            if "薪资" in question_lower or "工资" in question_lower:
                return f"平均薪资为 {avg_value:.2f} 元。"
            else:
                return f"平均值为 {avg_value:.2f}。"
        elif len(result) == 1 and 'department' in result[0] and 'avg_salary' in result[0]:
            # 处理单个部门的平均工资查询结果
            dept = result[0]['department']
            avg_sal = result[0]['avg_salary']
            if "最高" in question_lower:
                return f"平均工资最高的部门是 {dept}，平均工资为 {avg_sal:.2f} 元。"
            elif "最低" in question_lower:
                return f"平均工资最低的部门是 {dept}，平均工资为 {avg_sal:.2f} 元。"
            else:
                return f"{dept} 的平均工资为 {avg_sal:.2f} 元。"
    
    # 处理分组统计问题
    if "各" in question_lower and ("部门" in question_lower or "分组" in question_lower):
        if result:
            formatted_result = "统计结果如下：\n\n"
            for row in result:
                parts = []
                for key, value in row.items():
                    if "count" in key.lower() or "数量" in key:
                        parts.append(f"{value}人")
                    elif "avg" in key.lower() or "平均" in key:
                        parts.append(f"平均{value:.2f}")
                    else:
                        parts.append(f"{key}: {value}")
                formatted_result += "• " + ", ".join(parts) + "\n"
            return formatted_result
    
    # 处理筛选条件的问题
    if "的" in question_lower and len(result) > 0:
        if len(result) == 1:
            row = result[0]
            formatted_result = "查找到1条记录：\n"
            formatted_result += ", ".join([f"{k}: {v}" for k, v in row.items()])
            return formatted_result
        else:
            formatted_result = f"查找到{len(result)}条记录：\n\n"
            for i, row in enumerate(result[:10], 1):  # 最多显示10条
                formatted_result += f"{i}. "
                formatted_result += ", ".join([f"{k}: {v}" for k, v in row.items()])
                formatted_result += "\n"
            if len(result) > 10:
                formatted_result += f"... 还有{len(result) - 10}条记录"
            return formatted_result
    
    # 默认格式化
    if len(result) == 1 and len(result[0]) == 1:
        # 单个值结果
        value = list(result[0].values())[0]
        return f"查询结果：{value}"
    elif len(result) <= 5:
        # 少量记录，完整显示
        formatted_result = f"查询到{len(result)}条记录：\n\n"
        for i, row in enumerate(result, 1):
            formatted_result += f"{i}. "
            formatted_result += ", ".join([f"{k}: {v}" for k, v in row.items()])
            formatted_result += "\n"
        return formatted_result
    else:
        # 大量记录，只显示前几条
        formatted_result = f"查询到{len(result)}条记录，显示前5条：\n\n"
        for i, row in enumerate(result[:5], 1):
            formatted_result += f"{i}. "
            formatted_result += ", ".join([f"{k}: {v}" for k, v in row.items()])
            formatted_result += "\n"
        formatted_result += f"... 还有{len(result) - 5}条记录"
        return formatted_result

# 本地执行 SQL（不依赖 LangChain）
def execute_sql(db_path: str, sql_query: str):
    try:
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql_query(sql_query, conn)
            # 处理NaN值，确保JSON序列化不出错
            df = df.fillna('')
            return df.to_dict('records')
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL执行失败: {str(e)}")

@app.get("/")
async def root():
    return {"message": "智能数据问答系统 API"}

@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    try:
        # 检查文件大小（100MB限制）
        if hasattr(file, 'size') and file.size and file.size > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件大小超过100MB限制")
        
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="不支持的文件格式，请上传CSV或Excel文件")
        
        # 创建临时文件
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, file.filename)
        
        # 保存上传的文件 - 支持大文件
        with open(file_path, "wb") as buffer:
            # 分块读取以支持大文件
            chunk_size = 8192  # 8KB chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)
        
        # 读取数据
        _, ext = os.path.splitext(file.filename)
        if ext.lower() == '.csv':
            df = read_csv_with_auto_encoding(file_path)
        else:
            df = read_excel_with_engine(file_path, ext)
        
        # 数据清理：处理Excel文件常见问题
        # 1. 清理列名中的NULL字符和特殊字符
        df.columns = [str(col).replace('\x00', '').replace('\n', '_').replace('\r', '_').strip() 
                      if col is not None else f'未命名列_{i}' 
                      for i, col in enumerate(df.columns)]
        
        # 2. 处理重复列名
        seen_columns = {}
        new_columns = []
        for col in df.columns:
            if col in seen_columns:
                seen_columns[col] += 1
                new_columns.append(f"{col}_{seen_columns[col]}")
            else:
                seen_columns[col] = 0
                new_columns.append(col)
        df.columns = new_columns
        
        # 3. 处理NaN值和无穷大值
        df = df.replace([float('inf'), float('-inf')], None)  # 替换无穷大值
        df = df.fillna('')  # 用空字符串替换NaN值
        
        # 4. 确保所有列名都是有效的SQLite标识符
        df.columns = [f"col_{i}" if not str(col).strip() or str(col).startswith(tuple('0123456789')) 
                      else str(col).replace(' ', '_').replace('-', '_').replace('.', '_')
                      for i, col in enumerate(df.columns)]
        
        # 创建SQLite数据库
        session_id = f"session_{len(sessions)}"
        db_path = os.path.join(temp_dir, f"{session_id}.db")
        
        # 将数据存入SQLite
        conn = sqlite3.connect(db_path)
        table_name = "data_table"
        df.to_sql(table_name, conn, index=False, if_exists='replace')
        conn.close()
        
        # 存储会话信息
        sessions[session_id] = {
            "db_path": db_path,
            "table_name": table_name,
            "file_name": file.filename,
            "columns": df.columns.tolist(),
            "row_count": len(df),
            "temp_dir": temp_dir
        }
        
        # 为前端返回的示例数据也需要清理NaN值
        sample_data = df.head(3).fillna('').to_dict('records')
        
        return {
            "session_id": session_id,
            "data_info": {
                "file_name": file.filename,
                "columns": df.columns.tolist(),
                "row_count": len(df),
                "sample_data": sample_data
            }
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")

@app.post("/query")
async def query_data(request: QueryRequest):
    try:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        session_info = sessions[request.session_id]
        
        # 创建LLM实例
        llm = create_llm()
        
        if llm is None:
            # 如果LLM创建失败，尝试基础查询 + 智能分析模式
            question_lower = request.question.lower()
            
            # 改进的基础查询逻辑
            if "平均" in question_lower and ("工资" in question_lower or "薪资" in question_lower):
                if "部门" in question_lower:
                    if "最高" in question_lower or "最大" in question_lower:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary DESC LIMIT 1"
                    elif "最低" in question_lower or "最小" in question_lower:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary ASC LIMIT 1"
                    else:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary DESC"
                else:
                    sql_query = f"SELECT AVG(salary) as avg_salary FROM {session_info['table_name']}"
            elif "化石" in question_lower or "年代" in question_lower or "时间" in question_lower:
                # 对于涉及时间比较的查询，获取相关数据让LLM分析
                sql_query = f"SELECT * FROM {session_info['table_name']} WHERE 1=1"
                # 尝试找到包含时间、年代、化石等关键词的列
                time_related_columns = []
                for col in session_info['columns']:
                    col_lower = str(col).lower()
                    if any(keyword in col_lower for keyword in ['time', 'age', 'period', 'epoch', 'era', '时间', '年代', '时期']):
                        time_related_columns.append(col)
                
                if time_related_columns:
                    columns_str = ', '.join(time_related_columns + ['*'])
                    sql_query = f"SELECT {columns_str} FROM {session_info['table_name']}"
                else:
                    sql_query = f"SELECT * FROM {session_info['table_name']}"
            elif "最高" in question_lower and ("工资" in question_lower or "薪资" in question_lower):
                if "部门" in question_lower:
                    sql_query = f"SELECT department, MAX(salary) as max_salary FROM {session_info['table_name']} GROUP BY department ORDER BY max_salary DESC LIMIT 1"
                else:
                    sql_query = f"SELECT * FROM {session_info['table_name']} ORDER BY salary DESC LIMIT 1"
            elif "多少行" in question_lower or "行数" in question_lower or "count" in question_lower:
                if "部门" in question_lower:
                    sql_query = f"SELECT department, COUNT(*) as count FROM {session_info['table_name']} GROUP BY department"
                else:
                    sql_query = f"SELECT COUNT(*) as total_rows FROM {session_info['table_name']}"
            elif "前" in question_lower and ("条" in question_lower or "行" in question_lower):
                import re
                numbers = re.findall(r'\d+', request.question)
                limit = numbers[0] if numbers else "10"
                sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT {limit}"
            elif "各" in question_lower and "部门" in question_lower:
                sql_query = f"SELECT department, COUNT(*) as count, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department"
            elif "所有" in question_lower or "全部" in question_lower:
                sql_query = f"SELECT * FROM {session_info['table_name']}"
            else:
                # 默认查询：对于其他问题，尝试获取所有数据让LLM分析
                sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT 20"
            
            result = execute_sql(session_info['db_path'], sql_query)
            
            # 尝试使用LLM分析结果（即使主LLM失败，也尝试创建一个新的）
            try:
                analysis_llm = create_llm()
                if analysis_llm:
                    llm_analysis = analyze_with_llm(request.question, sql_query, result, analysis_llm, session_info)
                    if llm_analysis:
                        return {
                            "question": request.question,
                            "answer": llm_analysis,
                            "success": True,
                            "note": "使用LLM智能分析模式"
                        }
            except Exception as analysis_error:
                print(f"LLM分析失败: {analysis_error}")
            
            # 如果LLM分析也失败，回退到基础格式化
            answer = format_answer(request.question, sql_query, result, session_info['table_name'])
            
            return {
                "question": request.question,
                "answer": answer,
                "success": True,
                "note": "使用基础查询模式"
            }
        
        try:
            # 使用LangChain创建SQL查询链（延迟导入）
            from langchain_community.utilities import SQLDatabase  # 正确导入路径
            from langchain.chains import create_sql_query_chain  # 延迟导入

            # 创建数据库连接（供 LangChain 读取库结构）
            db = SQLDatabase.from_uri(f"sqlite:///{session_info['db_path']}")
            chain = create_sql_query_chain(llm, db)
            
            # 生成SQL查询
            sql_query = chain.invoke({"question": request.question})
            
            # 清理SQL查询字符串
            if isinstance(sql_query, str):
                # 移除可能的markdown格式
                sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
                # 提取SQL语句：找到SELECT开始到分号结束的部分
                lines = sql_query.split('\n')
                sql_lines = []
                in_sql = False
                for line in lines:
                    line = line.strip()
                    if line.upper().startswith(('SELECT', 'WITH')):
                        in_sql = True
                        sql_lines.append(line)
                    elif in_sql:
                        if line.endswith(';'):
                            sql_lines.append(line)
                            break
                        elif line and not line.startswith('--'):  # 忽略注释行
                            sql_lines.append(line)

                if sql_lines:
                    sql_query = ' '.join(sql_lines)
                else:
                    # 如果没有找到SQL，使用基础查询
                    sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT 10"
            
            # 执行查询
            result = execute_sql(session_info['db_path'], sql_query)
            
            # 首先尝试LLM智能分析
            llm_analysis = analyze_with_llm(request.question, sql_query, result, llm, session_info)
            if llm_analysis:
                return {
                    "question": request.question,
                    "answer": llm_analysis,
                    "success": True,
                    "note": "使用LLM智能分析"
                }
            
            # 如果LLM分析失败，回退到格式化答案
            answer = format_answer(request.question, sql_query, result, session_info['table_name'])
            
            return {
                "question": request.question,
                "answer": answer,
                "success": True
            }
            
        except Exception as llm_error:
            print(f"LLM查询失败: {llm_error}")
            # 如果LLM查询失败，尝试一些基本的查询模式
            question_lower = request.question.lower()
            
            # 改进的基础查询逻辑
            if "平均" in question_lower and ("工资" in question_lower or "薪资" in question_lower):
                if "部门" in question_lower:
                    # 各部门平均工资查询
                    if "最高" in question_lower or "最大" in question_lower:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary DESC LIMIT 1"
                    elif "最低" in question_lower or "最小" in question_lower:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary ASC LIMIT 1"
                    else:
                        sql_query = f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary DESC"
                else:
                    sql_query = f"SELECT AVG(salary) as avg_salary FROM {session_info['table_name']}"
            elif "最高" in question_lower and ("工资" in question_lower or "薪资" in question_lower):
                if "部门" in question_lower:
                    sql_query = f"SELECT department, MAX(salary) as max_salary FROM {session_info['table_name']} GROUP BY department ORDER BY max_salary DESC LIMIT 1"
                else:
                    sql_query = f"SELECT * FROM {session_info['table_name']} ORDER BY salary DESC LIMIT 1"
            elif "多少行" in question_lower or "行数" in question_lower or "count" in question_lower:
                if "部门" in question_lower:
                    sql_query = f"SELECT department, COUNT(*) as count FROM {session_info['table_name']} GROUP BY department"
                else:
                    sql_query = f"SELECT COUNT(*) as total_rows FROM {session_info['table_name']}"
            elif "前" in question_lower and ("条" in question_lower or "行" in question_lower):
                # 提取数字
                import re
                numbers = re.findall(r'\d+', request.question)
                limit = numbers[0] if numbers else "10"
                sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT {limit}"
            elif "各" in question_lower and "部门" in question_lower:
                sql_query = f"SELECT department, COUNT(*) as count, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department"
            elif "所有" in question_lower or "全部" in question_lower:
                sql_query = f"SELECT * FROM {session_info['table_name']}"
            else:
                sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT 5"
            
            result = execute_sql(session_info['db_path'], sql_query)
            answer = format_answer(request.question, sql_query, result, session_info['table_name'])
            
            return {
                "question": request.question,
                "answer": answer,
                "success": True,
                "note": "使用基础查询模式"
            }
        
    except Exception as e:
        return {
            "question": request.question,
            "answer": f"查询出错：{str(e)}",
            "success": False
        }

@app.get("/sessions/{session_id}/info")
async def get_session_info(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session_info = sessions[session_id]
    return {
        "session_id": session_id,
        "file_name": session_info["file_name"],
        "columns": session_info["columns"],
        "row_count": session_info["row_count"]
    }

@app.post("/config/model")
async def configure_model(config: ModelConfig):
    """配置大模型API"""
    try:
        # 测试配置是否有效
        llm = create_llm(config.api_key, config.api_base, config.model_name)
        if llm is None:
            raise HTTPException(status_code=400, detail="模型配置无效")
        
        # 存储到环境变量（仅在当前会话中有效）
        os.environ["OPENAI_API_KEY"] = config.api_key
        os.environ["OPENAI_API_BASE"] = config.api_base
        os.environ["MODEL_NAME"] = config.model_name
        
        return {
            "message": "模型配置成功",
            "api_base": config.api_base,
            "model_name": config.model_name
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置失败: {str(e)}")

@app.get("/config/model")
async def get_model_config():
    """获取当前模型配置"""
    return {
        "api_base": os.getenv("OPENAI_API_BASE", "未配置"),
        "model_name": os.getenv("MODEL_NAME", "未配置"),
        "api_key_configured": bool(os.getenv("OPENAI_API_KEY"))
    }

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        session_info = sessions[session_id]
        # 清理临时文件
        import shutil
        if os.path.exists(session_info["temp_dir"]):
            shutil.rmtree(session_info["temp_dir"])
        del sessions[session_id]
        return {"message": "会话已删除"}
    else:
        raise HTTPException(status_code=404, detail="会话不存在")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        # limit_max_size 参数在uvicorn.run中不可用，需要通过其他方式设置
    )