import axios from 'axios'
console.log("VITE_API_URL =", import.meta.env.VITE_API_URL)

export const API_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:8000` : '')

export const API_BASE = '/api/v1'
const BASE_URL = API_URL ? `${API_URL}${API_BASE}` : API_BASE

export const apiClient = axios.create({
  baseURL: BASE_URL,
})

// Request interceptor to log payloads for verification
apiClient.interceptors.request.use(config => {
  console.log("API_REQUEST_PAYLOAD:", config.method, config.url, JSON.stringify(config.data))
  return config;
})


export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await apiClient.post('/documents/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function createEnvelope({ documentId, signer, participants, signaturePosition = null, ...rest }) {
  const payload = {
    document_id: documentId,
    ...(signer && { signer }),
    ...(participants && { participants }),
    // Include ratio-based placement only when the sender clicked a position.
    // x_ratio / y_ratio are 0.0–1.0 relative to the rendered page dimensions.
    ...(signaturePosition && {
      signature_page: signaturePosition.page,
      signature_x_ratio: signaturePosition.x_ratio,
      signature_y_ratio: signaturePosition.y_ratio,
    }),
    ...rest
  }

  const { data } = await apiClient.post('/envelopes/', payload)
  return data
}

export async function sendEnvelope(envelopeId) {
  const { data } = await apiClient.post(`/envelopes/${envelopeId}/send/`)
  return data
}

// Persist a draft envelope (is_draft=true skips workflow activation)
export async function saveDraft(payload) {
  return createEnvelope({ ...payload, is_draft: true })
}

// Update an existing draft envelope (PATCH — participants and fields are replaced)
export async function updateDraft(id, payload) {
  const { data } = await apiClient.patch(`/envelopes/${id}/`, payload)
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

export async function getDashboardData() {
  const { data } = await apiClient.get('/dashboard/')
  return data
}

export async function getPackageDetail(id) {
  const { data } = await apiClient.get(`/packages/${id}/`)
  return data
}

export async function getPackages() {
  const { data } = await apiClient.get('/packages/')
  return data
}

export async function getTemplates() {
  const { data } = await apiClient.get('/templates/')
  return data
}

export async function getTemplateDetail(id) {
  const { data } = await apiClient.get(`/templates/${id}/`)
  return data
}

export async function createTemplate(payload) {
  const { data } = await apiClient.post('/templates/', payload)
  return data
}

export async function updateTemplate(id, payload) {
  const { data } = await apiClient.put(`/templates/${id}/`, payload)
  return data
}

export async function deleteTemplate(id) {
  const { data } = await apiClient.delete(`/templates/${id}/`)
  return data
}

export async function loginUser(username, password) {
  const { data } = await apiClient.post('/auth/login/', { username, password })
  return data
}

export async function registerUser(username, email, password) {
  const { data } = await apiClient.post('/auth/register/', { username, email, password })
  return data
}

export async function logoutUser() {
  const { data } = await apiClient.post('/auth/logout/')
  return data
}

export async function getUserMe() {
  const { data } = await apiClient.get('/auth/me/')
  return data
}

export async function analyzeContract(file, envelopeId = null) {
  const formData = new FormData()
  formData.append('file', file)
  if (envelopeId) {
    formData.append('envelope_id', envelopeId)
  }

  const { data } = await apiClient.post('/contracts/analyze/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function confirmCandidates(envelopeId, candidateIds) {
  const { data } = await apiClient.post(`/envelopes/${envelopeId}/confirm-candidates/`, {
    candidate_ids: candidateIds
  })
  return data
}

export async function ignoreCandidates(envelopeId, candidateIds) {
  const { data } = await apiClient.post(`/envelopes/${envelopeId}/ignore-candidates/`, {
    candidate_ids: candidateIds
  })
  return data
}

export async function getAuthorizationStatus(participantId, token) {
  const { data } = await apiClient.get(`/participants/${participantId}/authorization-status/`, {
    headers: { 'X-Participant-Token': token }
  })
  return data
}

export async function acceptTerms(participantId, token) {
  const { data } = await apiClient.post(`/participants/${participantId}/accept-terms/`, {
    accepted: true
  }, {
    headers: { 'X-Participant-Token': token }
  })
  return data
}

export async function sendEmailOTP(participantId, token) {
  const { data } = await apiClient.post(`/participants/${participantId}/send-email-otp/`, {}, {
    headers: { 'X-Participant-Token': token }
  })
  return data
}

export async function verifyEmailOTP(participantId, otp, token) {
  const { data } = await apiClient.post(`/participants/${participantId}/verify-email-otp/`, {
    otp
  }, {
    headers: { 'X-Participant-Token': token }
  })
  return data
}

export async function submitFaceVerification(participantId, selfieImage, token) {
  const formData = new FormData()
  formData.append('selfie_image', selfieImage)

  const { data } = await apiClient.post(`/participants/${participantId}/face-verification/`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-Participant-Token': token
    }
  })
  return data
}

export async function submitIdentityVerification(participantId, documentImage, token) {
  const formData = new FormData()
  formData.append('document_image', documentImage)

  const { data } = await apiClient.post(`/participants/${participantId}/identity-verification/`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-Participant-Token': token
    }
  })
  return data
}




