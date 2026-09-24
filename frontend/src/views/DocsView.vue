<script setup>
import { BookOpen, Check, Copy, ExternalLink } from '@lucide/vue'
import { ref } from 'vue'

import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const copied = ref('')
const baseUrl = window.location.origin

const curlExample = `curl ${baseUrl}/v1/chat/completions \\\
  -H "Authorization: Bearer YOUR_GATEWAY_TOKEN" \\\
  -H "Content-Type: application/json" \\\
  -d '{
    "model": "meta/llama-3.1-70b-instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'`

const pythonExample = `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_GATEWAY_TOKEN",
)

response = client.chat.completions.create(
    model="meta/llama-3.1-70b-instruct",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)`

async function copy(name, value) {
  await navigator.clipboard.writeText(value)
  copied.value = name
  window.setTimeout(() => { copied.value = '' }, 1600)
}
</script>

<template>
  <PageHeader
    title="接口文档"
    description="网关提供 OpenAI 兼容接口，现有 SDK 通常只需替换 base_url 和 api_key。"
  >
    <template #actions>
      <a class="button button--secondary" href="/openapi.json" target="_blank">
        <ExternalLink :size="16" />
        OpenAPI JSON
      </a>
    </template>
  </PageHeader>

  <section class="docs-intro">
    <div>
      <p class="section-kicker">BASE URL</p>
      <code>{{ baseUrl }}/v1</code>
    </div>
    <button class="button button--secondary button--compact" type="button" @click="copy('base', `${baseUrl}/v1`)">
      <Check v-if="copied === 'base'" :size="15" />
      <Copy v-else :size="15" />
      {{ copied === 'base' ? '已复制' : '复制' }}
    </button>
  </section>

  <section class="docs-layout">
    <aside class="docs-index surface">
      <p class="section-kicker">CONTENTS</p>
      <a href="#authentication">身份验证</a>
      <a href="#chat">聊天补全</a>
      <a href="#responses">Responses</a>
      <a href="#editor-apis">编辑器接口</a>
      <a href="#capabilities">高级能力</a>
      <a href="#models">模型列表</a>
      <a href="#errors">错误响应</a>
      <a href="#examples">SDK 示例</a>
    </aside>

    <div class="docs-content">
      <article id="authentication" class="doc-section">
        <div class="doc-title">
          <BookOpen :size="19" />
          <h2>身份验证</h2>
        </div>
        <p>在“访问令牌”页面创建令牌，然后通过 HTTP Bearer 方式传入。没有任何启用令牌时，网关会放行全部请求。</p>
        <div class="code-block"><code>Authorization: Bearer YOUR_GATEWAY_TOKEN</code></div>
      </article>

      <article id="chat" class="doc-section">
        <div class="endpoint-heading">
          <StatusBadge tone="success">POST</StatusBadge>
          <code>/v1/chat/completions</code>
        </div>
        <p>创建聊天补全。兼容 OpenAI Chat Completions 请求格式，并支持 <code>stream: true</code> 的 SSE 流式响应。</p>
        <div class="parameter-table">
          <div><strong>model</strong><span>string · 必填</span><p>模型 ID，禁用的模型会返回 403。</p></div>
          <div><strong>messages</strong><span>array · 必填</span><p>按顺序排列的对话消息。</p></div>
          <div><strong>stream</strong><span>boolean · 可选</span><p>启用 Server-Sent Events 流式返回。</p></div>
        </div>
      </article>

      <article id="responses" class="doc-section">
        <div class="endpoint-heading">
          <StatusBadge tone="success">POST</StatusBadge>
          <code>/v1/responses</code>
        </div>
        <p>透传 Responses API 请求，支持普通 JSON 与流式响应。系统预设启用时会合并或替换 <code>instructions</code>。</p>
      </article>

      <article id="editor-apis" class="doc-section">
        <h2>编辑器兼容接口</h2>
        <div class="parameter-table">
          <div><strong>POST /v1/completions</strong><span>文本补全</span><p>用于仍依赖传统 Completions 或 FIM 请求的编辑器。</p></div>
          <div><strong>POST /v1/embeddings</strong><span>向量生成</span><p>请求会原样转发，模型和上游必须支持该接口。</p></div>
          <div><strong>GET /v1/models</strong><span>模型发现</span><p>返回控制台中启用的模型。</p></div>
        </div>
      </article>

      <article id="capabilities" class="doc-section">
        <h2>高级能力透传</h2>
        <p>以下字段不会被网关过滤，但最终是否生效由具体模型和上游接口决定。</p>
        <div class="parameter-table">
          <div><strong>reasoning_effort</strong><span>推理强度</span><p>支持上游接受的 low、medium、high 等值。</p></div>
          <div><strong>image_url</strong><span>图片理解</span><p>支持远程图片地址或 Base64 Data URL 消息内容。</p></div>
          <div><strong>tools / tool_choice</strong><span>工具调用</span><p>工具定义与模型返回内容均保持原格式。</p></div>
          <div><strong>response_format</strong><span>结构化输出</span><p>JSON Schema 等配置会直接转发。</p></div>
        </div>
      </article>

      <article id="models" class="doc-section">
        <div class="endpoint-heading">
          <StatusBadge tone="info">GET</StatusBadge>
          <code>/v1/models</code>
        </div>
        <p>返回模型列表。模型目录已同步时只返回控制台中启用的模型，否则直接透传上游目录。</p>
        <p>编辑器使用时，将 Base URL 设置为 <code>{{ baseUrl }}/v1</code>，API Key 使用“访问令牌”页面创建的令牌。</p>
      </article>

      <article id="errors" class="doc-section">
        <h2>错误响应</h2>
        <div class="parameter-table">
          <div><strong>401</strong><span>Unauthorized</span><p>访问令牌缺失或无效。</p></div>
          <div><strong>403</strong><span>Forbidden</span><p>请求的模型已被网关管理员禁用。</p></div>
          <div><strong>503</strong><span>Unavailable</span><p>密钥池为空，或全部密钥正在冷却。</p></div>
        </div>
      </article>

      <article id="examples" class="doc-section">
        <h2>cURL</h2>
        <div class="code-block code-block--multiline">
          <button class="copy-code" type="button" title="复制 cURL" @click="copy('curl', curlExample)">
            <Check v-if="copied === 'curl'" :size="15" />
            <Copy v-else :size="15" />
          </button>
          <pre><code>{{ curlExample }}</code></pre>
        </div>
        <h2>Python SDK</h2>
        <div class="code-block code-block--multiline">
          <button class="copy-code" type="button" title="复制 Python 示例" @click="copy('python', pythonExample)">
            <Check v-if="copied === 'python'" :size="15" />
            <Copy v-else :size="15" />
          </button>
          <pre><code>{{ pythonExample }}</code></pre>
        </div>
      </article>
    </div>
  </section>
</template>
