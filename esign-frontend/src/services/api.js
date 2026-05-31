import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:8000` : '')

const BASE_URL = API_URL ? `${API_URL}/api` : '/api'

export const apiClient = axios.create({
  baseURL: BASE_URL,
})

export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await apiClient.post('/documents/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function createEnvelope({ documentId, signer, signaturePosition = null }) {
  const payload = {
    document_id: documentId,
    signer,
    // Include ratio-based placement only when the sender clicked a position.
    // x_ratio / y_ratio are 0.0–1.0 relative to the rendered page dimensions.
    ...(signaturePosition && {
      signature_page:    signaturePosition.page,
      signature_x_ratio: signaturePosition.x_ratio,
      signature_y_ratio: signaturePosition.y_ratio,
    }),
  }

  const { data } = await apiClient.post('/envelopes/', payload)
  return data
}

export async function sendEnvelope(envelopeId) {
  const { data } = await apiClient.post(`/envelopes/${envelopeId}/send/`)
  return data
}

export async function getSigningSession(token) {
  const { data } = await apiClient.get(`/sign/${token}/`)
  return data
}

export async function completeSigning(token, payload) {
  const response = await apiClient.post(
    `/sign/${token}/`,
    payload
  )

  return response.data
}

