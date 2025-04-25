package constants

// HTTP Status Codes
const (
	StatusOK                  = 200
	StatusCreated             = 201
	StatusNoContent           = 204
	StatusBadRequest          = 400
	StatusUnauthorized        = 401
	StatusForbidden           = 403
	StatusNotFound            = 404
	StatusMethodNotAllowed    = 405
	StatusConflict            = 409
	StatusInternalServerError = 500
	StatusServiceUnavailable  = 503
)

// HTTP Response Code Types
const (
	ResponseSuccess          = true
	ResponseFailure          = false
	CodeBadRequest           = "bad_request"
	CodeUnauthorized         = "unauthorized"
	CodeForbidden            = "forbidden"
	CodeNotFound             = "not_found"
	CodeMethodNotAllowed     = "method_not_allowed"
	CodeConflict             = "conflict"
	CodeInternalError        = "internal_error"
	CodeValidationError      = "validation_error"
	CodeInvalidCredentials   = "invalid_credentials"
	CodeTokenExpired         = "token_expired"
	CodeTokenInvalid         = "token_invalid"
	CodeDuplicateResource    = "duplicate_resource"
	CodeServiceUnavailable   = "service_unavailable"
	CodeAuthenticationFailed = "authentication_failed"
)

// HTTP Header Names
const (
	HeaderContentType           = "Content-Type"
	HeaderContentLength         = "Content-Length"
	HeaderContentDisposition    = "Content-Disposition"
	HeaderCacheControl          = "Cache-Control"
	HeaderPragma                = "Pragma"
	HeaderExpires               = "Expires"
	HeaderAuthorization         = "Authorization"
	HeaderXRequestID            = "X-Request-ID"
	HeaderXCSRFToken            = "X-CSRF-Token"
	HeaderXAPIKey               = "X-API-Key"
	HeaderXContentTypeOptions   = "X-Content-Type-Options"
	HeaderXFrameOptions         = "X-Frame-Options"
	HeaderXXSSProtection        = "X-XSS-Protection"
	HeaderReferrerPolicy        = "Referrer-Policy"
	HeaderContentSecurityPolicy = "Content-Security-Policy"
)

// HTTP Content Types
const (
	ContentTypeJSON           = "application/json"
	ContentTypeOctetStream    = "application/octet-stream"
	ContentTypeFormURLEncoded = "application/x-www-form-urlencoded"
	ContentTypeMultipartForm  = "multipart/form-data"
)

// Security Header Values
const (
	FrameOptionsDeny           = "DENY"
	XSSProtectionModeBlock     = "1; mode=block"
	ContentTypeOptionsNoSniff  = "nosniff"
	ReferrerPolicyStrictOrigin = "strict-origin-when-cross-origin"
	CSPDefaultSrc              = "default-src 'self'"
	CacheControlNoStore        = "no-cache, no-store, must-revalidate"
	PragmaNoCache              = "no-cache"
	ExpiresZero                = "0"
)
