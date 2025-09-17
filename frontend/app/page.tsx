'use client'

import { useState, useEffect } from 'react'
import { Upload, MessageCircle, Database, FileText, Send, X, CheckCircle, Settings, Bot } from 'lucide-react'
import axios from 'axios'

interface DataInfo {
  file_name: string
  columns: string[]
  row_count: number
  sample_data?: any[]
}

interface Message {
  id: string
  type: 'user' | 'assistant' | 'system'
  content: string
  note?: string
  timestamp: Date
}

interface ModelConfig {
  api_key: string
  api_base: string
  model_name: string
}

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [dataInfo, setDataInfo] = useState<DataInfo | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentMessage, setCurrentMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [showModelConfig, setShowModelConfig] = useState(false)
  const [modelConfig, setModelConfig] = useState<ModelConfig>({
    api_key: '',
    api_base: 'https://api.openai.com/v1',
    model_name: 'gpt-3.5-turbo'
  })
  const [isModelConfigured, setIsModelConfigured] = useState(false)

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  // 预设的模型配置
  const modelPresets = [
    { name: 'OpenAI GPT-3.5', api_base: 'https://api.openai.com/v1', model_name: 'gpt-3.5-turbo' },
    { name: 'OpenAI GPT-4', api_base: 'https://api.openai.com/v1', model_name: 'gpt-4' },
    { name: 'DeepSeek', api_base: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
    { name: 'Moonshot', api_base: 'https://api.moonshot.cn/v1', model_name: 'moonshot-v1-8k' },
    { name: 'ZhipuAI', api_base: 'https://api.zhipuai.cn/api/paas/v4', model_name: 'glm-4' },
  ]

  // 检查模型配置状态
  useEffect(() => {
    checkModelConfig()
  }, [])

  const checkModelConfig = async () => {
    try {
      const response = await axios.get(`${API_BASE}/config/model`)
      setIsModelConfigured(response.data.api_key_configured)
    } catch (error) {
      console.error('检查模型配置失败:', error)
    }
  }

  const handleModelConfig = async () => {
    try {
      setIsLoading(true)
      await axios.post(`${API_BASE}/config/model`, modelConfig)
      setIsModelConfigured(true)
      setShowModelConfig(false)
      alert('模型配置成功！')
    } catch (error) {
      console.error('模型配置失败:', error)
      alert('模型配置失败，请检查API Key和地址是否正确')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileUpload = async (file: File) => {
    try {
      setIsLoading(true)
      setUploadProgress(0)
      
      // 验证文件类型
      if (!file.name.match(/\.(csv|xlsx|xls)$/i)) {
        alert('请选择CSV或Excel文件')
        return
      }
      
      // 验证文件大小（限制100MB）
      if (file.size > 100 * 1024 * 1024) {
        alert('文件大小不能超过100MB')
        return
      }
      
      const formData = new FormData()
      formData.append('file', file)

      console.log('正在上传文件:', file.name, '到地址:', `${API_BASE}/upload-file`)

      const response = await axios.post(`${API_BASE}/upload-file`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 300000, // 300秒超时，支持大文件上传
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
            setUploadProgress(percentCompleted)
          }
        }
      })

      console.log('上传成功:', response.data)

      setSessionId(response.data.session_id)
      setDataInfo(response.data.data_info)
      
      const systemMessage: Message = {
        id: Date.now().toString(),
        type: 'system',
        content: `数据已成功加载！文件：${response.data.data_info.file_name}，包含 ${response.data.data_info.row_count} 行数据，${response.data.data_info.columns.length} 个字段。`,
        timestamp: new Date()
      }
      setMessages([systemMessage])
    } catch (error) {
      console.error('文件上传失败:', error)
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNREFUSED') {
          alert('无法连接到服务器，请确保后端服务正在运行')
        } else if (error.response) {
          alert(`文件上传失败：${error.response.data?.detail || error.response.statusText}`)
        } else if (error.request) {
          alert('网络错误，请检查网络连接')
        } else {
          alert(`上传失败：${error.message}`)
        }
      } else {
        alert('文件上传失败，请重试')
      }
    } finally {
      setIsLoading(false)
      setUploadProgress(0)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      handleFileUpload(files[0])
    }
  }

  const handleQuery = async () => {
    if (!currentMessage.trim() || !sessionId) return

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: currentMessage,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setCurrentMessage('')
    setIsLoading(true)

    try {
      const response = await axios.post(`${API_BASE}/query`, {
        question: currentMessage,
        session_id: sessionId
      })

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: response.data.success 
          ? response.data.answer
          : response.data.answer || '查询失败，请重试',
        note: response.data.note,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('查询失败:', error)
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: '查询失败，请重试',
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        <header className="text-center mb-8">
          <div className="flex items-center justify-center gap-4 mb-4">
            <h1 className="text-4xl font-bold text-gray-800">
              智能数据问答系统
            </h1>
            <button
              onClick={() => setShowModelConfig(true)}
              className={`p-2 rounded-lg transition-colors ${
                isModelConfigured 
                  ? 'bg-green-100 text-green-600 hover:bg-green-200' 
                  : 'bg-orange-100 text-orange-600 hover:bg-orange-200'
              }`}
              title={isModelConfigured ? '模型已配置' : '配置模型'}
            >
              <Settings size={24} />
            </button>
          </div>
          <p className="text-gray-600">
            上传数据文件，用自然语言提问，获得智能分析结果
          </p>
        </header>

        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 数据上传区域 */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow-lg p-6">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <Database className="mr-2" size={20} />
                数据源
              </h2>
              
              {!dataInfo ? (
                <div>
                  <div
                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                      isDragOver 
                        ? 'border-blue-400 bg-blue-50' 
                        : 'border-gray-300 hover:border-gray-400'
                    }`}
                    onDrop={handleDrop}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setIsDragOver(true)
                    }}
                    onDragLeave={() => setIsDragOver(false)}
                  >
                    <Upload className="mx-auto mb-4 text-gray-400" size={48} />
                    <p className="text-gray-600 mb-4">
                      拖拽文件到此处或点击上传
                    </p>
                    <input
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleFileUpload(file)
                      }}
                      className="hidden"
                      id="file-upload"
                      disabled={isLoading}
                    />
                    <label
                      htmlFor="file-upload"
                      className={`px-4 py-2 rounded-lg cursor-pointer transition-colors ${
                        isLoading 
                          ? 'bg-gray-400 text-white cursor-not-allowed' 
                          : 'bg-blue-500 text-white hover:bg-blue-600'
                      }`}
                    >
                      {isLoading ? '上传中...' : '选择文件'}
                    </label>
                    <p className="text-sm text-gray-500 mt-2">
                      支持 CSV, Excel 格式，文件大小限制100MB
                    </p>
                  </div>
                  
                  {/* 上传进度条 */}
                  {isLoading && uploadProgress > 0 && (
                    <div className="mt-4">
                      <div className="flex justify-between text-sm text-gray-600 mb-1">
                        <span>上传进度</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-blue-500 h-2 rounded-full transition-all duration-300" 
                          style={{ width: `${uploadProgress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center text-green-600">
                    <CheckCircle className="mr-2" size={20} />
                    <span className="font-medium">数据已加载</span>
                  </div>
                  
                  <div className="bg-gray-50 rounded-lg p-4">
                    <h3 className="font-medium mb-2">文件信息</h3>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p><strong>文件名:</strong> {dataInfo.file_name}</p>
                      <p><strong>行数:</strong> {dataInfo.row_count}</p>
                      <p><strong>列数:</strong> {dataInfo.columns.length}</p>
                    </div>
                  </div>

                  <div className="bg-gray-50 rounded-lg p-4">
                    <h3 className="font-medium mb-2">数据字段</h3>
                    <div className="flex flex-wrap gap-1">
                      {dataInfo.columns.map((col, idx) => (
                        <span
                          key={idx}
                          className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded"
                        >
                          {col}
                        </span>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setDataInfo(null)
                      setSessionId(null)
                      setMessages([])
                    }}
                    className="w-full bg-gray-500 text-white px-4 py-2 rounded-lg hover:bg-gray-600 transition-colors"
                  >
                    重新上传
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* 对话区域 */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-lg p-6 h-[600px] flex flex-col">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <MessageCircle className="mr-2" size={20} />
                智能问答
              </h2>

              {/* 消息列表 */}
              <div className="flex-1 overflow-y-auto space-y-4 mb-4">
                {messages.length === 0 ? (
                  <div className="text-center text-gray-500 mt-20">
                    <FileText size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>上传数据后，您可以开始提问</p>
                    <div className="mt-4 text-sm">
                      <p>示例问题：</p>
                      <ul className="mt-2 space-y-1">
                        <li>• 数据总共有多少行？</li>
                        <li>• 显示前10条记录</li>
                        <li>• 各个类别的数量分布</li>
                      </ul>
                    </div>
                  </div>
                ) : (
                  messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${
                        message.type === 'user' ? 'justify-end' : 'justify-start'
                      }`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg p-3 ${
                          message.type === 'user'
                            ? 'bg-blue-500 text-white'
                            : message.type === 'system'
                            ? 'bg-green-100 text-green-800 border border-green-200'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        <p className="whitespace-pre-wrap">{message.content}</p>
                        {message.note && (
                          <div className="mt-1 text-xs opacity-70 italic">
                            {message.note}
                          </div>
                        )}
                        <p className="text-xs mt-1 opacity-70">
                          {message.timestamp.toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 输入区域 */}
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={currentMessage}
                  onChange={(e) => setCurrentMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
                  placeholder={sessionId ? "输入您的问题..." : "请先上传数据文件"}
                  disabled={!sessionId || isLoading}
                  className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
                <button
                  onClick={handleQuery}
                  disabled={!sessionId || isLoading || !currentMessage.trim()}
                  className="bg-blue-500 text-white px-4 py-2 rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                >
                  <Send size={20} />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 模型配置弹窗 */}
        {showModelConfig && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold flex items-center">
                  <Bot className="mr-2" size={20} />
                  模型配置
                </h3>
                <button
                  onClick={() => setShowModelConfig(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="space-y-4">
                {/* 预设模型选择 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    选择预设模型
                  </label>
                  <div className="grid grid-cols-1 gap-2">
                    {modelPresets.map((preset, index) => (
                      <button
                        key={index}
                        onClick={() => setModelConfig({
                          ...modelConfig,
                          api_base: preset.api_base,
                          model_name: preset.model_name
                        })}
                        className={`p-2 text-left border rounded-lg hover:bg-gray-50 ${
                          modelConfig.api_base === preset.api_base && modelConfig.model_name === preset.model_name
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200'
                        }`}
                      >
                        <div className="font-medium">{preset.name}</div>
                        <div className="text-xs text-gray-500">{preset.model_name}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* API Key */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    API Key *
                  </label>
                  <input
                    type="password"
                    value={modelConfig.api_key}
                    onChange={(e) => setModelConfig({...modelConfig, api_key: e.target.value})}
                    placeholder="输入您的API Key"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* API Base */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    API 地址
                  </label>
                  <input
                    type="text"
                    value={modelConfig.api_base}
                    onChange={(e) => setModelConfig({...modelConfig, api_base: e.target.value})}
                    placeholder="API地址"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* Model Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    模型名称
                  </label>
                  <input
                    type="text"
                    value={modelConfig.model_name}
                    onChange={(e) => setModelConfig({...modelConfig, model_name: e.target.value})}
                    placeholder="模型名称"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* 操作按钮 */}
                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={() => setShowModelConfig(false)}
                    className="flex-1 bg-gray-500 text-white py-2 px-4 rounded-lg hover:bg-gray-600 transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleModelConfig}
                    disabled={!modelConfig.api_key || isLoading}
                    className="flex-1 bg-blue-500 text-white py-2 px-4 rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {isLoading ? '配置中...' : '保存'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}