// Package constants provides shared constant values used throughout the application.
//
// The general_const.go file defines general-purpose constants related to routing
// and request parameters. These constants ensure consistent API patterns and URL
// structure throughout the application, making the API more predictable and easier
// to maintain.
package constants

// Base Routes define the root URL paths for different parts of the API.
// These constants establish the URL hierarchy and API versioning strategy.
const (
	// APIBasePath is the root path prefix for all API endpoints.
	APIBasePath = "/api"

	// HealthPath is the endpoint for health checks and system status.
	HealthPath = "/health"
)

// URL Parameters define path parameter names used in route definitions.
// These constants are used when defining routes with path parameters and
// when extracting those parameters from requests.
const (
	// ParamKeyID is the URL parameter for API key identifiers.
	ParamKeyID = "keyID"

	// ParamEntityID is the URL parameter for entity identifiers.
	ParamEntityID = "entityID"

	// ParamMethodID is the URL parameter for detection method identifiers.
	ParamMethodID = "methodID"

	// ParamPatternID is the URL parameter for pattern identifiers.
	ParamPatternID = "patternID"

	// ParamTable is the URL parameter for database table names.
	ParamTable = "table"

	// ParamID is the URL parameter for generic resource identifiers.
	ParamID = "id"
)

// Query Parameters define common query string parameter names.
// These constants ensure consistent parameter naming in query strings
// across different API endpoints.
const (
	// QueryParamPage is the query parameter for pagination page number.
	QueryParamPage = "page"

	// QueryParamPageSize is the query parameter for pagination page size.
	QueryParamPageSize = "page_size"

	// QueryParamUsername is the query parameter for filtering by username.
	QueryParamUsername = "username"

	// QueryParamEmail is the query parameter for filtering by email.
	QueryParamEmail = "email"
)
