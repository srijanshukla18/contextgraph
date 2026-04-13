# ContextGraph Security Review

**Date**: 2025-12-31
**Reviewer**: Security Audit (Automated)
**Scope**: Complete codebase security audit

---

## [HIGH] Weak API Key Authentication Bypass
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:227-250
- **Type**: Insecure Authentication
- **Description**: When `REQUIRE_AUTH=false` or when `API_KEYS` is empty, authentication is completely bypassed.
- **Code snippet**:
```python
if not API_KEYS:
    logger.warning("No API_KEYS configured, authentication disabled")
    return "anonymous"
```
- **Risk**: Production deployment with misconfigured environment variables would expose all decision records without authentication.
- **Recommendation**: Fail closed by raising an exception when `REQUIRE_AUTH=true` but `API_KEYS` is empty.

---

## [HIGH] Server-Side Request Forgery (SSRF) Potential
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/sdk/python/contextgraph/core/client.py:163-183
- **Type**: SSRF
- **Description**: `urllib.request.urlopen` with user-configurable `server_url` without validation.
- **Risk**: Attacker could access cloud metadata endpoints (169.254.169.254), scan internal services.
- **Recommendation**: Implement URL allowlist, block private IP ranges.

---

## [HIGH] CORS Misconfiguration with Wildcard Credentials
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:176-182
- **Type**: CORS Misconfiguration
- **Description**: `allow_credentials=True` with user-configured origins and `allow_headers=["*"]`.
- **Risk**: Credential theft if ALLOWED_ORIGINS includes malicious domains.
- **Recommendation**: Validate origins, use explicit header allowlist.

---

## [MEDIUM] Missing Input Validation on Limit/Offset
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:667-696
- **Type**: Missing Input Validation
- **Description**: No minimum validation or negative value checks on offset.
- **Recommendation**: Add `offset: int = Query(default=0, ge=0, le=10000)`

---

## [MEDIUM] In-Memory Rate Limiting (Not Production-Safe)
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:117-141
- **Type**: Insufficient Rate Limiting
- **Description**: Rate limiter uses in-memory dictionary, not shared across instances.
- **Recommendation**: Implement Redis-based rate limiting.

---

## [MEDIUM] Database Credentials in Environment Variables
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:27
- **Type**: Credential Management
- **Description**: PostgreSQL connection string in plaintext env var.
- **Recommendation**: Use secrets management system.

---

## [MEDIUM] API Keys in Plaintext Environment
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:28
- **Type**: Credential Management
- **Description**: API keys as comma-separated plaintext, vulnerable to timing attacks.
- **Recommendation**: Hash keys with bcrypt, use constant-time comparison.

---

## [MEDIUM] Unsafe JSON Deserialization Without Size Limits
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:503-508
- **Type**: Insecure Deserialization
- **Description**: User-supplied JSON serialized to JSONB without size/depth validation.
- **Recommendation**: Add JSON size limits (max 1MB), depth validation.

---

## [MEDIUM] Missing HTTPS Enforcement
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:164-169
- **Type**: Insecure Transport
- **Description**: Server doesn't enforce HTTPS.
- **Recommendation**: Add HTTPS redirect middleware, HSTS headers.

---

## [MEDIUM] Information Disclosure in Health Endpoint
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py:431
- **Type**: Information Disclosure
- **Description**: Health check exposes first 50 chars of database errors.
- **Recommendation**: Return only generic "database unavailable" message.

---

## [LOW] Weak Default Credentials Example
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/.env.example
- **Type**: Weak Credentials Example
- **Description**: Placeholder values in example file.
- **Recommendation**: Add script to generate secure random values.

---

## [LOW] Docker Container Runs as Non-Root (POSITIVE)
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/Dockerfile
- **Type**: Security Best Practice
- **Description**: Correctly uses non-root user. No action needed.

---

## [LOW] SQL Queries Use Parameterization (POSITIVE)
- **File**: /Users/srijanshukla/code/projects/active-pending/contextgraph/server/main.py
- **Type**: Security Best Practice
- **Description**: All queries use proper %s placeholders. No SQL injection.

---

## Summary

**Total Issues**: 13
- Critical: 0
- High: 3
- Medium: 7
- Low: 3

**Priority Actions**:
1. Fix authentication bypass
2. Add SSRF protection
3. Harden CORS configuration
