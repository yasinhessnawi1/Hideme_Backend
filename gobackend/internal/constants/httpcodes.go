// Package constants provides shared constant values used throughout the application.
//
// The httpcodes.go file defines HTTP-related constants such as status codes,
// response codes, headers, and content types. These constants ensure consistent
// HTTP communication patterns across the application and provide meaningful
// standardized responses to API clients. The security header values implement
// recommended web security best practices.
package constants

// HTTP Status Codes define the standard HTTP response status codes used in the application.
// These codes indicate the result of the HTTP request processing.
const (
	// StatusOK indicates that the request has succeeded.
	StatusOK = 200

	// StatusCreated indicates that the request has succeeded and a new resource has been created.
	StatusCreated = 201

	// StatusNoContent indicates that the request has succeeded but there is no content to send.
	StatusNoContent = 204

	// StatusBadRequest indicates that the server cannot process the request due to client error.
	StatusBadRequest = 400

	// StatusUnauthorized indicates that the request lacks valid authentication credentials.
	StatusUnauthorized = 401

	// StatusForbidden indicates that the server understood the request but refuses to authorize it.
	StatusForbidden = 403

	// StatusNotFound indicates that the server cannot find the requested resource.
	StatusNotFound = 404

	// StatusMethodNotAllowed indicates that the request method is not supported for the requested resource.
	StatusMethodNotAllowed = 405

	// StatusConflict indicates that the request conflicts with the current state of the server.
	StatusConflict = 409

	// StatusInternalServerError indicates that the server encountered an unexpected condition.
	StatusInternalServerError = 500
)

// HTTP Response Code Types define application-specific response codes.
// These codes provide more detailed information about the response beyond HTTP status codes.
const (
	// ResponseSuccess indicates that the request was processed successfully.
	ResponseSuccess = true

	// ResponseFailure indicates that the request processing failed.
	ResponseFailure = false

	// CodeBadRequest indicates a malformed or invalid request.
	CodeBadRequest = "bad_request"

	// CodeUnauthorized indicates missing or invalid authentication.
	CodeUnauthorized = "unauthorized"

	// CodeForbidden indicates the user lacks permission for the requested action.
	CodeForbidden = "forbidden"

	// CodeNotFound indicates the requested resource does not exist.
	CodeNotFound = "not_found"

	// CodeMethodNotAllowed indicates the HTTP method is not allowed for the endpoint.
	CodeMethodNotAllowed = "method_not_allowed"

	// CodeConflict indicates a resource conflict, such as a duplicate entry.
	CodeConflict = "conflict"

	// CodeInternalError indicates an unexpected server error.
	CodeInternalError = "internal_error"

	// CodeValidationError indicates request validation failed.
	CodeValidationError = "validation_error"

	// CodeInvalidCredentials indicates provided authentication credentials are incorrect.
	CodeInvalidCredentials = "invalid_credentials"

	// CodeTokenExpired indicates an authentication token has expired.
	CodeTokenExpired = "token_expired"

	// CodeTokenInvalid indicates an authentication token is malformed or invalid.
	CodeTokenInvalid = "token_invalid"

	// CodeDuplicateResource indicates an attempt to create a resource that already exists.
	CodeDuplicateResource = "duplicate_resource"

	// CodeAuthenticationFailed indicates a general authentication failure.
	CodeAuthenticationFailed = "authentication_failed"
)

// HTTP Header Names define common HTTP headers used in requests and responses.
// These constants ensure consistent header usage throughout the application.
const (
	// HeaderContentType specifies the media type of the resource.
	HeaderContentType = "Content-Type"

	// HeaderContentLength specifies the size of the entity-body in bytes.
	HeaderContentLength = "Content-Length"

	// HeaderContentDisposition suggests how the content should be displayed.
	HeaderContentDisposition = "Content-Disposition"

	// HeaderCacheControl directs caching behavior for the request/response chain.
	HeaderCacheControl = "Cache-Control"

	// HeaderPragma provides implementation-specific directives that might apply to any
	// recipient along the request/response chain.
	HeaderPragma = "Pragma"

	// HeaderExpires specifies the date/time after which the response is considered stale.
	HeaderExpires = "Expires"

	// HeaderAuthorization provides authentication credentials for HTTP authentication.
	HeaderAuthorization = "Authorization"

	// HeaderXRequestID contains a unique identifier for the HTTP request.
	HeaderXRequestID = "X-Request-ID"

	// HeaderXCSRFToken contains the Cross-Site Request Forgery protection token.
	HeaderXCSRFToken = "X-CSRF-Token"

	// HeaderXAPIKey contains the API key for authentication.
	HeaderXAPIKey = "X-API-Key"

	// HeaderXContentTypeOptions controls MIME type sniffing.
	HeaderXContentTypeOptions = "X-Content-Type-Options"

	// HeaderXFrameOptions controls whether the page can be displayed in a frame.
	HeaderXFrameOptions = "X-Frame-Options"

	// HeaderXXSSProtection enables the Cross-site scripting (XSS) filter in browsers.
	HeaderXXSSProtection = "X-XSS-Protection"

	// HeaderReferrerPolicy controls how much referrer information should be included with requests.
	HeaderReferrerPolicy = "Referrer-Policy"

	// HeaderContentSecurityPolicy defines content sources which are approved and can be loaded.
	HeaderContentSecurityPolicy = "Content-Security-Policy"
)

// HTTP Content Types define media types used in the Content-Type header.
// These constants ensure consistent content type specification.
const (
	// ContentTypeJSON specifies the content is in JSON format.
	ContentTypeJSON = "application/json"

	// ContentTypeOctetStream specifies the content is an arbitrary binary data stream.
	ContentTypeOctetStream = "application/octet-stream"
)

// Security Header Values define the values for various security-related HTTP headers.
// These values implement recommended web security best practices.
const (
	// FrameOptionsDeny prevents the page from being displayed in a frame.
	FrameOptionsDeny = "DENY"

	// XSSProtectionModeBlock enables XSS filtering and prevents page rendering if an attack is detected.
	XSSProtectionModeBlock = "1; mode=block"

	// ContentTypeOptionsNoSniff prevents MIME type sniffing.
	ContentTypeOptionsNoSniff = "nosniff"

	// ReferrerPolicyStrictOrigin restricts referrer information to origin only for cross-origin requests.
	ReferrerPolicyStrictOrigin = "strict-origin-when-cross-origin"

	// CSPDefaultSrc restricts content sources to the same origin by default.
	CSPDefaultSrc = "default-src 'self'"

	// CacheControlNoStore prevents caching of sensitive information.
	CacheControlNoStore = "no-cache, no-store, must-revalidate"

	// PragmaNoCache prevents caching in HTTP/1.0 caches.
	PragmaNoCache = "no-cache"

	// ExpiresZero sets the expiration date to the past to prevent caching.
	ExpiresZero = "0"
)
