import { expect, test } from '@playwright/test'

test('edge blocks internal routes and rejects oversized JSON before authentication', async ({ request }) => {
  expect((await request.get('/api/v1/internal/uploads/admission')).status()).toBe(404)
  const oversized = await request.post('/api/v1/auth/session', {
    data: { username: 'synthetic-nobody', password: 'x'.repeat(300_000) },
  })
  expect(oversized.status()).toBe(413)
})

test('forged forwarding headers cannot evade shared login admission through Caddy', async ({ request }) => {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await request.post('/api/v1/auth/session', {
      headers: { 'X-Forwarded-For': `203.0.113.${attempt + 1}` },
      data: { username: `synthetic-missing-${attempt}`, password: 'invalid-synthetic-password' },
    })
    expect(response.status()).toBe(401)
  }
  const limited = await request.post('/api/v1/auth/session', {
    headers: { 'X-Forwarded-For': '198.51.100.7', 'X-Real-IP': '198.51.100.8' },
    data: { username: 'synthetic-missing-final', password: 'invalid-synthetic-password' },
  })
  expect(limited.status()).toBe(429)
  expect(Number(limited.headers()['retry-after'])).toBeGreaterThan(0)
})
