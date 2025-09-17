# 智能数据问答系统

基于 LangChain 和 Next.js 的智能数据分析问答平台，支持上传 CSV/Excel 文件，使用自然语言查询数据。

## 功能特点

- 📊 **多格式支持**: CSV、Excel 文件上传
- 🤖 **自然语言查询**: 使用 AI 将问题转换为 SQL 查询  
- 💬 **对话式交互**: 类似聊天的问答体验
- 📈 **实时结果**: 即时显示查询结果和 SQL 语句
- 🎨 **现代化界面**: 基于 Tailwind CSS 的响应式设计

## 技术栈

**后端:**
- FastAPI - Python Web 框架
- LangChain - AI 应用开发框架
- SQLAlchemy - 数据库 ORM
- Pandas - 数据处理
- SQLite - 数据存储

**前端:**
- Next.js 14 - React 框架
- TypeScript - 类型安全
- Tailwind CSS - UI 样式
- Lucide React - 图标库

## 快速开始

### 1. 安装依赖

**后端依赖:**
```bash
cd backend
pip install -r requirements.txt
```

**前端依赖:**
```bash
cd frontend
npm install
```

## 环境配置

### 方法一：环境变量配置（推荐）

复制环境变量模板:
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置您的大模型：

**OpenAI配置：**
```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-3.5-turbo
```

**DeepSeek配置：**
```env
OPENAI_API_KEY=your_deepseek_api_key
OPENAI_API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

**Moonshot配置：**
```env
OPENAI_API_KEY=your_moonshot_api_key
OPENAI_API_BASE=https://api.moonshot.cn/v1
MODEL_NAME=moonshot-v1-8k
```

**智谱AI配置：**
```env
OPENAI_API_KEY=your_zhipu_api_key
OPENAI_API_BASE=https://api.zhipuai.cn/api/paas/v4
MODEL_NAME=glm-4
```

**自定义API配置：**
```env
OPENAI_API_KEY=your_custom_api_key
OPENAI_API_BASE=https://your-custom-api-endpoint.com/v1
MODEL_NAME=your-model-name
```

### 方法二：Web界面配置

1. 启动系统后，点击页面右上角的设置图标 ⚙️
2. 在弹出的配置界面中：
   - 选择预设模型或手动配置
   - 输入API Key
   - 确认API地址和模型名称
   - 点击"保存"按钮

### 支持的模型提供商

| 提供商 | API地址 | 模型示例 |
|--------|---------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-3.5-turbo`, `gpt-4` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱AI | `https://api.zhipuai.cn/api/paas/v4` | `glm-4` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| 百川AI | `https://api.baichuan-ai.com/v1` | `baichuan2-turbo` |

> 💡 **提示**: 系统支持任何兼容OpenAI API格式的模型服务

### 启动服务

**启动后端 API:**
```bash
cd backend
python main.py
```
后端服务将在 http://localhost:8000 启动

**启动前端应用:**
```bash
cd frontend
npm run dev
```
前端应用将在 http://localhost:3000 启动

## 使用方法

1. **上传数据**: 拖拽或选择 CSV/Excel 文件上传
2. **开始提问**: 使用自然语言描述您想要查询的内容
3. **查看结果**: 系统会显示查询结果和对应的 SQL 语句

## 示例问题

- "数据总共有多少行？"
- "显示前10条记录"
- "各个类别的数量分布"
- "平均值是多少？"
- "找出最大值对应的记录"

## API 接口

### 上传文件
```
POST /upload-file
Content-Type: multipart/form-data
```

### 查询数据
```
POST /query
{
  "question": "您的问题",
  "session_id": "会话ID"
}
```

### 配置模型 API

```
POST /config/model
{
  "api_key": "your_api_key",
  "api_base": "https://api.provider.com/v1", 
  "model_name": "model-name"
}
```

### 获取模型配置状态
```
GET /config/model
```

## 项目结构

```
smart-data-qa/
├── backend/
│   ├── main.py              # FastAPI 主应用
│   └── requirements.txt     # Python 依赖
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # 主页面组件
│   │   ├── layout.tsx       # 布局组件
│   │   └── globals.css      # 全局样式
│   ├── package.json         # Node.js 依赖
│   └── tailwind.config.js   # Tailwind 配置
└── .env.example             # 环境变量模板
```

## 注意事项

- 确保已安装 Python 3.8+ 和 Node.js 16+
- 支持多种AI模型提供商，只需配置相应的API Key和地址
- 上传的文件会临时存储在服务器，会话结束后自动清理
- 目前支持的文件格式：CSV、XLSX、XLS
- 系统具备基础查询模式，即使AI模型配置失败也能正常工作

## 故障排除

### 模型配置问题
1. **API Key无效**: 检查API Key是否正确，是否有足够的配额
2. **API地址错误**: 确认API地址格式正确，包含完整的端点路径
3. **模型名称错误**: 确认模型名称与API提供商的文档一致

### 文件上传问题
1. **文件格式不支持**: 仅支持CSV和Excel格式
2. **文件过大**: 建议文件大小不超过10MB
3. **编码问题**: CSV文件请使用UTF-8编码

### 网络连接问题
1. 检查后端服务是否正常运行在8000端口
2. 确认前端能够访问后端API
3. 检查防火墙设置

## 许可证

MIT License