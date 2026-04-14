# Postman Scenario: Semantic Cache Miss to Tiered LLM Invocation

## Goal
Validate one automation path end-to-end:
1. Chat request enters Go backend.
2. Semantic cache lookup misses.
3. Request is routed to a tier.
4. LLM is invoked using that tier.
5. Response is returned with a non-cache model.

## Environment
- GO_BASE_URL = http://localhost:8080
- session_id = empty

## Scenario Name
Cache miss should trigger tier routing and LLM call

## Step 1: Create Session
- Method: POST
- URL: {{GO_BASE_URL}}/session
- Body: none

Tests:
```javascript
pm.test('Session created', function () {
  pm.response.to.have.status(201);
  const body = pm.response.json();
  pm.expect(body).to.have.property('session_id');
  pm.environment.set('session_id', body.session_id);
});
```

## Step 2: Send a New Complex Prompt (Expected Cache Miss)
Use a prompt that is unlikely to already exist in cache.

- Method: POST
- URL: {{GO_BASE_URL}}/chat
- Body:
```json
{
  "session_id": "{{session_id}}",
  "prompt": "Design a phased migration strategy from monolith to microservices with rollback, observability, and cost controls."
}
```

Tests:
```javascript
pm.test('Chat call succeeded', function () {
  pm.response.to.have.status(200);
});

pm.test('Cache miss occurred', function () {
  const body = pm.response.json();
  pm.expect(body).to.have.property('cache_hit');
  pm.expect(body.cache_hit).to.eql(false);
});

pm.test('Tiered LLM path was used (not semantic-cache)', function () {
  const body = pm.response.json();
  pm.expect(body).to.have.property('model_used');
  pm.expect(body.model_used).to.not.eql('semantic-cache');
});

pm.test('Response contract is valid', function () {
  const body = pm.response.json();
  pm.expect(body).to.have.property('response');
  pm.expect(body.response).to.be.a('string').and.not.empty;
  pm.expect(body).to.have.property('tokens_used');
  pm.expect(body.tokens_used).to.be.a('number');
});
```

## Optional Step 3: Verify It Is Cached After First Miss
Repeat the exact same request from Step 2.

Expected:
- cache_hit = true
- model_used = semantic-cache

## Pass Criteria
- First call returns cache_hit as false.
- First call returns model_used not equal to semantic-cache.
- First call returns a valid response payload.
- Optional repeat call shows cache_hit true, proving write-back after LLM completion.
