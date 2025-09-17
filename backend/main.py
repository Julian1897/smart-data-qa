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
    conversation_id: Optional[str] = None

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

# 存储对话历史
conversations = {}

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

def extract_answer_from_full_response(full_response: str) -> str:
    """从SQl+答案的完整响应中提取纯答案部分，用于上下文分析"""
    # 如果包含SQL查询格式，提取SQL后面的内容
    if '🔍 **SQL查询**:' in full_response:
        # 找到SQL代码块结束后的内容
        parts = full_response.split('```')
        if len(parts) >= 3:
            # 返回第二个```后面的内容
            answer_part = parts[2].strip()
            # 移除开头的换行
            return answer_part.lstrip('\n').strip()
    
    # 如果没有SQL格式，直接返回原内容
    return full_response

# 处理代词引用的辅助函数
def has_implicit_context_reference(question: str, conversation_history: list) -> bool:
    """检查问题中是否包含隐式的上下文引用"""
    if not conversation_history:
        return False
    
    question_lower = question.lower()
    
    # 检查是否有明显的上下文指示词
    context_indicators = [
        '哪一年', '什么时候', '在哪里', '怎么', '为什么', '多少',
        '是哪', '是什么', '是谁', '是怎么', '有多', '有什么'
    ]
    
    # 如果问题以这些词开头，且问题很短，很可能是对上一个答案的追问
    for indicator in context_indicators:
        if question_lower.startswith(indicator) and len(question.strip()) < 30:
            return True
    
    # 检查是否是简短的追问（只有几个字，且包含疑问词）
    question_words = question.strip().split()
    if len(question_words) <= 8 and any(word in question_lower for word in ['什么', '哪', '怎么', '为什么', '多少', '何时']):
        return True
    
    return False

def has_pronoun_reference(question: str) -> bool:
    """检查问题中是否包含代词引用"""
    pronouns = ['他们', '它们', '这个', '这些', '那个', '那些', '他', '她', '它', '其', '此']
    return any(pronoun in question for pronoun in pronouns)

def process_pronoun_references(question: str, conversation_history: list) -> str:
    """处理问题中的代词引用和隐式上下文引用，基于对话历史替换代词"""
    if not conversation_history:
        return question
    
    # 获取最近的对话
    if len(conversation_history) > 0:
        last_question, last_full_answer = conversation_history[-1]
        # 提取纯答案部分，去除SQL信息
        last_answer = extract_answer_from_full_response(last_full_answer)
        
        # 简单的代词替换策略
        processed_question = question
        
        # 处理明显的代词引用
        if '他们' in question and '部门' in last_answer:
            # 尝试从上一个回答中提取部门名称
            import re
            dept_match = re.search(r'(\w+)部门', last_answer)
            if dept_match:
                dept_name = dept_match.group(1)
                processed_question = processed_question.replace('他们', f'{dept_name}部门')
            elif '平均工资最高的部门' in last_answer or '平均薪资最高' in last_answer:
                # 如果上一个问题是关于平均工资最高的部门
                processed_question = processed_question.replace('他们', '平均工资最高的部门')
        
        # 处理其他代词
        if '它' in question:
            # 尝试从上一个回答中提取实体
            import re
            entity_patterns = [
                r'(\w+属)',  # 地质学中的属
                r'(\w+样品)',  # 样品
                r'(\w+纪)',   # 地质纪
                r'(\w+化石)',  # 化石
            ]
            for pattern in entity_patterns:
                match = re.search(pattern, last_answer)
                if match:
                    entity = match.group(1)
                    processed_question = processed_question.replace('它', entity)
                    break
        
        # 处理隐式上下文引用
        if has_implicit_context_reference(question, conversation_history):
            # 对于隐式引用，添加上下文信息
            if '哪一年' in question.lower() or '什么时候' in question.lower():
                # 如果问的是时间，尝试找到上一个答案中的主要实体
                import re
                # 找到化石名称
                fossil_match = re.search(r'([\w\s]+化石|[\w\s]+fossil)', last_answer, re.IGNORECASE)
                if fossil_match:
                    fossil_name = fossil_match.group(1)
                    processed_question = f"{fossil_name}{processed_question}"
                # 找到其他实体
                elif re.search(r'(\w+属|最早的\w+)', last_answer):
                    entity_match = re.search(r'(最早的\w+|\w+属|\w+样品)', last_answer)
                    if entity_match:
                        entity = entity_match.group(1)
                        processed_question = f"{entity}{processed_question}"
                        
            elif '在哪里' in question.lower() or '哪个地方' in question.lower():
                # 如果问的是地点
                import re
                entity_match = re.search(r'(最早的\w+|\w+化石|\w+属)', last_answer)
                if entity_match:
                    entity = entity_match.group(1)
                    processed_question = f"{entity}{processed_question}"
        
        # 如果问题包含"这个"或"这些"
        if '这个' in question or '这些' in question:
            # 基于上一个问题的主题来推断
            if '部门' in last_question:
                processed_question = processed_question.replace('这个', '这个部门').replace('这些', '这些部门')
            elif '样品' in last_question or '化石' in last_question:
                processed_question = processed_question.replace('这个', '这个化石').replace('这些', '这些化石')
    
    return processed_question

def generate_contextual_query(processed_question: str, conversation_history: list, session_info: dict) -> str:
    """基于上下文生成SQL查询"""
    if not conversation_history:
        return f"SELECT * FROM {session_info['table_name']} LIMIT 10"
    
    last_question, last_answer = conversation_history[-1]
    
    # 如果当前问题是关于"他们的平均工资"并且上一个问题是关于"平均工资最高的部门"
    if '平均工资' in processed_question and '平均工资最高' in last_answer:
        # 生成查询最高平均工资部门的具体工资数值
        return f"SELECT department, AVG(salary) as avg_salary FROM {session_info['table_name']} GROUP BY department ORDER BY avg_salary DESC LIMIT 1"
    
    # 默认查询
    return f"SELECT * FROM {session_info['table_name']} LIMIT 10"

# 智能分析查询结果
def analyze_with_llm(question: str, sql_query: str, result: list, llm, session_info: dict = None, conversation_history: list = None) -> str:
    """使用LLM分析SQL查询结果，提供智能解释"""
    if not result:
        return "我不知道"

    if not llm:
        return "我不知道"

    try:
        # 构建对话上下文
        context_info = ""
        if conversation_history:
            context_info = "\n\n对话历史：\n"
            for i, (prev_q, prev_full_a) in enumerate(conversation_history[-3:]):
                # 提取纯答案部分，去除SQL信息
                prev_a = extract_answer_from_full_response(prev_full_a)
                context_info += f"{i+1}. 问题：{prev_q}\n   回答：{prev_a}\n"
            
            # 检查是否是上下文相关问题
            if has_implicit_context_reference(question, conversation_history) or has_pronoun_reference(question):
                context_info += "\n重要提示：当前问题似乎与上一个问题的答案相关。请仔细分析对话历史，理解当前问题所指的具体对象或实体。\n"
            
            context_info += "\n请根据对话历史理解当前问题中的代词和上下文引用。\n"

        # 准备分析提示
        context = f"""
用户问题：{question}

执行的SQL查询：
{sql_query}

查询结果：
{result}{context_info}

请分析查询结果并回答用户的问题。要求：
1. 直接回答用户的问题，不要重复查询结果的原始数据
2. 如果用户使用了代词（如"他们"、"它"、"这个"等），请结合对话历史来理解指代内容
3. 如果涉及时间/年代比较，请提供专业的时间顺序分析
4. 如果涉及地质年代（如Silurian, Carboniferous等），请说明它们的时间关系
5. 如果涉及地质演化程度，请考虑SiO2、MgO、K2O等化学成分的意义
6. 如果是数值比较，请明确指出最大/最小值
7. 如果是统计分析，请提供清晰的总结
8. 请用中文回答，语言简洁专业
9. 如果无法得出明确结论，请直接回答"我不知道"
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

def create_full_response(question: str, sql_query: str, result: list, session_info: dict, conversation_history: list) -> str:
    """创建包含SQL查询和答案的完整响应"""
    # 清理SQL查询，去除多余的空格和换行
    clean_sql = ' '.join(sql_query.split())
    
    print(f"[DEBUG] 正在创建包含SQL的响应: {clean_sql[:50]}...")  # 调试信息
    
    # 创建LLM实例进行智能分析
    llm = create_llm()
    
    if llm:
        # 尝试LLM智能分析
        llm_analysis = analyze_with_llm(question, sql_query, result, llm, session_info, conversation_history)
        if llm_analysis and llm_analysis != "我不知道":
            final_response = f"🔍 **SQL查询**: ```sql\n{clean_sql}\n```\n\n{llm_analysis}"
            print(f"[DEBUG] LLM分析成功，返回包含SQL的响应")  # 调试信息
            return final_response
    
    # 如果LLM分析失败，使用基础格式化
    basic_answer = format_answer(question, sql_query, result, session_info['table_name'])
    final_response = f"🔍 **SQL查询**: ```sql\n{clean_sql}\n```\n\n{basic_answer}"
    print(f"[DEBUG] 使用基础格式化，返回包含SQL的响应")  # 调试信息
    return final_response

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
        import time
        sessions[session_id] = {
            "db_path": db_path,
            "table_name": table_name,
            "file_name": file.filename,
            "columns": df.columns.tolist(),
            "row_count": len(df),
            "temp_dir": temp_dir,
            "created_at": time.time()
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
        
        # 获取或创建对话历史
        conversation_id = request.conversation_id or f"conv_{request.session_id}_default"
        if conversation_id not in conversations:
            conversations[conversation_id] = []
        
        conversation_history = conversations[conversation_id]
        
        # 处理代词引用问题
        processed_question = process_pronoun_references(request.question, conversation_history)
        
        # 创建LLM实例
        llm = create_llm()
        
        # 生成SQL查询
        sql_query = None
        
        if llm:
            try:
                # 使用LangChain创建SQL查询链（延迟导入）
                from langchain_community.utilities import SQLDatabase
                from langchain.chains import create_sql_query_chain

                # 创建数据库连接（供 LangChain 读取库结构）
                db = SQLDatabase.from_uri(f"sqlite:///{session_info['db_path']}")
                chain = create_sql_query_chain(llm, db)
                
                # 生成SQL查询（使用处理后的问题）
                sql_query = chain.invoke({"question": processed_question})
                
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
                        
            except Exception as llm_error:
                print(f"LLM查询生成失败: {llm_error}")
                sql_query = None
        
        # 如果LLM生成SQL失败，使用基础查询逻辑
        if not sql_query:
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
                # 对于代词引用或隐式上下文引用，尝试基于上下文生成查询
                if (has_pronoun_reference(request.question) or has_implicit_context_reference(request.question, conversation_history)) and conversation_history:
                    sql_query = generate_contextual_query(processed_question, conversation_history, session_info)
                else:
                    sql_query = f"SELECT * FROM {session_info['table_name']} LIMIT 20"
        
        # 执行查询
        result = execute_sql(session_info['db_path'], sql_query)
        
        # 创建完整响应（包含SQL和答案）
        full_answer = create_full_response(request.question, sql_query, result, session_info, conversation_history)
        
        # 创建基础答案用于上下文分析（不包含SQL，避免污染上下文）
        basic_answer = format_answer(request.question, sql_query, result, session_info['table_name'])
        
        # 保存对话历史（保存完整答案用于显示，但在上下文分析时会被过滤）
        conversations[conversation_id].append((request.question, full_answer))
        if len(conversations[conversation_id]) > 10:
            conversations[conversation_id] = conversations[conversation_id][-10:]
        
        return {
            "question": request.question,
            "answer": full_answer,
            "success": True,
            "conversation_id": conversation_id,
            "note": "SQL查询已显示"
        }
        
    except Exception as e:
        return {
            "question": request.question,
            "answer": f"查询出错：{str(e)}",
            "success": False
        }

@app.get("/sessions")
async def list_all_sessions():
    """获取所有会话列表"""
    session_list = []
    for session_id, session_info in sessions.items():
        # 获取该会话的对话数量
        conversation_count = len([conv_id for conv_id in conversations.keys() if conv_id.startswith(f"conv_{session_id}_")])
        
        session_list.append({
            "session_id": session_id,
            "file_name": session_info["file_name"],
            "row_count": session_info["row_count"],
            "columns_count": len(session_info["columns"]),
            "conversation_count": conversation_count,
            "created_at": session_info.get("created_at", "Unknown")
        })
    
    # 按创建时间排序（最新的在前）
    session_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return {
        "sessions": session_list
    }

@app.get("/sessions/{session_id}/conversations")
async def list_conversations(session_id: str):
    """获取会话的所有对话列表"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 查找所有属于该session的对话
    session_conversations = []
    for conv_id, history in conversations.items():
        if conv_id.startswith(f"conv_{session_id}_"):
            # 计算对话信息
            message_count = len(history)
            last_activity = None
            conversation_title = "新对话"
            
            if history:
                # 使用第一个问题作为标题（截取前30个字符）
                first_question = history[0][0]
                conversation_title = first_question[:30] + ("..." if len(first_question) > 30 else "")
                # 最后一次活动时间（模拟，实际应该用时间戳）
                import datetime
                last_activity = datetime.datetime.now().isoformat()
            
            session_conversations.append({
                "conversation_id": conv_id,
                "title": conversation_title,
                "message_count": message_count,
                "last_activity": last_activity
            })
    
    # 按最后活动时间排序（最新的在前）
    session_conversations.sort(key=lambda x: x['last_activity'] or '', reverse=True)
    
    return {
        "session_id": session_id,
        "conversations": session_conversations
    }

@app.post("/sessions/{session_id}/conversations")
async def create_new_conversation(session_id: str):
    """为指定会话创建新的对话"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 生成新的对话 ID
    import time
    new_conversation_id = f"conv_{session_id}_{int(time.time() * 1000)}"
    
    # 初始化空的对话历史
    conversations[new_conversation_id] = []
    
    return {
        "conversation_id": new_conversation_id,
        "title": "新对话",
        "message_count": 0,
        "created_at": time.time()
    }

@app.get("/sessions/{session_id}/conversations/{conversation_id}")
async def get_conversation_history(session_id: str, conversation_id: str):
    """获取对话历史"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if conversation_id not in conversations:
        return {"conversation_id": conversation_id, "history": []}
    
    return {
        "conversation_id": conversation_id,
        "history": conversations[conversation_id]
    }

@app.delete("/sessions/{session_id}/conversations/{conversation_id}")
async def clear_conversation_history(session_id: str, conversation_id: str):
    """清空对话历史"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if conversation_id in conversations:
        conversations[conversation_id] = []
    
    return {"message": "对话历史已清空"}

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