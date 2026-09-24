export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers,
  })
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await response.json() : null
  if (!response.ok) {
    const error = new Error(data?.detail || data?.error?.message || '请求失败')
    error.status = response.status
    throw error
  }
  return data
}

export function jsonBody(value) {
  return JSON.stringify(value)
}
