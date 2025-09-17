'use client'

import { useState, useEffect, useRef } from 'react'
import { Upload, MessageCircle, Database, FileText, Send, X, CheckCircle, Settings, Bot, Plus, History, Trash2 } from 'lucide-react'
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

interface ConversationState {
  conversation_id: string | null
  messages: Message[]
}

interface ConversationInfo {
  conversation_id: string
  title: string
  message_count: number
  last_activity: string | null
}

interface SessionInfo {
  session_id: string
  file_name: string
  row_count: number
  columns_count: number
  conversation_count: number
  created_at: number
}

interface ModelConfig {
  api_key: string
  api_base: string
  model_name: string
}

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [dataInfo, setDataInfo] = useState<DataInfo | null>(null)
  const [conversationState, setConversationState] = useState<ConversationState>({
    conversation_id: null,
    messages: []
  })
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
  const [conversations, setConversations] = useState<ConversationInfo[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [showConversationSidebar, setShowConversationSidebar] = useState(false)
  const [showSessionHistory, setShowSessionHistory] = useState(false)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
  
  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversationState.messages, isLoading])
  
  // 加载对话列表
  useEffect(() => {
    if (sessionId) {
      loadConversations()
    }
  }, [sessionId])
  
  // 加载所有会话列表
  useEffect(() => {
    loadAllSessions()
  }, [])
  
  const loadAllSessions = async () => {
    try {
      const response = await axios.get(`${API_BASE}/sessions`)
      setSessions(response.data.sessions)
    } catch (error) {
      console.error('加载会话列表失败:', error)
    }
  }
  
  const loadConversations = async () => {
    if (!sessionId) return
    
    try {
      const response = await axios.get(`${API_BASE}/sessions/${sessionId}/conversations`)
      setConversations(response.data.conversations)
    } catch (error) {
      console.error('加载对话列表失败:', error)
    }
  }
  
  const startNewSession = () => {
    // 重置所有状态，返回上传页面
    setDataInfo(null)
    setSessionId(null)
    setConversationState({
      conversation_id: null,
      messages: []
    })
    setConversations([])
  }
  
  const switchToSession = async (targetSessionId: string) => {
    try {
      // 获取会话信息
      const sessionResponse = await axios.get(`${API_BASE}/sessions/${targetSessionId}/info`)
      
      setSessionId(targetSessionId)
      setDataInfo({
        file_name: sessionResponse.data.file_name,
        columns: sessionResponse.data.columns,
        row_count: sessionResponse.data.row_count
      })
      
      // 获取该会话的对话列表
      const conversationsResponse = await axios.get(`${API_BASE}/sessions/${targetSessionId}/conversations`)
      setConversations(conversationsResponse.data.conversations)
      
      // 如果有对话，加载最新的一个
      if (conversationsResponse.data.conversations.length > 0) {
        const latestConv = conversationsResponse.data.conversations[0]
        await switchToConversation(latestConv.conversation_id)
      } else {
        // 没有对话，创建一个新的
        await createNewConversationForSession(targetSessionId)
      }
      
      setShowSessionHistory(false)
      
    } catch (error) {
      console.error('切换会话失败:', error)
    }
  }
  
  const createNewConversationForSession = async (targetSessionId?: string) => {
    const sessionToUse = targetSessionId || sessionId
    if (!sessionToUse) return
    
    try {
      const response = await axios.post(`${API_BASE}/sessions/${sessionToUse}/conversations`)
      
      // 更新对话列表
      await loadConversations()
      
      // 切换到新对话
      setConversationState({
        conversation_id: response.data.conversation_id,
        messages: []
      })
      
    } catch (error) {
      console.error('创建新对话失败:', error)
    }
  }
  
  const switchToConversation = async (conversationId: string) => {
    if (!sessionId) return
    
    try {
      const response = await axios.get(`${API_BASE}/sessions/${sessionId}/conversations/${conversationId}`)
      
      // 转换历史数据为消息格式
      const messages: Message[] = response.data.history.map((item: [string, string], index: number) => {
        const [question, answer] = item
        return [
          {
            id: `${conversationId}_q_${index}`,
            type: 'user' as const,
            content: question,
            timestamp: new Date()
          },
          {
            id: `${conversationId}_a_${index}`,
            type: 'assistant' as const,
            content: answer,
            timestamp: new Date()
          }
        ]
      }).flat()
      
      setConversationState({
        conversation_id: conversationId,
        messages: messages
      })
      
      setShowConversationSidebar(false)
      
    } catch (error) {
      console.error('切换对话失败:', error)
    }
  }
  
  const deleteConversation = async (conversationId: string) => {
    if (!sessionId) return
    
    try {
      await axios.delete(`${API_BASE}/sessions/${sessionId}/conversations/${conversationId}`)
      
      // 更新对话列表
      await loadConversations()
      
      // 如果删除的是当前对话，创建新对话
      if (conversationState.conversation_id === conversationId) {
        await createNewConversationForSession()
      }
      
    } catch (error) {
      console.error('删除对话失败:', error)
    }
  }

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
      
      // 创建新的对话
      const newConversationId = `conv_${response.data.session_id}_${Date.now()}`
      
      const systemMessage: Message = {
        id: Date.now().toString(),
        type: 'system',
        content: `数据已成功加载！文件：${response.data.data_info.file_name}，包含 ${response.data.data_info.row_count} 行数据，${response.data.data_info.columns.length} 个字段。`,
        timestamp: new Date()
      }
      
      setConversationState({
        conversation_id: newConversationId,
        messages: [systemMessage]
      })
      
      // 加载对话列表
      setTimeout(() => loadConversations(), 100)
      // 更新所有会话列表
      setTimeout(() => loadAllSessions(), 200)
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

    // 立即显示用户消息
    setConversationState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage]
    }))
    
    setCurrentMessage('')
    setIsLoading(true)

    try {
      const response = await axios.post(`${API_BASE}/query`, {
        question: currentMessage,
        session_id: sessionId,
        conversation_id: conversationState.conversation_id
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

      // 只添加助手消息（用户消息已经添加过了）
      setConversationState(prev => ({
        conversation_id: response.data.conversation_id || prev.conversation_id,
        messages: [...prev.messages, assistantMessage]
      }))
    } catch (error) {
      console.error('查询失败:', error)
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: '查询失败，请重试',
        timestamp: new Date()
      }
      // 只添加错误消息（用户消息已经添加过了）
      setConversationState(prev => ({
        ...prev,
        messages: [...prev.messages, errorMessage]
      }))
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
                      setConversationState({
                        conversation_id: null,
                        messages: []
                      })
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
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold flex items-center">
                  <MessageCircle className="mr-2" size={20} />
                  智能问答
                </h2>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setShowSessionHistory(true)}
                    className="text-sm bg-purple-100 text-purple-600 px-3 py-1 rounded-lg hover:bg-purple-200 transition-colors flex items-center"
                    title="查看会话历史（不同文件）"
                  >
                    <Database className="mr-1" size={14} />
                    会话历史
                  </button>
                  <button
                    onClick={startNewSession}
                    className="text-sm bg-green-100 text-green-600 px-3 py-1 rounded-lg hover:bg-green-200 transition-colors flex items-center"
                    title="上传新文件开始新会话"
                  >
                    <Plus className="mr-1" size={14} />
                    新会话
                  </button>
                </div>
              </div>

              {/* 消息列表 */}
              <div className="flex-1 overflow-y-auto space-y-4 mb-4">
                {conversationState.messages.length === 0 ? (
                  <div className="text-center text-gray-500 mt-20">
                    <FileText size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>上传数据后，您可以开始提问</p>
                    <div className="mt-4 text-sm">
                      <p>示例问题：</p>
                      <ul className="mt-2 space-y-1">
                        <li>• 数据总共有多少行？</li>
                        <li>• 显示前10条记录</li>
                        <li>• 各个类别的数量分布</li>
                        <li>• 平均工资最高的是哪个部门？</li>
                        <li>• 他们的平均工资是多少？ (上下文问题)</li>
                      </ul>
                    </div>
                  </div>
                ) : (
                  <>
                    {conversationState.messages.map((message) => (
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
                          <p className="whitespace-pre-wrap">
                          {message.content.split('```').map((part, index) => {
                            if (index % 2 === 1) {
                              // 这是代码块内容
                              const lines = part.split('\n')
                              const language = lines[0] || ''
                              const code = lines.slice(1).join('\n')
                              return (
                                <code key={index} className="block bg-gray-800 text-green-400 p-2 rounded mt-1 mb-1 text-sm overflow-x-auto">
                                  {code}
                                </code>
                              )
                            } else {
                              // 这是普通文本
                              return <span key={index}>{part}</span>
                            }
                          })}
                        </p>
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
                    ))}
                    
                    {/* 加载状态 */}
                    {isLoading && (
                      <div className="flex justify-start">
                        <div className="max-w-[80%] rounded-lg p-3 bg-gray-100 text-gray-800">
                          <div className="flex items-center space-x-2">
                            <div className="flex space-x-1">
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                            </div>
                            <span className="text-sm text-gray-500">正在思考...</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
                {/* 滚动锤点 */}
                <div ref={messagesEndRef} />
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

        {/* 会话历史弹窗 */}
        {showSessionHistory && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold flex items-center">
                  <Database className="mr-2" size={20} />
                  会话历史（所有文件）
                </h3>
                <button
                  onClick={() => setShowSessionHistory(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="space-y-3">
                {/* 新建会话按钮 */}
                <button
                  onClick={() => {
                    setShowSessionHistory(false)
                    startNewSession()
                  }}
                  className="w-full bg-green-500 text-white py-3 px-4 rounded-lg hover:bg-green-600 transition-colors flex items-center justify-center"
                >
                  <Plus className="mr-2" size={16} />
                  上传新文件开始新会话
                </button>

                {/* 会话列表 */}
                <div className="space-y-3">
                  {sessions.length === 0 ? (
                    <div className="text-center text-gray-500 py-8">
                      <Database size={48} className="mx-auto mb-2 text-gray-300" />
                      <p>还没有上传过文件</p>
                    </div>
                  ) : (
                    sessions.map((session) => (
                      <div
                        key={session.session_id}
                        className={`border rounded-lg p-4 cursor-pointer transition-colors ${
                          session.session_id === sessionId
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        }`}
                        onClick={() => switchToSession(session.session_id)}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium text-base mb-2 flex items-center">
                              <FileText className="mr-2" size={16} />
                              {session.file_name}
                            </h4>
                            <div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
                              <div>
                                <span className="font-medium">数据量：</span> {session.row_count} 行
                              </div>
                              <div>
                                <span className="font-medium">字段：</span> {session.columns_count} 个
                              </div>
                              <div>
                                <span className="font-medium">对话数：</span> {session.conversation_count} 个
                              </div>
                              <div>
                                <span className="font-medium">创建时间：</span> {new Date(session.created_at * 1000).toLocaleDateString()}
                              </div>
                            </div>
                          </div>
                          {session.session_id === sessionId && (
                            <div className="ml-3 bg-blue-500 text-white px-2 py-1 rounded text-xs">
                              当前
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 对话历史侧边栏 */}
        {showConversationSidebar && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold flex items-center">
                  <History className="mr-2" size={20} />
                  对话历史
                </h3>
                <button
                  onClick={() => setShowConversationSidebar(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="space-y-3">
                {/* 新建对话按钮 */}
                <button
                  onClick={() => createNewConversationForSession()}
                  className="w-full bg-orange-500 text-white py-2 px-4 rounded-lg hover:bg-orange-600 transition-colors flex items-center justify-center"
                >
                  <MessageCircle className="mr-2" size={16} />
                  在当前文件下开始新对话
                </button>

                {/* 对话列表 */}
                <div className="space-y-2">
                  {conversations.length === 0 ? (
                    <div className="text-center text-gray-500 py-8">
                      <MessageCircle size={48} className="mx-auto mb-2 text-gray-300" />
                      <p>还没有对话历史</p>
                    </div>
                  ) : (
                    conversations.map((conv) => (
                      <div
                        key={conv.conversation_id}
                        className={`border rounded-lg p-3 cursor-pointer transition-colors ${
                          conv.conversation_id === conversationState.conversation_id
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        }`}
                        onClick={() => switchToConversation(conv.conversation_id)}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium text-sm truncate">
                              {conv.title}
                            </h4>
                            <p className="text-xs text-gray-500 mt-1">
                              {conv.message_count} 条消息
                              {conv.last_activity && (
                                <span className="ml-2">
                                  {new Date(conv.last_activity).toLocaleString()}
                                </span>
                              )}
                            </p>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              if (confirm('确定要删除这个对话吗？')) {
                                deleteConversation(conv.conversation_id)
                              }
                            }}
                            className="text-gray-400 hover:text-red-500 p-1"
                            title="删除对话"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

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